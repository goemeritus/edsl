"""An Agent is an AI agent that can reference a set of traits in answering questions."""

from __future__ import annotations
import copy
import inspect
import types
from typing import Callable, Optional, Union, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from edsl import Cache, Survey, Scenario
    from edsl.language_models import LanguageModel
    from edsl.surveys.MemoryPlan import MemoryPlan
    from edsl.questions import QuestionBase
    from edsl.agents.Invigilator import InvigilatorBase

from uuid import uuid4

from edsl.base.Base import Base
from edsl.prompts import Prompt
from edsl.exceptions import QuestionScenarioRenderError

from edsl.exceptions.agents import (
    AgentErrors,
    AgentCombinationError,
    AgentDirectAnswerFunctionError,
    AgentDynamicTraitsFunctionError,
)

from edsl.agents.descriptors import (
    TraitsDescriptor,
    CodebookDescriptor,
    InstructionDescriptor,
    NameDescriptor,
)
from edsl.utilities.decorators import (
    sync_wrapper,
    add_edsl_version,
    remove_edsl_version,
)
from edsl.data_transfer_models import AgentResponseDict
from edsl.utilities.restricted_python import create_restricted_function


class Agent(Base):
    """An class representing an agent that can answer questions."""

    __doc__ = "https://docs.expectedparrot.com/en/latest/agents.html"

    default_instruction = """You are answering questions as if you were a human. Do not break character."""

    _traits = TraitsDescriptor()
    codebook = CodebookDescriptor()
    instruction = InstructionDescriptor()
    name = NameDescriptor()
    dynamic_traits_function_name = ""
    answer_question_directly_function_name = ""
    has_dynamic_traits_function = False

    def __init__(
        self,
        traits: Optional[dict] = None,
        name: Optional[str] = None,
        codebook: Optional[dict] = None,
        instruction: Optional[str] = None,
        traits_presentation_template: Optional[str] = None,
        dynamic_traits_function: Optional[Callable] = None,
        dynamic_traits_function_source_code: Optional[str] = None,
        dynamic_traits_function_name: Optional[str] = None,
        answer_question_directly_source_code: Optional[str] = None,
        answer_question_directly_function_name: Optional[str] = None,
    ):
        """Initialize a new instance of Agent.

        :param traits: A dictionary of traits that the agent has. The keys need to be valid identifiers.
        :param name: A name for the agent
        :param codebook: A codebook mapping trait keys to trait descriptions.
        :param instruction: Instructions for the agent in how to answer questions.
        :param trait_presentation_template: A template for how to present the agent's traits.
        :param dynamic_traits_function: A function that returns a dictionary of traits.

        The `traits` parameter is a dictionary of traits that the agent has.
        These traits are used to construct a prompt that is presented to the LLM.
        In the absence of a `traits_presentation_template`, the default is used.
        This is a template that is used to present the agent's traits to the LLM.
        See :py:class:`edsl.prompts.library.agent_persona.AgentPersona` for more information.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.traits
        {'age': 10, 'hair': 'brown', 'height': 5.5}

        These traits are used to construct a prompt that is presented to the LLM.

        In the absence of a `traits_presentation_template`, the default is used.

        >>> a = Agent(traits = {"age": 10}, traits_presentation_template = "I am a {{age}} year old.")
        >>> repr(a.agent_persona)
        'Prompt(text=\"""I am a {{age}} year old.\""")'

        When this is rendered for presentation to the LLM, it will replace the `{{age}}` with the actual age.
        it is also possible to use the `codebook` to provide a more human-readable description of the trait.
        Here is an example where we give a prefix to the age trait (namely the age):

        >>> traits = {"age": 10, "hair": "brown", "height": 5.5}
        >>> codebook = {'age': 'Their age is'}
        >>> a = Agent(traits = traits, codebook = codebook, traits_presentation_template = "This agent is Dave. {{codebook['age']}} {{age}}")
        >>> d = a.traits | {'codebook': a.codebook}
        >>> a.agent_persona.render(d)
        Prompt(text=\"""This agent is Dave. Their age is 10\""")

        Instructions
        ------------
        The agent can also have instructions. These are instructions that are given to the agent when answering questions.

        >>> Agent.default_instruction
        'You are answering questions as if you were a human. Do not break character.'

        See see how these are used to actually construct the prompt that is presented to the LLM, see :py:class:`edsl.agents.Invigilator.InvigilatorBase`.

        """
        self.name = name
        self._traits = traits or dict()
        self.codebook = codebook or dict()
        if instruction is None:
            self.instruction = self.default_instruction
        else:
            self.instruction = instruction
        # self.instruction = instruction or self.default_instruction
        self.dynamic_traits_function = dynamic_traits_function

        # Deal with dynamic traits function
        if self.dynamic_traits_function:
            self.dynamic_traits_function_name = self.dynamic_traits_function.__name__
            self.has_dynamic_traits_function = True
        else:
            self.has_dynamic_traits_function = False

        if dynamic_traits_function_source_code:
            self.dynamic_traits_function_name = dynamic_traits_function_name
            self.dynamic_traits_function = create_restricted_function(
                dynamic_traits_function_name, dynamic_traits_function
            )

        # Deal with direct answer function
        if answer_question_directly_source_code:
            self.answer_question_directly_function_name = (
                answer_question_directly_function_name
            )
            protected_method = create_restricted_function(
                answer_question_directly_function_name,
                answer_question_directly_source_code,
            )
            bound_method = types.MethodType(protected_method, self)
            setattr(self, "answer_question_directly", bound_method)

        self._check_dynamic_traits_function()

        self.current_question = None

        if traits_presentation_template is not None:
            self._traits_presentation_template = traits_presentation_template
            self.traits_presentation_template = traits_presentation_template
        else:
            self.traits_presentation_template = "Your traits: {{traits}}"

    @property
    def agent_persona(self) -> Prompt:
        return Prompt(text=self.traits_presentation_template)

    def prompt(self) -> str:
        """Return the prompt for the agent.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.prompt()
        Prompt(text=\"""Your traits: {'age': 10, 'hair': 'brown', 'height': 5.5}\""")
        """
        replacement_dict = (
            self.traits | {"traits": self.traits} | {"codebook": self.codebook}
        )
        if undefined := self.agent_persona.undefined_template_variables(
            replacement_dict
        ):
            raise QuestionScenarioRenderError(
                f"Agent persona still has variables that were not rendered: {undefined}"
            )
        else:
            return self.agent_persona.render(replacement_dict)

    def _check_dynamic_traits_function(self) -> None:
        """Check whether dynamic trait function is valid.

        This checks whether the dynamic traits function is valid.

        >>> def f(question): return {"age": 10, "hair": "brown", "height": 5.5}
        >>> a = Agent(dynamic_traits_function = f)
        >>> a._check_dynamic_traits_function()

        >>> def g(question, poo): return {"age": 10, "hair": "brown", "height": 5.5}
        >>> a = Agent(dynamic_traits_function = g)
        Traceback (most recent call last):
        ...
        edsl.exceptions.agents.AgentDynamicTraitsFunctionError: ...
        """
        if self.has_dynamic_traits_function:
            sig = inspect.signature(self.dynamic_traits_function)
            if "question" in sig.parameters:
                if len(sig.parameters) > 1:
                    raise AgentDynamicTraitsFunctionError(
                        message=f"The dynamic traits function {self.dynamic_traits_function} has too many parameters. It should only have one parameter: 'question'."
                    )
            else:
                if len(sig.parameters) > 0:
                    raise AgentDynamicTraitsFunctionError(
                        f"""The dynamic traits function {self.dynamic_traits_function} has too many parameters. It should have no parameters or 
                        just a single parameter: 'question'."""
                    )

    @property
    def traits(self) -> dict[str, str]:
        """An agent's traits, which is a dictionary.

        The agent could have a a dynamic traits function (`dynamic_traits_function`) that returns a dictionary of traits
        when called. This function can also take a `question` as an argument.
        If so, the dynamic traits function is called and the result is returned.
        Otherwise, the traits are returned.

        Example:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.traits
        {'age': 10, 'hair': 'brown', 'height': 5.5}

        """
        if self.has_dynamic_traits_function:
            sig = inspect.signature(self.dynamic_traits_function)
            if "question" in sig.parameters:
                return self.dynamic_traits_function(question=self.current_question)
            else:
                return self.dynamic_traits_function()
        else:
            return self._traits

    def rename(
        self, old_name_or_dict: Union[str, dict], new_name: Optional[str] = None
    ) -> Agent:
        """Rename a trait.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.rename("age", "years") == Agent(traits = {'years': 10, 'hair': 'brown', 'height': 5.5})
        True

        >>> a.rename({'years': 'smage'})
        Agent(traits = {'hair': 'brown', 'height': 5.5, 'smage': 10})

        """
        if isinstance(old_name_or_dict, dict) and new_name is None:
            for old_name, new_name in old_name_or_dict.items():
                self = self._rename(old_name, new_name)
            return self

        if isinstance(old_name_or_dict, dict) and new_name:
            raise AgentErrors(
                f"You passed a dict: {old_name_or_dict} and a new name: {new_name}. You should pass only a dict."
            )

        if isinstance(old_name_or_dict, str):
            self._rename(old_name_or_dict, new_name)
            return self

        raise AgentErrors("Something is not right with Agent renaming")

    def _rename(self, old_name: str, new_name: str) -> Agent:
        """Rename a trait.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.rename("age", "years") == Agent(traits = {'years': 10, 'hair': 'brown', 'height': 5.5})
        True
        """
        self.traits[new_name] = self.traits.pop(old_name)
        return self

    def __getitem__(self, key):
        """Allow for accessing traits using the bracket notation.

        Example:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a['traits']['age']
        10

        """
        return getattr(self, key)

    def remove_direct_question_answering_method(self) -> None:
        """Remove the direct question answering method.

        Example usage:

        >>> a = Agent()
        >>> def f(self, question, scenario): return "I am a direct answer."
        >>> a.add_direct_question_answering_method(f)
        >>> a.remove_direct_question_answering_method()
        >>> hasattr(a, "answer_question_directly")
        False
        """
        if hasattr(self, "answer_question_directly"):
            delattr(self, "answer_question_directly")

    def add_direct_question_answering_method(
        self,
        method: Callable,
        validate_response: bool = False,
        translate_response: bool = False,
    ) -> None:
        """Add a method to the agent that can answer a particular question type.
        https://docs.expectedparrot.com/en/latest/agents.html#agent-direct-answering-methods

        :param method: A method that can answer a question directly.
        :param validate_response: Whether to validate the response.
        :param translate_response: Whether to translate the response.

        Example usage:

        >>> a = Agent()
        >>> def f(self, question, scenario): return "I am a direct answer."
        >>> a.add_direct_question_answering_method(f)
        >>> a.answer_question_directly(question = None, scenario = None)
        'I am a direct answer.'
        """
        if hasattr(self, "answer_question_directly"):
            import warnings

            warnings.warn(
                "Warning: overwriting existing answer_question_directly method"
            )

        self.validate_response = validate_response
        self.translate_response = translate_response

        signature = inspect.signature(method)
        for argument in ["question", "scenario", "self"]:
            if argument not in signature.parameters:
                raise AgentDirectAnswerFunctionError(
                    f"The method {method} does not have a '{argument}' parameter."
                )
        bound_method = types.MethodType(method, self)
        setattr(self, "answer_question_directly", bound_method)
        self.answer_question_directly_function_name = bound_method.__name__

    def create_invigilator(
        self,
        *,
        question: "QuestionBase",
        cache: "Cache",
        survey: Optional["Survey"] = None,
        scenario: Optional["Scenario"] = None,
        model: Optional["LanguageModel"] = None,
        debug: bool = False,
        memory_plan: Optional["MemoryPlan"] = None,
        current_answers: Optional[dict] = None,
        iteration: int = 1,
        sidecar_model=None,
        raise_validation_errors: bool = True,
    ) -> "InvigilatorBase":
        """Create an Invigilator.

        An invigilator is an object that is responsible for administering a question to an agent.
        There are several different types of invigilators, depending on the type of question and the agent.
        For example, there are invigilators for functional questions (i.e., question is of type :class:`edsl.questions.QuestionFunctional`:), for direct questions, and for LLM questions.

        >>> a = Agent(traits = {})
        >>> a.create_invigilator(question = None, cache = False)
        InvigilatorAI(...)

        An invigator is an object that is responsible for administering a question to an agent and
        recording the responses.
        """
        from edsl import Model, Scenario

        cache = cache
        self.current_question = question
        model = model or Model()
        scenario = scenario or Scenario()
        invigilator = self._create_invigilator(
            question=question,
            scenario=scenario,
            survey=survey,
            model=model,
            debug=debug,
            memory_plan=memory_plan,
            current_answers=current_answers,
            iteration=iteration,
            cache=cache,
            sidecar_model=sidecar_model,
            raise_validation_errors=raise_validation_errors,
        )
        if hasattr(self, "validate_response"):
            invigilator.validate_response = self.validate_response
        if hasattr(self, "translate_response"):
            invigilator.translate_response = self.translate_response
        return invigilator

    async def async_answer_question(
        self,
        *,
        question: QuestionBase,
        cache: Cache,
        scenario: Optional[Scenario] = None,
        survey: Optional[Survey] = None,
        model: Optional[LanguageModel] = None,
        debug: bool = False,
        memory_plan: Optional[MemoryPlan] = None,
        current_answers: Optional[dict] = None,
        iteration: int = 0,
    ) -> AgentResponseDict:
        """
        Answer a posed question.

        :param question: The question to answer.
        :param scenario: The scenario in which the question is asked.
        :param model: The language model to use.
        :param debug: Whether to run in debug mode.
        :param memory_plan: The memory plan to use.
        :param current_answers: The current answers.
        :param iteration: The iteration number.

        >>> a = Agent(traits = {})
        >>> a.add_direct_question_answering_method(lambda self, question, scenario: "I am a direct answer.")
        >>> from edsl import QuestionFreeText
        >>> q = QuestionFreeText.example()
        >>> a.answer_question(question = q, cache = False).answer
        'I am a direct answer.'

        This is a function where an agent returns an answer to a particular question.
        However, there are several different ways an agent can answer a question, so the
        actual functionality is delegated to an :class:`edsl.agents.InvigilatorBase`: object.
        """
        invigilator = self.create_invigilator(
            question=question,
            cache=cache,
            scenario=scenario,
            survey=survey,
            model=model,
            debug=debug,
            memory_plan=memory_plan,
            current_answers=current_answers,
            iteration=iteration,
        )
        response: AgentResponseDict = await invigilator.async_answer_question()
        return response

    answer_question = sync_wrapper(async_answer_question)

    def _create_invigilator(
        self,
        question: QuestionBase,
        cache: Optional[Cache] = None,
        scenario: Optional[Scenario] = None,
        model: Optional[LanguageModel] = None,
        survey: Optional[Survey] = None,
        debug: bool = False,
        memory_plan: Optional[MemoryPlan] = None,
        current_answers: Optional[dict] = None,
        iteration: int = 0,
        sidecar_model=None,
        raise_validation_errors: bool = True,
    ) -> "InvigilatorBase":
        """Create an Invigilator."""
        from edsl import Model
        from edsl import Scenario

        model = model or Model()
        scenario = scenario or Scenario()

        from edsl.agents.Invigilator import (
            InvigilatorHuman,
            InvigilatorFunctional,
            InvigilatorAI,
            InvigilatorBase,
        )

        if cache is None:
            from edsl.data.Cache import Cache

            cache = Cache()

        if debug:
            raise NotImplementedError("Debug mode is not yet implemented.")
            # use the question's _simulate_answer method
            # invigilator_class = InvigilatorDebug
        elif hasattr(question, "answer_question_directly"):
            # It's a functional question and the answer only depends on the agent's traits & the scenario
            invigilator_class = InvigilatorFunctional
        elif hasattr(self, "answer_question_directly"):
            # this of the case where the agent has a method that can answer the question directly
            # this occurrs when 'answer_question_directly' has been given to the
            # which happens when the agent is created from an existing survey
            invigilator_class = InvigilatorHuman
        else:
            # this means an LLM agent will be used. This is the standard case.
            invigilator_class = InvigilatorAI

        if sidecar_model is not None:
            # this is the case when a 'simple' model is being used
            from edsl.agents.Invigilator import InvigilatorSidecar

            invigilator_class = InvigilatorSidecar

        invigilator = invigilator_class(
            self,
            question=question,
            scenario=scenario,
            survey=survey,
            model=model,
            memory_plan=memory_plan,
            current_answers=current_answers,
            iteration=iteration,
            cache=cache,
            sidecar_model=sidecar_model,
            raise_validation_errors=raise_validation_errors,
        )
        return invigilator

    def select(self, *traits: str) -> Agent:
        """Selects agents with only the references traits

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})


        >>> a.select("age", "height")
        Agent(traits = {'age': 10, 'height': 5.5})

        >>> a.select("age")
        Agent(traits = {'age': 10})

        """

        if len(traits) == 1:
            traits_to_select = [list(traits)[0]]
        else:
            traits_to_select = list(traits)

        return Agent(traits={trait: self.traits[trait] for trait in traits_to_select})

    def __add__(self, other_agent: Optional[Agent] = None) -> Agent:
        """
        Combine two agents by joining their traits.

        The agents must not have overlapping traits.

        Example usage:

        >>> a1 = Agent(traits = {"age": 10})
        >>> a2 = Agent(traits = {"height": 5.5})
        >>> a1 + a2
        Agent(traits = {'age': 10, 'height': 5.5})
        >>> a1 + a1
        Traceback (most recent call last):
        ...
        edsl.exceptions.agents.AgentCombinationError: The agents have overlapping traits: {'age'}.
        ...
        """
        if other_agent is None:
            return self
        elif common_traits := set(self.traits.keys()) & set(other_agent.traits.keys()):
            raise AgentCombinationError(
                f"The agents have overlapping traits: {common_traits}."
            )
        else:
            new_agent = Agent(traits=copy.deepcopy(self.traits))
            new_agent.traits.update(other_agent.traits)
            return new_agent

    def __eq__(self, other: Agent) -> bool:
        """Check if two agents are equal.

        This only checks the traits.
        >>> a1 = Agent(traits = {"age": 10})
        >>> a2 = Agent(traits = {"age": 10})
        >>> a1 == a2
        True
        >>> a3 = Agent(traits = {"age": 11})
        >>> a1 == a3
        False
        """
        return self.data == other.data

    def __getattr__(self, name):
        # This will be called only if 'name' is not found in the usual places
        if name == "has_dynamic_traits_function":
            return self.has_dynamic_traits_function

        if name in self._traits:
            return self._traits[name]

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __getstate__(self):
        state = self.__dict__.copy()
        # Include any additional state that needs to be serialized
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # Ensure _traits is initialized if it's missing
        if "_traits" not in self.__dict__:
            self._traits = {}

    def print(self) -> None:
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __repr__(self) -> str:
        """Return representation of Agent."""
        class_name = self.__class__.__name__
        items = [
            f'{k} = """{v}"""' if isinstance(v, str) else f"{k} = {v}"
            for k, v in self.data.items()
            if k != "question_type"
        ]
        return f"{class_name}({', '.join(items)})"

    def _repr_html_(self):
        from edsl.utilities.utilities import data_to_html

        return data_to_html(self.to_dict())

    #######################
    # SERIALIZATION METHODS
    #######################
    @property
    def data(self) -> dict:
        """Format the data for serialization.

        TODO: Warn if has dynamic traits function or direct answer function that cannot be serialized.
        TODO: Add ability to have coop-hosted functions that are serializable.
        """

        raw_data = {
            k.replace("_", "", 1): v
            for k, v in self.__dict__.items()
            if k.startswith("_")
        }

        if hasattr(self, "set_instructions"):
            if not self.set_instructions:
                raw_data.pop("instruction")
        if self.codebook == {}:
            raw_data.pop("codebook")
        if self.name == None:
            raw_data.pop("name")

        if hasattr(self, "dynamic_traits_function"):
            raw_data.pop(
                "dynamic_traits_function", None
            )  # in case dynamic_traits_function will appear with _ in self.__dict__
            dynamic_traits_func = self.dynamic_traits_function
            if dynamic_traits_func:
                func = inspect.getsource(dynamic_traits_func)
                raw_data["dynamic_traits_function_source_code"] = func
                raw_data["dynamic_traits_function_name"] = (
                    self.dynamic_traits_function_name
                )
        if hasattr(self, "answer_question_directly"):
            raw_data.pop(
                "answer_question_directly", None
            )  # in case answer_question_directly will appear with _ in self.__dict__
            answer_question_directly_func = self.answer_question_directly

            if (
                answer_question_directly_func
                and raw_data.get("answer_question_directly_source_code", None) != None
            ):
                raw_data["answer_question_directly_source_code"] = inspect.getsource(
                    answer_question_directly_func
                )
                raw_data["answer_question_directly_function_name"] = (
                    self.answer_question_directly_function_name
                )

        return raw_data

    def __hash__(self) -> int:
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(add_edsl_version=False))

    # @add_edsl_version
    def to_dict(self, add_edsl_version=True) -> dict[str, Union[dict, bool]]:
        """Serialize to a dictionary with EDSL info.

        Example usage:

        >>> a = Agent(name = "Steve", traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.to_dict()
        {'name': 'Steve', 'traits': {'age': 10, 'hair': 'brown', 'height': 5.5}, 'edsl_version': '...', 'edsl_class_name': 'Agent'}
        """
        d = copy.deepcopy(self.data)
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = self.__class__.__name__

        return d

    @classmethod
    @remove_edsl_version
    def from_dict(cls, agent_dict: dict[str, Union[dict, bool]]) -> Agent:
        """Deserialize from a dictionary.

        Example usage:

        >>> Agent.from_dict({'name': "Steve", 'traits': {'age': 10, 'hair': 'brown', 'height': 5.5}})
        Agent(name = \"""Steve\""", traits = {'age': 10, 'hair': 'brown', 'height': 5.5})

        """
        return cls(**agent_dict)

    def _table(self) -> tuple[dict, list]:
        """Prepare generic table data."""
        table_data = []
        for attr_name, attr_value in self.__dict__.items():
            table_data.append({"Attribute": attr_name, "Value": repr(attr_value)})
        column_names = ["Attribute", "Value"]
        return table_data, column_names

    def add_trait(self, trait_name_or_dict: str, value: Optional[Any] = None) -> Agent:
        """Adds a trait to an agent and returns that agent"""
        if isinstance(trait_name_or_dict, dict) and value is None:
            self.traits.update(trait_name_or_dict)
            return self

        if isinstance(trait_name_or_dict, dict) and value:
            raise AgentErrors(
                f"You passed a dict: {trait_name_or_dict} and a value: {value}. You should pass only a dict."
            )

        if isinstance(trait_name_or_dict, str):
            trait = trait_name_or_dict
            self.traits[trait] = value
            return self

        raise AgentErrors("Something is not right with adding a trait to an Agent")

    def remove_trait(self, trait: str) -> Agent:
        """Remove a trait from the agent.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.remove_trait("age")
        Agent(traits = {'hair': 'brown', 'height': 5.5})
        """
        _ = self.traits.pop(trait)
        return self

    def translate_traits(self, values_codebook: dict) -> Agent:
        """Translate traits to a new codebook.

        >>> a = Agent(traits = {"age": 10, "hair": 1, "height": 5.5})
        >>> a.translate_traits({"hair": {1:"brown"}})
        Agent(traits = {'age': 10, 'hair': 'brown', 'height': 5.5})

        :param values_codebook: The new codebook.
        """
        for key, value in self.traits.items():
            if key in values_codebook:
                self.traits[key] = values_codebook[key][value]
        return self

    def rich_print(self):
        """Display an object as a rich table.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> a.rich_print()
        <rich.table.Table object at ...>
        """
        from rich.table import Table

        table_data, column_names = self._table()
        table = Table(title=f"{self.__class__.__name__} Attributes")
        for column in column_names:
            table.add_column(column, style="bold")

        for row in table_data:
            row_data = [row[column] for column in column_names]
            table.add_row(*row_data)

        return table

    @classmethod
    def example(cls, randomize: bool = False) -> Agent:
        """
        Returns an example Agent instance.

        :param randomize: If True, adds a random string to the value of an example key.
        """
        addition = "" if not randomize else str(uuid4())
        return cls(traits={"age": 22, "hair": f"brown{addition}", "height": 5.5})

    def code(self) -> str:
        """Return the code for the agent.

        Example usage:

        >>> a = Agent(traits = {"age": 10, "hair": "brown", "height": 5.5})
        >>> print(a.code())
        from edsl import Agent
        agent = Agent(traits={'age': 10, 'hair': 'brown', 'height': 5.5})
        """
        return f"from edsl import Agent\nagent = Agent(traits={self.traits})"


def main():
    """
    Give an example of usage.

    WARNING: Consume API credits
    """
    from edsl.agents import Agent
    from edsl.questions import QuestionMultipleChoice

    # a simple agent
    agent = Agent(traits={"age": 10, "hair": "brown", "height": 5.5})
    agent.traits
    agent.print()
    # combining two agents
    agent = Agent(traits={"age": 10}) + Agent(traits={"height": 5.5})
    agent.traits
    # Agent -> Job using the to() method
    agent = Agent(traits={"allergies": "peanut"})
    question = QuestionMultipleChoice(
        question_text="Would you enjoy a PB&J?",
        question_options=["Yes", "No"],
        question_name="food_preference",
    )
    job = question.by(agent)
    results = job.run()


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
