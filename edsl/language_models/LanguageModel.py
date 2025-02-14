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
import os
from typing import (
    Coroutine,
    Any,
    Type,
    Union,
    List,
    get_type_hints,
    TypedDict,
    Optional,
    TYPE_CHECKING,
)
from abc import ABC, abstractmethod

from edsl.data_transfer_models import (
    ModelResponse,
    ModelInputs,
    EDSLOutput,
    AgentResponseDict,
)

if TYPE_CHECKING:
    from edsl.data.Cache import Cache
    from edsl.scenarios.FileStore import FileStore
    from edsl.questions.QuestionBase import QuestionBase
    from edsl.language_models.key_management.KeyLookup import KeyLookup

from edsl.enums import InferenceServiceType

from edsl.utilities.decorators import (
    sync_wrapper,
    jupyter_nb_handler,
)
from edsl.utilities.remove_edsl_version import remove_edsl_version

from edsl.Base import PersistenceMixin, RepresentationMixin
from edsl.language_models.RegisterLanguageModelsMeta import RegisterLanguageModelsMeta

from edsl.language_models.key_management.KeyLookupCollection import (
    KeyLookupCollection,
)

from edsl.language_models.RawResponseHandler import RawResponseHandler


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


class classproperty:
    def __init__(self, method):
        self.method = method

    def __get__(self, instance, cls):
        return self.method(cls)


from edsl.Base import HashingMixin


