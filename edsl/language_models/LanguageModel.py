"""This module contains the LanguageModel class, which is an abstract base class for all language models.

Terminology:

raw_response: The JSON response from the model. This has all the model meta-data about the call. 

edsl_augmented_response: The JSON response from model, but augmented with EDSL-specific information, 
such as the cache key, token usage, etc. 

generated_tokens: The actual tokens generated by the model. This is the output that is used by the user.
edsl_answer_dict: The parsed JSON response from the model either {'answer': ...} or {'answer': ..., 'comment': ...}

"""

from __future__ import annotations
import warnings
from functools import wraps
import asyncio
import json
import time
import os
import hashlib
from typing import (
    Coroutine,
    Any,
    Callable,
    Type,
    Union,
    List,
    get_type_hints,
    TypedDict,
    Optional,
)
from abc import ABC, abstractmethod

from json_repair import repair_json

from edsl.data_transfer_models import (
    ModelResponse,
    ModelInputs,
    EDSLOutput,
    AgentResponseDict,
)


from edsl.config import CONFIG
from edsl.utilities.decorators import sync_wrapper, jupyter_nb_handler
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version
from edsl.language_models.repair import repair
from edsl.enums import InferenceServiceType
from edsl.Base import RichPrintingMixin, PersistenceMixin
from edsl.enums import service_to_api_keyname
from edsl.exceptions import MissingAPIKeyError
from edsl.language_models.RegisterLanguageModelsMeta import RegisterLanguageModelsMeta
from edsl.exceptions.language_models import LanguageModelBadResponseError

TIMEOUT = float(CONFIG.get("EDSL_API_TIMEOUT"))


def convert_answer(response_part):
    import json

    response_part = response_part.strip()

    if response_part == "None":
        return None

    repaired = repair_json(response_part)
    if repaired == '""':
        # it was a literal string
        return response_part

    try:
        return json.loads(repaired)
    except json.JSONDecodeError as j:
        # last resort
        return response_part


def extract_item_from_raw_response(data, key_sequence):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return data
    current_data = data
    for i, key in enumerate(key_sequence):
        try:
            if isinstance(current_data, (list, tuple)):
                if not isinstance(key, int):
                    raise TypeError(
                        f"Expected integer index for sequence at position {i}, got {type(key).__name__}"
                    )
                if key < 0 or key >= len(current_data):
                    raise IndexError(
                        f"Index {key} out of range for sequence of length {len(current_data)} at position {i}"
                    )
            elif isinstance(current_data, dict):
                if key not in current_data:
                    raise KeyError(
                        f"Key '{key}' not found in dictionary at position {i}"
                    )
            else:
                raise TypeError(
                    f"Cannot index into {type(current_data).__name__} at position {i}. Full response is: {data} of type {type(data)}. Key sequence is: {key_sequence}"
                )

            current_data = current_data[key]
        except Exception as e:
            path = " -> ".join(map(str, key_sequence[: i + 1]))
            if "error" in data:
                msg = data["error"]
            else:
                msg = f"Error accessing path: {path}. {str(e)}. Full response is: '{data}'"
            raise LanguageModelBadResponseError(message=msg, response_json=data)
    if isinstance(current_data, str):
        return current_data.strip()
    else:
        return current_data


