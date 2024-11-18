# """This module contains the Result class, which captures the result of one interview."""
from __future__ import annotations
from collections import UserDict
from typing import Any, Type, Callable, Optional
from collections import UserDict
from edsl.base.Base import Base
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version


class PromptDict(UserDict):
    """A dictionary that is used to store the prompt for a given result."""

    def rich_print(self):
        """Display an object as a table."""
        from rich.table import Table

        table = Table(title="")
        table.add_column("Attribute", style="bold")
        table.add_column("Value")

        to_display = self
        for attr_name, attr_value in to_display.items():
            table.add_row(attr_name, repr(attr_value))

        return table


def agent_namer_closure():
    """Return a function that can be used to name an agent."""
    agent_dict = {}

    def agent_namer(agent):
        """Return a name for an agent. If the agent has been named before, return the same name. Otherwise, return a new name."""
        nonlocal agent_dict
        agent_count = len(agent_dict)
        if id(agent) in agent_dict:
            return agent_dict[id(agent)]
        else:
            agent_dict[id(agent)] = f"Agent_{agent_count}"
            return agent_dict[id(agent)]

    return agent_namer


agent_namer = agent_namer_closure()


class Result(Base, UserDict):
    """
    This class captures the result of one interview.

    The answer dictionary has the structure:

    >>> import warnings
    >>> warnings.simplefilter("ignore", UserWarning)
    >>> Result.example().answer == {'how_feeling_yesterday': 'Great', 'how_feeling': 'OK'}
    True

    Its main data is an Agent, a Scenario, a Model, an Iteration, and an Answer.
    These are stored both in the UserDict and as attributes.


    """

    def __init__(
        self,
        agent: "Agent",
        scenario: "Scenario",
        model: Type["LanguageModel"],
        iteration: int,
        answer: str,
        prompt: dict[str, str] = None,
        raw_model_response=None,
        survey: Optional["Survey"] = None,
        question_to_attributes: Optional[dict] = None,
        generated_tokens: Optional[dict] = None,
        comments_dict: Optional[dict] = None,
        cache_used_dict: Optional[dict] = None,
    ):
        """Initialize a Result object.

        :param agent: The Agent object.
        :param scenario: The Scenario object.
        :param model: The LanguageModel object.
        :param iteration: The iteration number.
        :param answer: The answer string.
        :param prompt: A dictionary of prompts.
        :param raw_model_response: The raw model response.

        """
        if question_to_attributes is not None:
            question_to_attributes = question_to_attributes
        else:
            question_to_attributes = {}

        if survey is not None:
            question_to_attributes = {
                q.question_name: {
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "question_options": (
                        None
                        if not hasattr(q, "question_options")
                        else q.question_options
                    ),
                }
                for q in survey.questions
            }

        data = {
            "agent": agent,
            "scenario": scenario,
            "model": model,
            "iteration": iteration,
            "answer": answer,
            "prompt": prompt or {},
            "raw_model_response": raw_model_response or {},
            "question_to_attributes": question_to_attributes,
            "generated_tokens": generated_tokens or {},
            "comments_dict": comments_dict or {},
        }
        super().__init__(**data)
        # but also store the data as attributes
        self.agent = agent
        self.scenario = scenario
        self.model = model
        self.iteration = iteration
        self.answer = answer
        self.prompt = prompt or {}
        self.raw_model_response = raw_model_response or {}
        self.survey = survey
        self.question_to_attributes = question_to_attributes
        self.generated_tokens = generated_tokens
        self.comments_dict = comments_dict or {}
        self.cache_used_dict = cache_used_dict or {}

        self._combined_dict = None
        self._problem_keys = None

    ###############
    # Used in Results
    ###############
    @property
    def sub_dicts(self) -> dict[str, dict]:
        """Return a dictionary where keys are strings for each of the main class attributes/objects."""
        if self.agent.name is None:
            agent_name = agent_namer(self.agent)
        else:
            agent_name = self.agent.name

        # comments_dict = {k: v for k, v in self.answer.items() if k.endswith("_comment")}
        question_text_dict = {}
        question_options_dict = {}
        question_type_dict = {}
        for key, _ in self.answer.items():
            if key in self.question_to_attributes:
                # You might be tempted to just use the naked key
                # but this is a bad idea because it pollutes the namespace
                question_text_dict[key + "_question_text"] = (
                    self.question_to_attributes[key]["question_text"]
                )
                question_options_dict[key + "_question_options"] = (
                    self.question_to_attributes[key]["question_options"]
                )
                question_type_dict[key + "_question_type"] = (
                    self.question_to_attributes[key]["question_type"]
                )

        return {
            "agent": self.agent.traits
            | {"agent_name": agent_name}
            | {"agent_instruction": self.agent.instruction},
            "scenario": self.scenario,
            "model": self.model.parameters | {"model": self.model.model},
            "answer": self.answer,
            "prompt": self.prompt,
            "raw_model_response": self.raw_model_response,
            "iteration": {"iteration": self.iteration},
            "question_text": question_text_dict,
            "question_options": question_options_dict,
            "question_type": question_type_dict,
            "comment": self.comments_dict,
            "generated_tokens": self.generated_tokens,
        }

    def check_expression(self, expression) -> None:
        for key in self.problem_keys:
            if key in expression and not key + "." in expression:
                raise ValueError(
                    f"Key by iself {key} is problematic. Use the full key {key + '.' + key} name instead."
                )
        return None

    def code(self):
        """Return a string of code that can be used to recreate the Result object."""
        raise NotImplementedError

    @property
    def problem_keys(self):
        """Return a list of keys that are problematic."""
        return self._problem_keys

    def _compute_combined_dict_and_problem_keys(self) -> None:
        combined = {}
        problem_keys = []
        for key, sub_dict in self.sub_dicts.items():
            combined.update(sub_dict)
            # in some cases, the sub_dict might have keys that conflict with the main dict
            if key in combined:
                # The key is already in the combined dict
                problem_keys = problem_keys + [key]

            combined.update({key: sub_dict})
            # I *think* this allows us to do do things like "answer.how_feelling" i.e., that the evaluator can use
            # dot notation to access the subdicts.
        self._combined_dict = combined
        self._problem_keys = problem_keys

    @property
    def combined_dict(self) -> dict[str, Any]:
        """Return a dictionary that includes all sub_dicts, but also puts the key-value pairs in each sub_dict as a key_value pair in the combined dictionary.

        >>> r = Result.example()
        >>> r.combined_dict['how_feeling']
        'OK'
        """
        if self._combined_dict is None or self._problem_keys is None:
            self._compute_combined_dict_and_problem_keys()
        return self._combined_dict

    @property
    def problem_keys(self):
        """Return a list of keys that are problematic."""
        if self._combined_dict is None or self._problem_keys is None:
            self._compute_combined_dict_and_problem_keys()
        return self._problem_keys

    def get_value(self, data_type: str, key: str) -> Any:
        """Return the value for a given data type and key.

        >>> r = Result.example()
        >>> r.get_value("answer", "how_feeling")
        'OK'

        - data types can be "agent", "scenario", "model", or "answer"
        - keys are relevant attributes of the Objects the data types represent
        """
        return self.sub_dicts[data_type][key]

    @property
    def key_to_data_type(self) -> dict[str, str]:
        """Return a dictionary where keys are object attributes and values are the data type (object) that the attribute is associated with.

        >>> r = Result.example()
        >>> r.key_to_data_type["how_feeling"]
        'answer'

        """
        d = {}
        problem_keys = []
        data_types = sorted(self.sub_dicts.keys())
        for data_type in data_types:
            for key in self.sub_dicts[data_type]:
                if key in d:
                    import warnings

                    warnings.warn(
                        f"Key '{key}' of data type '{data_type}' is already in use. Renaming to {key}_{data_type}"
                    )
                    problem_keys.append((key, data_type))
                    key = f"{key}_{data_type}"
                    # raise ValueError(f"Key '{key}' is already in the dictionary")
                d[key] = data_type

        for key, data_type in problem_keys:
            self.sub_dicts[data_type][f"{key}_{data_type}"] = self.sub_dicts[
                data_type
            ].pop(key)
        return d

    def rows(self, index) -> tuple[int, str, str, str]:
        """Return a generator of rows for the Result object."""
        for data_type, subdict in self.sub_dicts.items():
            for key, value in subdict.items():
                yield (index, data_type, key, str(value))

    def leaves(self):
        leaves = []
        for question_name, answer in self.answer.items():
            if not question_name.endswith("_comment"):
                leaves.append(
                    {
                        "question": f"({question_name}): "
                        + str(
                            self.question_to_attributes[question_name]["question_text"]
                        ),
                        "answer": answer,
                        "comment": self.answer.get(question_name + "_comment", ""),
                        "scenario": repr(self.scenario),
                        "agent": repr(self.agent),
                        "model": repr(self.model),
                        "iteration": self.iteration,
                    }
                )
        return leaves

    ###############
    # Useful
    ###############
    def copy(self) -> Result:
        """Return a copy of the Result object."""
        return Result.from_dict(self.to_dict())

    def __eq__(self, other) -> bool:
        """Return True if the Result object is equal to another Result object.

        >>> r = Result.example()
        >>> r == r
        True

        """
        return self.to_dict() == other.to_dict()

    ###############
    # Serialization
    ###############
    def to_dict(self, add_edsl_version=True) -> dict[str, Any]:
        """Return a dictionary representation of the Result object.

        >>> r = Result.example()
        >>> r.to_dict()['scenario']
        {'period': 'morning', 'edsl_version': '...', 'edsl_class_name': 'Scenario'}
        """

        def convert_value(value, add_edsl_version=True):
            if hasattr(value, "to_dict"):
                return value.to_dict(add_edsl_version=add_edsl_version)
            else:
                return value

        d = {}
        for key, value in self.items():
            d[key] = convert_value(value, add_edsl_version=add_edsl_version)

            if key == "prompt":
                new_prompt_dict = {}
                for prompt_name, prompt_obj in value.items():
                    new_prompt_dict[prompt_name] = (
                        prompt_obj
                        if not hasattr(prompt_obj, "to_dict")
                        else prompt_obj.to_dict()
                    )
                d[key] = new_prompt_dict
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = "Result"

        return d

    def __hash__(self):
        """Return a hash of the Result object."""
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(add_edsl_version=False))

    @classmethod
    @remove_edsl_version
    def from_dict(self, json_dict: dict) -> Result:
        """Return a Result object from a dictionary representation."""

        from edsl import Agent
        from edsl import Scenario
        from edsl.language_models.LanguageModel import LanguageModel
        from edsl.prompts.Prompt import Prompt

        prompt_data = json_dict.get("prompt", {})
        prompt_d = {}
        for prompt_name, prompt_obj in prompt_data.items():
            prompt_d[prompt_name] = Prompt.from_dict(prompt_obj)

        result = Result(
            agent=Agent.from_dict(json_dict["agent"]),
            scenario=Scenario.from_dict(json_dict["scenario"]),
            model=LanguageModel.from_dict(json_dict["model"]),
            iteration=json_dict["iteration"],
            answer=json_dict["answer"],
            prompt=prompt_d,  # json_dict["prompt"],
            raw_model_response=json_dict.get(
                "raw_model_response", {"raw_model_response": "No raw model response"}
            ),
            question_to_attributes=json_dict.get("question_to_attributes", None),
            generated_tokens=json_dict.get("generated_tokens", {}),
            comments_dict=json_dict.get("comments_dict", {}),
        )
        return result

    def rich_print(self) -> None:
        """Display an object as a table."""
        # from edsl.utilities import print_dict_with_rich
        from rich import print
        from rich.table import Table

        table = Table(title="Result")
        table.add_column("Attribute", style="bold")
        table.add_column("Value")

        to_display = self.__dict__.copy()
        data = to_display.pop("data", None)
        for attr_name, attr_value in to_display.items():
            if hasattr(attr_value, "rich_print"):
                table.add_row(attr_name, attr_value.rich_print())
            elif isinstance(attr_value, dict):
                a = PromptDict(attr_value)
                table.add_row(attr_name, a.rich_print())
            else:
                table.add_row(attr_name, repr(attr_value))
        return table

    def __repr__(self):
        """Return a string representation of the Result object."""
        return f"Result(agent={repr(self.agent)}, scenario={repr(self.scenario)}, model={repr(self.model)}, iteration={self.iteration}, answer={repr(self.answer)}, prompt={repr(self.prompt)})"

    @classmethod
    def example(cls):
        """Return an example Result object."""
        from edsl.results.Results import Results

        return Results.example()[0]

    def score(self, scoring_function: Callable) -> Any:
        """Score the result using a passed-in scoring function.

        >>> def f(status): return 1 if status == 'Joyful' else 0
        >>> Result.example().score(f)
        1
        """
        import inspect

        signature = inspect.signature(scoring_function)
        params = {}
        for k, v in signature.parameters.items():
            if k in self.combined_dict:
                params[k] = self.combined_dict[k]
            elif v.default is not v.empty:
                params[k] = v.default
            else:
                raise ValueError(f"Parameter {k} not found in Result object")
        return scoring_function(**params)


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