class LanguageModel(
    PersistenceMixin,
    RepresentationMixin,
    HashingMixin,
    ABC,
    metaclass=RegisterLanguageModelsMeta,
):
    """ABC for Language Models."""

    _model_ = None
    key_sequence = (
        None  # This should be something like ["choices", 0, "message", "content"]
    )

    DEFAULT_RPM = 100
    DEFAULT_TPM = 1000

    @classproperty
    def response_handler(cls):
        key_sequence = cls.key_sequence
        usage_sequence = cls.usage_sequence if hasattr(cls, "usage_sequence") else None
        return RawResponseHandler(key_sequence, usage_sequence)

    def __init__(
        self,
        tpm: Optional[float] = None,
        rpm: Optional[float] = None,
        omit_system_prompt_if_empty_string: bool = True,
        key_lookup: Optional["KeyLookup"] = None,
        **kwargs,
    ):
        """Initialize the LanguageModel."""
        self.model = getattr(self, "_model_", None)
        default_parameters = getattr(self, "_parameters_", None)
        parameters = self._overide_default_parameters(kwargs, default_parameters)
        self.parameters = parameters
        self.remote = False
        self.omit_system_prompt_if_empty = omit_system_prompt_if_empty_string

        self.key_lookup = self._set_key_lookup(key_lookup)
        self.model_info = self.key_lookup.get(self._inference_service_)

        if rpm is not None:
            self._rpm = rpm

        if tpm is not None:
            self._tpm = tpm

        for key, value in parameters.items():
            setattr(self, key, value)

        for key, value in kwargs.items():
            if key not in parameters:
                setattr(self, key, value)

        if kwargs.get("skip_api_key_check", False):
            # Skip the API key check. Sometimes this is useful for testing.
            self._api_token = None

    def _set_key_lookup(self, key_lookup: "KeyLookup") -> "KeyLookup":
        """Set the key lookup."""
        if key_lookup is not None:
            return key_lookup
        else:
            klc = KeyLookupCollection()
            klc.add_key_lookup(fetch_order=("config", "env"))
            return klc.get(("config", "env"))

    def set_key_lookup(self, key_lookup: "KeyLookup") -> None:
        """Set the key lookup, later"""
        if hasattr(self, "_api_token"):
            del self._api_token
        self.key_lookup = key_lookup

    def ask_question(self, question: "QuestionBase") -> str:
        """Ask a question and return the response.

        :param question: The question to ask.
        """
        user_prompt = question.get_instructions().render(question.data).text
        system_prompt = "You are a helpful agent pretending to be a human."
        return self.execute_model_call(user_prompt, system_prompt)

    @property
    def rpm(self):
        if not hasattr(self, "_rpm"):
            if self.model_info is None:
                self._rpm = self.DEFAULT_RPM
            else:
                self._rpm = self.model_info.rpm
        return self._rpm

    @property
    def tpm(self):
        if not hasattr(self, "_tpm"):
            if self.model_info is None:
                self._tpm = self.DEFAULT_TPM
            else:
                self._tpm = self.model_info.tpm
        return self._tpm

    # in case we want to override the default values
    @tpm.setter
    def tpm(self, value):
        self._tpm = value

    @rpm.setter
    def rpm(self, value):
        self._rpm = value

    @property
    def api_token(self) -> str:
        if not hasattr(self, "_api_token"):
            info = self.key_lookup.get(self._inference_service_, None)
            if info is None:
                raise ValueError(
                    f"No key found for service '{self._inference_service_}'"
                )
            self._api_token = info.api_token
        return self._api_token

    def __getitem__(self, key):
        return getattr(self, key)

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

        if self._model_ == "test":
            return True

        key_name = service_to_api_keyname.get(self._inference_service_, "NOT FOUND")
        key_value = os.getenv(key_name)
        return key_value is not None

    def __hash__(self) -> str:
        """Allow the model to be used as a key in a dictionary.

        >>> m = LanguageModel.example()
        >>> hash(m)
        325654563661254408
        """
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(add_edsl_version=False))

    def __eq__(self, other) -> bool:
        """Check is two models are the same.

        >>> m1 = LanguageModel.example()
        >>> m2 = LanguageModel.example()
        >>> m1 == m2
        True

        """
        return self.model == other.model and self.parameters == other.parameters

    @staticmethod
    def _overide_default_parameters(passed_parameter_dict, default_parameter_dict):
        """Return a dictionary of parameters, with passed parameters taking precedence over defaults.

        >>> LanguageModel._overide_default_parameters(passed_parameter_dict={"temperature": 0.5}, default_parameter_dict={"temperature":0.9})
        {'temperature': 0.5}
        >>> LanguageModel._overide_default_parameters(passed_parameter_dict={"temperature": 0.5}, default_parameter_dict={"temperature":0.9, "max_tokens": 1000})
        {'temperature': 0.5, 'max_tokens': 1000}
        """
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
        """Execute the model call and returns a coroutine."""
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
        """Execute the model call and returns the result as a coroutine."""

        async def main():
            results = await asyncio.gather(
                self.async_execute_model_call(*args, **kwargs)
            )
            return results[0]  # Since there's only one task, return its result

        return main()

    @classmethod
    def get_generated_token_string(cls, raw_response: dict[str, Any]) -> str:
        """Return the generated token string from the raw response.

        >>> m = LanguageModel.example(test_model = True)
        >>> raw_response = m.execute_model_call("Hello, model!", "You are a helpful agent.")
        >>> m.get_generated_token_string(raw_response)
        'Hello world'

        """
        return cls.response_handler.get_generated_token_string(raw_response)

    @classmethod
    def get_usage_dict(cls, raw_response: dict[str, Any]) -> dict[str, Any]:
        """Return the usage dictionary from the raw response."""
        return cls.response_handler.get_usage_dict(raw_response)

    @classmethod
    def parse_response(cls, raw_response: dict[str, Any]) -> EDSLOutput:
        """Parses the API response and returns the response text."""
        return cls.response_handler.parse_response(raw_response)

    async def _async_get_intended_model_call_outcome(
        self,
        user_prompt: str,
        system_prompt: str,
        cache: Cache,
        iteration: int = 0,
        files_list: Optional[List[FileStore]] = None,
        invigilator=None,
    ) -> ModelResponse:
        """Handle caching of responses.

        :param user_prompt: The user's prompt.
        :param system_prompt: The system's prompt.
        :param iteration: The iteration number.
        :param cache: The cache to use.
        :param files_list: The list of files to use.
        :param invigilator: The invigilator to use.

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
                "files_list": files_list,
            }
            from edsl.config import CONFIG

            TIMEOUT = float(CONFIG.get("EDSL_API_TIMEOUT"))

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

    def simple_ask(
        self,
        question: QuestionBase,
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
        cache: Cache,
        iteration: int = 1,
        files_list: Optional[List[FileStore]] = None,
        **kwargs,
    ) -> dict:
        """Get response, parse, and return as string.

        :param user_prompt: The user's prompt.
        :param system_prompt: The system's prompt.
        :param cache: The cache to use.
        :param iteration: The iteration number.
        :param files_list: The list of files to use.

        """
        params = {
            "user_prompt": user_prompt,
            "system_prompt": system_prompt,
            "iteration": iteration,
            "cache": cache,
            "files_list": files_list,
        }
        if "invigilator" in kwargs:
            params.update({"invigilator": kwargs["invigilator"]})

        model_inputs = ModelInputs(user_prompt=user_prompt, system_prompt=system_prompt)
        model_outputs: ModelResponse = (
            await self._async_get_intended_model_call_outcome(**params)
        )
        edsl_dict: EDSLOutput = self.parse_response(model_outputs.response)

        agent_response_dict = AgentResponseDict(
            model_inputs=model_inputs,
            model_outputs=model_outputs,
            edsl_dict=edsl_dict,
        )
        return agent_response_dict

    get_response = sync_wrapper(async_get_response)

    def cost(self, raw_response: dict[str, Any]) -> Union[float, str]:
        """Return the dollar cost of a raw response.

        :param raw_response: The raw response from the model.
        """

        usage = self.get_usage_dict(raw_response)
        from edsl.language_models.PriceManager import PriceManager

        price_manger = PriceManager()
        return price_manger.calculate_cost(
            inference_service=self._inference_service_,
            model=self.model,
            usage=usage,
            input_token_name=self.input_token_name,
            output_token_name=self.output_token_name,
        )

    def to_dict(self, add_edsl_version: bool = True) -> dict[str, Any]:
        """Convert instance to a dictionary

        :param add_edsl_version: Whether to add the EDSL version to the dictionary.

        >>> m = LanguageModel.example()
        >>> m.to_dict()
        {'model': '...', 'parameters': {'temperature': ..., 'max_tokens': ..., 'top_p': ..., 'frequency_penalty': ..., 'presence_penalty': ..., 'logprobs': False, 'top_logprobs': ...}, 'inference_service': 'openai', 'edsl_version': '...', 'edsl_class_name': 'LanguageModel'}
        """
        d = {
            "model": self.model,
            "parameters": self.parameters,
            "inference_service": self._inference_service_,
        }
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = self.__class__.__name__
        return d

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict) -> Type[LanguageModel]:
        """Convert dictionary to a LanguageModel child instance.

        NB: This method does not use the stores inference_service but rather just fetches a model class based on the name.
        """
        from edsl.language_models.model import get_model_class

        # breakpoint()

        model_class = get_model_class(
            data["model"], service_name=data.get("inference_service", None)
        )
        return model_class(**data)

    def __repr__(self) -> str:
        """Return a representation of the object."""
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
        import warnings

        warnings.warn(
            f"""Warning: one model is replacing another. If you want to run both models, use a single `by` e.g., 
              by(m1, m2, m3) not by(m1).by(m2).by(m3)."""
        )
        return other_model or self

    @classmethod
    def example(
        cls,
        test_model: bool = False,
        canned_response: str = "Hello world",
        throw_exception: bool = False,
    ) -> LanguageModel:
        """Return a default instance of the class.

        >>> from edsl.language_models import LanguageModel
        >>> m = LanguageModel.example(test_model = True, canned_response = "WOWZA!")
        >>> isinstance(m, LanguageModel)
        True
        >>> from edsl import QuestionFreeText
        >>> q = QuestionFreeText(question_text = "What is your name?", question_name = 'example')
        >>> q.by(m).run(cache = False, disable_remote_cache = True, disable_remote_inference = True).select('example').first()
        'WOWZA!'
        >>> m = LanguageModel.example(test_model = True, canned_response = "WOWZA!", throw_exception = True)
        >>> r = q.by(m).run(cache = False, disable_remote_cache = True, disable_remote_inference = True, print_exceptions = True)
        Exception report saved to ...
        """
        from edsl.language_models.model import Model

        if test_model:
            m = Model(
                "test", canned_response=canned_response, throw_exception=throw_exception
            )
            return m
        else:
            return Model(skip_api_key_check=True)

    def from_cache(self, cache: "Cache") -> LanguageModel:
        from copy import deepcopy
        from types import MethodType
        from edsl import Cache

        new_instance = deepcopy(self)
        print("Cache entries", len(cache))
        new_instance.cache = Cache(
            data={k: v for k, v in cache.items() if v.model == self.model}
        )
        print("Cache entries with same model", len(new_instance.cache))

        new_instance.user_prompts = [
            ce.user_prompt for ce in new_instance.cache.values()
        ]
        new_instance.system_prompts = [
            ce.system_prompt for ce in new_instance.cache.values()
        ]

        async def async_execute_model_call(self, user_prompt: str, system_prompt: str):
            cache_call_params = {
                "model": str(self.model),
                "parameters": self.parameters,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "iteration": 1,
            }
            cached_response, cache_key = cache.fetch(**cache_call_params)
            response = json.loads(cached_response)
            cost = 0
            return ModelResponse(
                response=response,
                cache_used=True,
                cache_key=cache_key,
                cached_response=cached_response,
                cost=cost,
            )

        # Bind the new method to the copied instance
        setattr(
            new_instance,
            "async_execute_model_call",
            MethodType(async_execute_model_call, new_instance),
        )

        return new_instance


if __name__ == "__main__":
    """Run the module's test suite."""
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