def handle_key_error(func):
    """Handle KeyError exceptions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
            assert True == False
        except KeyError as e:
            return f"""KeyError occurred: {e}. This is most likely because the model you are using 
            returned a JSON object we were not expecting."""

    return wrapper


class LanguageModel(
    RichPrintingMixin, PersistenceMixin, ABC, metaclass=RegisterLanguageModelsMeta
):
    """ABC for LLM subclasses.

    TODO:

    1) Need better, more descriptive names for functions

    get_model_response_no_cache  (currently called async_execute_model_call)

    get_model_response (currently called async_get_raw_response; uses cache & adds tracking info)
      Calls:
        - async_execute_model_call
        - _updated_model_response_with_tracking

    get_answer (currently called async_get_response)
        This parses out the answer block and does some error-handling.
        Calls:
            - async_get_raw_response
            - parse_response


    """

    _model_ = None
    key_sequence = (
        None  # This should be something like ["choices", 0, "message", "content"]
    )
    __rate_limits = None
    _safety_factor = 0.8

    def __init__(
        self, tpm=None, rpm=None, omit_system_prompt_if_empty_string=True, **kwargs
    ):
        """Initialize the LanguageModel."""
        self.model = getattr(self, "_model_", None)
        default_parameters = getattr(self, "_parameters_", None)
        parameters = self._overide_default_parameters(kwargs, default_parameters)
        self.parameters = parameters
        self.remote = False
        self.omit_system_prompt_if_empty = omit_system_prompt_if_empty_string

        # self._rpm / _tpm comes from the class
        if rpm is not None:
            self._rpm = rpm

        if tpm is not None:
            self._tpm = tpm

        for key, value in parameters.items():
            setattr(self, key, value)

        for key, value in kwargs.items():
            if key not in parameters:
                setattr(self, key, value)

        if "use_cache" in kwargs:
            warnings.warn(
                "The use_cache parameter is deprecated. Use the Cache class instead."
            )

        if skip_api_key_check := kwargs.get("skip_api_key_check", False):
            # Skip the API key check. Sometimes this is useful for testing.
            self._api_token = None

    def ask_question(self, question):
        user_prompt = question.get_instructions().render(question.data).text
        system_prompt = "You are a helpful agent pretending to be a human."
        return self.execute_model_call(user_prompt, system_prompt)

    @property
    def api_token(self) -> str:
        if not hasattr(self, "_api_token"):
            key_name = service_to_api_keyname.get(self._inference_service_, "NOT FOUND")
            if self._inference_service_ == "bedrock":
                self._api_token = [os.getenv(key_name[0]), os.getenv(key_name[1])]
                # Check if any of the tokens are None
                missing_token = any(token is None for token in self._api_token)
            else:
                self._api_token = os.getenv(key_name)
                missing_token = self._api_token is None
            if missing_token and self._inference_service_ != "test" and not self.remote:
                print("raising error")
                raise MissingAPIKeyError(
                    f"""The key for service: `{self._inference_service_}` is not set.
                        Need a key with name {key_name} in your .env file."""
                )

        return self._api_token

    def __getitem__(self, key):
        return getattr(self, key)

    def _repr_html_(self):
        from edsl.utilities.utilities import data_to_html

        return data_to_html(self.to_dict())

    def hello(self, verbose=False):
        """Runs a simple test to check if the model is working."""
        token = self.api_token
        masked = token[: min(8, len(token))] + "..."
        if verbose:
            print(f"Current key is {masked}")
        return self.execute_model_call(
            user_prompt="Hello, model!", system_prompt="You are a helpful agent."
        )

    def has_valid_api_key(self) -> bool:
        """Check if the model has a valid API key.

        >>> LanguageModel.example().has_valid_api_key() : # doctest: +SKIP
        True

        This method is used to check if the model has a valid API key.
        """
        from edsl.enums import service_to_api_keyname
        import os

        if self._model_ == "test":
            return True

        key_name = service_to_api_keyname.get(self._inference_service_, "NOT FOUND")
        key_value = os.getenv(key_name)
        return key_value is not None

    def __hash__(self) -> str:
        """Allow the model to be used as a key in a dictionary."""
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict())

    def __eq__(self, other):
        """Check is two models are the same.

        >>> m1 = LanguageModel.example()
        >>> m2 = LanguageModel.example()
        >>> m1 == m2
        True

        """
        return self.model == other.model and self.parameters == other.parameters

    def set_rate_limits(self, rpm=None, tpm=None) -> None:
        """Set the rate limits for the model.

        >>> m = LanguageModel.example()
        >>> m.set_rate_limits(rpm=100, tpm=1000)
        >>> m.RPM
        100
        """
        if rpm is not None:
            self._rpm = rpm
        if tpm is not None:
            self._tpm = tpm
        return None
        # self._set_rate_limits(rpm=rpm, tpm=tpm)

    # def _set_rate_limits(self, rpm=None, tpm=None) -> None:
    #     """Set the rate limits for the model.

    #     If the model does not have rate limits, use the default rate limits."""
    #     if rpm is not None and tpm is not None:
    #         self.__rate_limits = {"rpm": rpm, "tpm": tpm}
    #         return

    #     if self.__rate_limits is None:
    #         if hasattr(self, "get_rate_limits"):
    #             self.__rate_limits = self.get_rate_limits()
    #         else:
    #             self.__rate_limits = self.__default_rate_limits

    @property
    def RPM(self):
        """Model's requests-per-minute limit."""
        # self._set_rate_limits()
        # return self._safety_factor * self.__rate_limits["rpm"]
        return self._rpm

    @property
    def TPM(self):
        """Model's tokens-per-minute limit."""
        # self._set_rate_limits()
        # return self._safety_factor * self.__rate_limits["tpm"]
        return self._tpm

    @property
    def rpm(self):
        return self._rpm

    @rpm.setter
    def rpm(self, value):
        self._rpm = value

    @property
    def tpm(self):
        return self._tpm

    @tpm.setter
    def tpm(self, value):
        self._tpm = value

    @staticmethod
    def _overide_default_parameters(passed_parameter_dict, default_parameter_dict):
        """Return a dictionary of parameters, with passed parameters taking precedence over defaults.

        >>> LanguageModel._overide_default_parameters(passed_parameter_dict={"temperature": 0.5}, default_parameter_dict={"temperature":0.9})
        {'temperature': 0.5}
        >>> LanguageModel._overide_default_parameters(passed_parameter_dict={"temperature": 0.5}, default_parameter_dict={"temperature":0.9, "max_tokens": 1000})
        {'temperature': 0.5, 'max_tokens': 1000}
        """
        # parameters = dict({})

        # this is the case when data is loaded from a dict after serialization
        if "parameters" in passed_parameter_dict:
            passed_parameter_dict = passed_parameter_dict["parameters"]
        return {
            parameter_name: passed_parameter_dict.get(parameter_name, default_value)
            for parameter_name, default_value in default_parameter_dict.items()
        }

    def __call__(self, user_prompt: str, system_prompt: str):
        return self.execute_model_call(user_prompt, system_prompt)

    @abstractmethod
    async def async_execute_model_call(user_prompt: str, system_prompt: str):
        """Execute the model call and returns a coroutine.

        >>> m = LanguageModel.example(test_model = True)
        >>> async def test(): return await m.async_execute_model_call("Hello, model!", "You are a helpful agent.")
        >>> asyncio.run(test())
        {'message': [{'text': 'Hello world'}], ...}

        >>> m.execute_model_call("Hello, model!", "You are a helpful agent.")
        {'message': [{'text': 'Hello world'}], ...}
        """
        pass

    async def remote_async_execute_model_call(
        self, user_prompt: str, system_prompt: str
    ):
        """Execute the model call and returns the result as a coroutine, using Coop."""
        from edsl.coop import Coop

        client = Coop()
        response_data = await client.remote_async_execute_model_call(
            self.to_dict(), user_prompt, system_prompt
        )
        return response_data

    @jupyter_nb_handler
    def execute_model_call(self, *args, **kwargs) -> Coroutine:
        """Execute the model call and returns the result as a coroutine.

        >>> m = LanguageModel.example(test_model = True)
        >>> m.execute_model_call(user_prompt = "Hello, model!", system_prompt = "You are a helpful agent.")

        """

        async def main():
            results = await asyncio.gather(
                self.async_execute_model_call(*args, **kwargs)
            )
            return results[0]  # Since there's only one task, return its result

        return main()

    @classmethod
    def get_generated_token_string(cls, raw_response: dict[str, Any]) -> str:
        """Return the generated token string from the raw response."""
        return extract_item_from_raw_response(raw_response, cls.key_sequence)

    @classmethod
    def get_usage_dict(cls, raw_response: dict[str, Any]) -> dict[str, Any]:
        """Return the usage dictionary from the raw response."""
        if not hasattr(cls, "usage_sequence"):
            raise NotImplementedError(
                "This inference service does not have a usage_sequence."
            )
        return extract_item_from_raw_response(raw_response, cls.usage_sequence)

    @classmethod
    def parse_response(cls, raw_response: dict[str, Any]) -> EDSLOutput:
        """Parses the API response and returns the response text."""
        generated_token_string = cls.get_generated_token_string(raw_response)
        last_newline = generated_token_string.rfind("\n")

        if last_newline == -1:
            # There is no comment
            edsl_dict = {
                "answer": convert_answer(generated_token_string),
                "generated_tokens": generated_token_string,
                "comment": None,
            }
        else:
            edsl_dict = {
                "answer": convert_answer(generated_token_string[:last_newline]),
                "comment": generated_token_string[last_newline + 1 :].strip(),
                "generated_tokens": generated_token_string,
            }
        return EDSLOutput(**edsl_dict)

    async def _async_get_intended_model_call_outcome(
        self,
        user_prompt: str,
        system_prompt: str,
        cache: "Cache",
        iteration: int = 0,
        files_list=None,
    ) -> ModelResponse:
        """Handle caching of responses.

        :param user_prompt: The user's prompt.
        :param system_prompt: The system's prompt.
        :param iteration: The iteration number.
        :param cache: The cache to use.

        If the cache isn't being used, it just returns a 'fresh' call to the LLM.
        But if cache is being used, it first checks the database to see if the response is already there.
        If it is, it returns the cached response, but again appends some tracking information.
        If it isn't, it calls the LLM, saves the response to the database, and returns the response with tracking information.

        If self.use_cache is True, then attempts to retrieve the response from the database;
        if not in the DB, calls the LLM and writes the response to the DB.

        >>> from edsl import Cache
        >>> m = LanguageModel.example(test_model = True)
        >>> m._get_intended_model_call_outcome(user_prompt = "Hello", system_prompt = "hello", cache = Cache())
        ModelResponse(...)"""

        if files_list:
            files_hash = "+".join([str(hash(file)) for file in files_list])
            # print(f"Files hash: {files_hash}")
            user_prompt_with_hashes = user_prompt + f" {files_hash}"
        else:
            user_prompt_with_hashes = user_prompt

        cache_call_params = {
            "model": str(self.model),
            "parameters": self.parameters,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt_with_hashes,
            "iteration": iteration,
        }
        cached_response, cache_key = cache.fetch(**cache_call_params)

        if cache_used := cached_response is not None:
            response = json.loads(cached_response)
        else:
            f = (
                self.remote_async_execute_model_call
                if hasattr(self, "remote") and self.remote
                else self.async_execute_model_call
            )
            params = {
                "user_prompt": user_prompt,
                "system_prompt": system_prompt,
                "files_list": files_list
                # **({"encoded_image": encoded_image} if encoded_image else {}),
            }
            # response = await f(**params)
            response = await asyncio.wait_for(f(**params), timeout=TIMEOUT)
            new_cache_key = cache.store(
                **cache_call_params, response=response
            )  # store the response in the cache
            assert new_cache_key == cache_key  # should be the same

        cost = self.cost(response)

        return ModelResponse(
            response=response,
            cache_used=cache_used,
            cache_key=cache_key,
            cached_response=cached_response,
            cost=cost,
        )

    _get_intended_model_call_outcome = sync_wrapper(
        _async_get_intended_model_call_outcome
    )

    # get_raw_response = sync_wrapper(async_get_raw_response)

    def simple_ask(
        self,
        question: "QuestionBase",
        system_prompt="You are a helpful agent pretending to be a human.",
        top_logprobs=2,
    ):
        """Ask a question and return the response."""
        self.logprobs = True
        self.top_logprobs = top_logprobs
        return self.execute_model_call(
            user_prompt=question.human_readable(), system_prompt=system_prompt
        )

    async def async_get_response(
        self,
        user_prompt: str,
        system_prompt: str,
        cache: "Cache",
        iteration: int = 1,
        files_list: Optional[List["File"]] = None,
    ) -> dict:
        """Get response, parse, and return as string.

        :param user_prompt: The user's prompt.
        :param system_prompt: The system's prompt.
        :param iteration: The iteration number.
        :param cache: The cache to use.
        :param encoded_image: The encoded image to use.

        """
        params = {
            "user_prompt": user_prompt,
            "system_prompt": system_prompt,
            "iteration": iteration,
            "cache": cache,
            "files_list": files_list,
        }
        model_inputs = ModelInputs(user_prompt=user_prompt, system_prompt=system_prompt)
        model_outputs = await self._async_get_intended_model_call_outcome(**params)
        edsl_dict = self.parse_response(model_outputs.response)
        agent_response_dict = AgentResponseDict(
            model_inputs=model_inputs,
            model_outputs=model_outputs,
            edsl_dict=edsl_dict,
        )
        return agent_response_dict

        # return await self._async_prepare_response(model_call_outcome, cache=cache)

    get_response = sync_wrapper(async_get_response)

    def cost(self, raw_response: dict[str, Any]) -> Union[float, str]:
        """Return the dollar cost of a raw response."""

        usage = self.get_usage_dict(raw_response)
        from edsl.coop import Coop

        c = Coop()
        price_lookup = c.fetch_prices()
        key = (self._inference_service_, self.model)
        if key not in price_lookup:
            return f"Could not find price for model {self.model} in the price lookup."

        relevant_prices = price_lookup[key]
        try:
            input_tokens = int(usage[self.input_token_name])
            output_tokens = int(usage[self.output_token_name])
        except Exception as e:
            return f"Could not fetch tokens from model response: {e}"

        try:
            inverse_output_price = relevant_prices["output"]["one_usd_buys"]
            inverse_input_price = relevant_prices["input"]["one_usd_buys"]
        except Exception as e:
            if "output" not in relevant_prices:
                return f"Could not fetch prices from {relevant_prices} - {e}; Missing 'output' key."
            if "input" not in relevant_prices:
                return f"Could not fetch prices from {relevant_prices} - {e}; Missing 'input' key."
            return f"Could not fetch prices from {relevant_prices} - {e}"

        if inverse_input_price == "infinity":
            input_cost = 0
        else:
            try:
                input_cost = input_tokens / float(inverse_input_price)
            except Exception as e:
                return f"Could not compute input price - {e}."

        if inverse_output_price == "infinity":
            output_cost = 0
        else:
            try:
                output_cost = output_tokens / float(inverse_output_price)
            except Exception as e:
                return f"Could not compute output price - {e}"

        return input_cost + output_cost

    #######################
    # SERIALIZATION METHODS
    #######################
    def _to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "parameters": self.parameters}

    @add_edsl_version
    def to_dict(self) -> dict[str, Any]:
        """Convert instance to a dictionary.

        >>> m = LanguageModel.example()
        >>> m.to_dict()
        {'model': '...', 'parameters': {'temperature': ..., 'max_tokens': ..., 'top_p': ..., 'frequency_penalty': ..., 'presence_penalty': ..., 'logprobs': False, 'top_logprobs': ...}, 'edsl_version': '...', 'edsl_class_name': 'LanguageModel'}
        """
        return self._to_dict()

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict) -> Type[LanguageModel]:
        """Convert dictionary to a LanguageModel child instance."""
        from edsl.language_models.registry import get_model_class

        model_class = get_model_class(data["model"])
        # data["use_cache"] = True
        return model_class(**data)

    #######################
    # DUNDER METHODS
    #######################
    def print(self):
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __repr__(self) -> str:
        """Return a string representation of the object."""
        param_string = ", ".join(
            f"{key} = {value}" for key, value in self.parameters.items()
        )
        return (
            f"Model(model_name = '{self.model}'"
            + (f", {param_string}" if param_string else "")
            + ")"
        )

    def __add__(self, other_model: Type[LanguageModel]) -> Type[LanguageModel]:
        """Combine two models into a single model (other_model takes precedence over self)."""
        print(
            f"""Warning: one model is replacing another. If you want to run both models, use a single `by` e.g., 
              by(m1, m2, m3) not by(m1).by(m2).by(m3)."""
        )
        return other_model or self

    def rich_print(self):
        """Display an object as a table."""
        from rich.table import Table

        table = Table(title="Language Model")
        table.add_column("Attribute", style="bold")
        table.add_column("Value")

        to_display = self.__dict__.copy()
        for attr_name, attr_value in to_display.items():
            table.add_row(attr_name, repr(attr_value))

        return table

    @classmethod
    def example(
        cls,
        test_model: bool = False,
        canned_response: str = "Hello world",
        throw_exception: bool = False,
    ):
        """Return a default instance of the class.

        >>> from edsl.language_models import LanguageModel
        >>> m = LanguageModel.example(test_model = True, canned_response = "WOWZA!")
        >>> isinstance(m, LanguageModel)
        True
        >>> from edsl import QuestionFreeText
        >>> q = QuestionFreeText(question_text = "What is your name?", question_name = 'example')
        >>> q.by(m).run(cache = False).select('example').first()
        'WOWZA!'
        """
        from edsl import Model

        if test_model:
            m = Model("test", canned_response=canned_response)
            return m
        else:
            return Model(skip_api_key_check=True)


if __name__ == "__main__":
    """Run the module's test suite."""
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
