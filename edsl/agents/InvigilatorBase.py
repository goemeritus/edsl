from abc import ABC, abstractmethod
import asyncio
from typing import Coroutine, Dict, Any, Optional

from edsl.prompts.Prompt import Prompt
from edsl.utilities.decorators import jupyter_nb_handler
from edsl.data_transfer_models import AgentResponseDict

from edsl.data.Cache import Cache

from edsl.questions.QuestionBase import QuestionBase
from edsl.scenarios.Scenario import Scenario
from edsl.surveys.MemoryPlan import MemoryPlan
from edsl.language_models.LanguageModel import LanguageModel

from edsl.data_transfer_models import EDSLResultObjectInput
from edsl.agents.PromptConstructor import PromptConstructor

from edsl.agents.prompt_helpers import PromptPlan


class InvigilatorBase(ABC):
    """An invigiator (someone who administers an exam) is a class that is responsible for administering a question to an agent.

    >>> InvigilatorBase.example().answer_question()
    {'message': [{'text': 'SPAM!'}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}

    >>> InvigilatorBase.example().get_failed_task_result(failure_reason="Failed to get response").comment
    'Failed to get response'

    This returns an empty prompt because there is no memory the agent needs to have at q0.


    """

    def __init__(
        self,
        agent: "Agent",
        question: QuestionBase,
        scenario: Scenario,
        model: LanguageModel,
        memory_plan: MemoryPlan,
        current_answers: dict,
        survey: Optional["Survey"],
        cache: Optional[Cache] = None,
        iteration: Optional[int] = 1,
        additional_prompt_data: Optional[dict] = None,
        sidecar_model: Optional[LanguageModel] = None,
        raise_validation_errors: Optional[bool] = True,
        prompt_plan: Optional["PromptPlan"] = None,
    ):
        """Initialize a new Invigilator."""
        self.agent = agent
        self.question = question
        self.scenario = scenario
        self.model = model
        self.memory_plan = memory_plan
        self.current_answers = current_answers or {}
        self.iteration = iteration
        self.additional_prompt_data = additional_prompt_data
        self.cache = cache
        self.sidecar_model = sidecar_model
        self.survey = survey
        self.raise_validation_errors = raise_validation_errors
        if prompt_plan is None:
            self.prompt_plan = PromptPlan()
        else:
            self.prompt_plan = prompt_plan

        self.raw_model_response = (
            None  # placeholder for the raw response from the model
        )

    @property
    def prompt_constructor(self) -> PromptConstructor:
        """Return the prompt constructor."""
        return PromptConstructor(self, prompt_plan=self.prompt_plan)

    def to_dict(self, include_cache=False):
        breakpoint()
        attributes = [
            "agent",
            "question",
            "scenario",
            "model",
            "memory_plan",
            "current_answers",
            "iteration",
            "additional_prompt_data",
            "sidecar_model",
            "survey",
        ]
        if include_cache:
            attributes.append("cache")

        def serialize_attribute(attr):
            value = getattr(self, attr)
            if value is None:
                return None
            if hasattr(value, "to_dict"):
                return value.to_dict()
            if isinstance(value, (int, float, str, bool, dict, list)):
                return value
            return str(value)

        return {attr: serialize_attribute(attr) for attr in attributes}

    @classmethod
    def from_dict(cls, data):
        from edsl.agents.Agent import Agent
        from edsl.questions import QuestionBase
        from edsl.scenarios.Scenario import Scenario
        from edsl.surveys.MemoryPlan import MemoryPlan
        from edsl.language_models.LanguageModel import LanguageModel
        from edsl.surveys.Survey import Survey
        from edsl.data.Cache import Cache

        agent = Agent.from_dict(data["agent"])
        question = QuestionBase.from_dict(data["question"])
        scenario = Scenario.from_dict(data["scenario"])
        model = LanguageModel.from_dict(data["model"])
        memory_plan = MemoryPlan.from_dict(data["memory_plan"])
        survey = Survey.from_dict(data["survey"])
        current_answers = data["current_answers"]
        iteration = data["iteration"]
        additional_prompt_data = data["additional_prompt_data"]
        if "cache" not in data:
            cache = {}
        else:
            cache = Cache.from_dict(data["cache"])

        if data["sidecar_model"] is None:
            sidecar_model = None
        else:
            sidecar_model = LanguageModel.from_dict(data["sidecar_model"])

        return cls(
            agent=agent,
            question=question,
            scenario=scenario,
            model=model,
            memory_plan=memory_plan,
            current_answers=current_answers,
            survey=survey,
            iteration=iteration,
            additional_prompt_data=additional_prompt_data,
            cache=cache,
            sidecar_model=sidecar_model,
        )

    def __repr__(self) -> str:
        """Return a string representation of the Invigilator.

        >>> InvigilatorBase.example().__repr__()
        'InvigilatorExample(...)'

        """
        return f"{self.__class__.__name__}(agent={repr(self.agent)}, question={repr(self.question)}, scneario={repr(self.scenario)}, model={repr(self.model)}, memory_plan={repr(self.memory_plan)}, current_answers={repr(self.current_answers)}, iteration{repr(self.iteration)}, additional_prompt_data={repr(self.additional_prompt_data)}, cache={repr(self.cache)}, sidecarmodel={repr(self.sidecar_model)})"

    def get_failed_task_result(self, failure_reason) -> EDSLResultObjectInput:
        """Return an AgentResponseDict used in case the question-asking fails.

        Possible reasons include:
        - Legimately skipped because of skip logic
        - Failed to get response from the model

        """
        data = {
            "answer": None,
            "generated_tokens": None,
            "comment": failure_reason,
            "question_name": self.question.question_name,
            "prompts": self.get_prompts(),
            "cached_response": None,
            "raw_model_response": None,
            "cache_used": None,
            "cache_key": None,
        }
        return EDSLResultObjectInput(**data)

    def get_prompts(self) -> Dict[str, Prompt]:
        """Return the prompt used."""

        return {
            "user_prompt": Prompt("NA"),
            "system_prompt": Prompt("NA"),
        }

    @abstractmethod
    async def async_answer_question(self):
        """Asnwer a question."""
        pass

    @jupyter_nb_handler
    def answer_question(self) -> Coroutine:
        """Return a function that gets the answers to the question."""

        async def main():
            """Return the answer to the question."""
            results = await asyncio.gather(self.async_answer_question())
            return results[0]  # Since there's only one task, return its result

        return main()

    @classmethod
    def example(
        cls, throw_an_exception=False, question=None, scenario=None, survey=None
    ) -> "InvigilatorBase":
        """Return an example invigilator.

        >>> InvigilatorBase.example()
        InvigilatorExample(...)

        """
        from edsl.agents.Agent import Agent
        from edsl.questions import QuestionMultipleChoice
        from edsl.scenarios.Scenario import Scenario
        from edsl.language_models import LanguageModel
        from edsl.surveys.MemoryPlan import MemoryPlan

        from edsl.enums import InferenceServiceType

        from edsl import Model

        model = Model("test", canned_response="SPAM!")

        if throw_an_exception:
            model.throw_an_exception = True
        agent = Agent.example()
        # question = QuestionMultipleChoice.example()
        from edsl.surveys import Survey

        if not survey:
            survey = Survey.example()

        if question not in survey.questions and question is not None:
            survey.add_question(question)

        question = question or survey.questions[0]
        scenario = scenario or Scenario.example()
        # memory_plan = None #memory_plan = MemoryPlan()
        from edsl import Survey

        memory_plan = MemoryPlan(survey=survey)
        current_answers = None
        from edsl.agents.PromptConstructor import PromptConstructor

        class InvigilatorExample(InvigilatorBase):
            """An example invigilator."""

            async def async_answer_question(self):
                """Answer a question."""
                return await self.model.async_execute_model_call(
                    user_prompt="Hello", system_prompt="Hi"
                )

        return InvigilatorExample(
            agent=agent,
            question=question,
            scenario=scenario,
            survey=survey,
            model=model,
            memory_plan=memory_plan,
            current_answers=current_answers,
        )


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
