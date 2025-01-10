"""This module contains the Interview class, which is responsible for conducting an interview asynchronously."""

from __future__ import annotations
import asyncio
from typing import Any, Type, List, Generator, Optional, Union, TYPE_CHECKING
import copy
from dataclasses import dataclass

# from edsl.jobs.Answers import Answers
from edsl.jobs.data_structures import Answers
from edsl.jobs.interviews.InterviewStatusLog import InterviewStatusLog
from edsl.jobs.interviews.InterviewStatusDictionary import InterviewStatusDictionary
from edsl.jobs.interviews.InterviewExceptionCollection import (
    InterviewExceptionCollection,
)
from edsl.jobs.interviews.InterviewExceptionEntry import InterviewExceptionEntry
from edsl.jobs.buckets.ModelBuckets import ModelBuckets
from edsl.jobs.AnswerQuestionFunctionConstructor import (
    AnswerQuestionFunctionConstructor,
)
from edsl.jobs.InterviewTaskManager import InterviewTaskManager
from edsl.jobs.FetchInvigilator import FetchInvigilator
from edsl.jobs.RequestTokenEstimator import RequestTokenEstimator


if TYPE_CHECKING:
    from edsl.agents.Agent import Agent
    from edsl.surveys.Survey import Survey
    from edsl.scenarios.Scenario import Scenario
    from edsl.data.Cache import Cache
    from edsl.language_models.LanguageModel import LanguageModel
    from edsl.jobs.tokens.InterviewTokenUsage import InterviewTokenUsage
    from edsl.agents.InvigilatorBase import InvigilatorBase
    from edsl.language_models.key_management.KeyLookup import KeyLookup


@dataclass
class InterviewRunningConfig:
    cache: Optional["Cache"] = (None,)
    skip_retry: bool = (False,)  # COULD BE SET WITH CONFIG
    raise_validation_errors: bool = (True,)
    stop_on_exception: bool = (False,)


class Interview:
    """
    An 'interview' is one agent answering one survey, with one language model, for a given scenario.

    The main method is `async_conduct_interview`, which conducts the interview asynchronously.
    Most of the class is dedicated to creating the tasks for each question in the survey, and then running them.
    """

    def __init__(
        self,
        agent: Agent,
        survey: Survey,
        scenario: Scenario,
        model: Type["LanguageModel"],
        iteration: int = 0,
        indices: dict = None,  # explain?
        cache: Optional["Cache"] = None,
        skip_retry: bool = False,  # COULD BE SET WITH CONFIG
        raise_validation_errors: bool = True,
    ):
        """Initialize the Interview instance.

        :param agent: the agent being interviewed.
        :param survey: the survey being administered to the agent.
        :param scenario: the scenario that populates the survey questions.
        :param model: the language model used to answer the questions.
        # :param debug: if True, run without calls to the language model.
        :param iteration: the iteration number of the interview.
        :param cache: the cache used to store the answers.

        >>> i = Interview.example()
        >>> i.task_manager.task_creators
        {}

        >>> i.exceptions
        {}

        >>> _ = asyncio.run(i.async_conduct_interview())
        >>> i.task_status_logs['q0']
        [{'log_time': ..., 'value': <TaskStatus.NOT_STARTED: 1>}, {'log_time': ..., 'value': <TaskStatus.WAITING_FOR_DEPENDENCIES: 2>}, {'log_time': ..., 'value': <TaskStatus.API_CALL_IN_PROGRESS: 7>}, {'log_time': ..., 'value': <TaskStatus.SUCCESS: 8>}]

        >>> i.to_index
        {'q0': 0, 'q1': 1, 'q2': 2}

        """
        self.agent = agent
        self.survey = copy.deepcopy(survey)  # why do we need to deepcopy the survey?
        self.scenario = scenario
        self.model = model
        self.iteration = iteration

        self.answers = Answers()  # will get filled in as interview progresses

        self.task_manager = InterviewTaskManager(
            survey=self.survey,
            iteration=iteration,
        )

        self.exceptions = InterviewExceptionCollection()

        self.running_config = InterviewRunningConfig(
            cache=cache,
            skip_retry=skip_retry,
            raise_validation_errors=raise_validation_errors,
        )

        self.cache = cache
        self.skip_retry = skip_retry
        self.raise_validation_errors = raise_validation_errors

        # dictionary mapping question names to their index in the survey.
        self.to_index = {
            question_name: index
            for index, question_name in enumerate(self.survey.question_names)
        }

        self.failed_questions = []

        self.indices = indices
        self.initial_hash = hash(self)

    @property
    def has_exceptions(self) -> bool:
        """Return True if there are exceptions."""
        return len(self.exceptions) > 0

    @property
    def task_status_logs(self) -> InterviewStatusLog:
        """Return the task status logs for the interview.

        The keys are the question names; the values are the lists of status log changes for each task.
        """
        return self.task_manager.task_status_logs

    @property
    def token_usage(self) -> InterviewTokenUsage:
        """Determine how many tokens were used for the interview."""
        return self.task_manager.token_usage  # task_creators.token_usage

    @property
    def interview_status(self) -> InterviewStatusDictionary:
        """Return a dictionary mapping task status codes to counts."""
        # return self.task_creators.interview_status
        return self.task_manager.interview_status

    def to_dict(self, include_exceptions=True, add_edsl_version=True) -> dict[str, Any]:
        """Return a dictionary representation of the Interview instance.
        This is just for hashing purposes.

        >>> i = Interview.example()
        >>> hash(i)
        767745459362662063
        """
        d = {
            "agent": self.agent.to_dict(add_edsl_version=add_edsl_version),
            "survey": self.survey.to_dict(add_edsl_version=add_edsl_version),
            "scenario": self.scenario.to_dict(add_edsl_version=add_edsl_version),
            "model": self.model.to_dict(add_edsl_version=add_edsl_version),
            "iteration": self.iteration,
            "exceptions": {},
        }
        if include_exceptions:
            d["exceptions"] = self.exceptions.to_dict()
        if hasattr(self, "indices"):
            d["indices"] = self.indices
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Interview":
        """Return an Interview instance from a dictionary."""

        from edsl.agents.Agent import Agent
        from edsl.surveys.Survey import Survey
        from edsl.scenarios.Scenario import Scenario
        from edsl.language_models.LanguageModel import LanguageModel

        agent = Agent.from_dict(d["agent"])
        survey = Survey.from_dict(d["survey"])
        scenario = Scenario.from_dict(d["scenario"])
        model = LanguageModel.from_dict(d["model"])
        iteration = d["iteration"]
        params = {
            "agent": agent,
            "survey": survey,
            "scenario": scenario,
            "model": model,
            "iteration": iteration,
        }
        if "indices" in d:
            params["indices"] = d["indices"]
        interview = cls(**params)
        if "exceptions" in d:
            exceptions = InterviewExceptionCollection.from_dict(d["exceptions"])
            interview.exceptions = exceptions
        return interview

    def __hash__(self) -> int:
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(include_exceptions=False, add_edsl_version=False))

    def __eq__(self, other: "Interview") -> bool:
        """
        >>> from edsl.jobs.interviews.Interview import Interview; i = Interview.example(); d = i.to_dict(); i2 = Interview.from_dict(d); i == i2
        True
        """
        return hash(self) == hash(other)

    async def async_conduct_interview(
        self,
        run_config: Optional["RunConfig"] = None,
        #     model_buckets: Optional[ModelBuckets] = None,
        #     stop_on_exception: bool = False,
        #     raise_validation_errors: bool = True,
        #     key_lookup: Optional[KeyLookup] = None,
    ) -> tuple["Answers", List[dict[str, Any]]]:
        """
        Conduct an Interview asynchronously.
        It returns a tuple with the answers and a list of valid results.

        :param model_buckets: a dictionary of token buckets for the model.
        :param debug: run without calls to LLM.
        :param stop_on_exception: if True, stops the interview if an exception is raised.

        Example usage:

        >>> i = Interview.example()
        >>> result, _ = asyncio.run(i.async_conduct_interview())
        >>> result['q0']
        'yes'

        >>> i = Interview.example(throw_exception = True)
        >>> result, _ = asyncio.run(i.async_conduct_interview())
        >>> i.exceptions
        {'q0': ...
        >>> i = Interview.example()
        >>> from edsl.jobs.Jobs import RunConfig, RunParameters, RunEnvironment
        >>> run_config = RunConfig(parameters = RunParameters(), environment = RunEnvironment())
        >>> run_config.parameters.stop_on_exception = True
        >>> result, _ = asyncio.run(i.async_conduct_interview(run_config))
        Traceback (most recent call last):
        ...
        asyncio.exceptions.CancelledError
        """
        from edsl.jobs.Jobs import RunConfig, RunParameters, RunEnvironment

        if run_config is None:
            run_config = RunConfig(
                parameters=RunParameters(),
                environment=RunEnvironment(),
            )
        self.stop_on_exception = run_config.parameters.stop_on_exception

        # if no model bucket is passed, create an 'infinity' bucket with no rate limits
        bucket_collection = run_config.environment.bucket_collection

        if bucket_collection:
            model_buckets = bucket_collection.get(self.model)
        else:
            model_buckets = None

        if model_buckets is None or hasattr(self.agent, "answer_question_directly"):
            model_buckets = ModelBuckets.infinity_bucket()

        # was "self.tasks" - is that necessary?
        self.tasks = self.task_manager.build_question_tasks(
            answer_func=AnswerQuestionFunctionConstructor(
                self, key_lookup=run_config.environment.key_lookup
            )(),
            token_estimator=RequestTokenEstimator(self),
            model_buckets=model_buckets,
        )

        ## This is the key part---it creates a task for each question,
        ## with dependencies on the questions that must be answered before this one can be answered.

        ## 'Invigilators' are used to administer the survey.
        fetcher = FetchInvigilator(
            interview=self,
            current_answers=self.answers,
            key_lookup=run_config.environment.key_lookup,
        )
        self.invigilators = [fetcher(question) for question in self.survey.questions]
        await asyncio.gather(
            *self.tasks, return_exceptions=not run_config.parameters.stop_on_exception
        )
        self.answers.replace_missing_answers_with_none(self.survey)
        valid_results = list(
            self._extract_valid_results(self.tasks, self.invigilators, self.exceptions)
        )
        return self.answers, valid_results

    @staticmethod
    def _extract_valid_results(
        tasks: List["asyncio.Task"],
        invigilators: List["InvigilatorBase"],
        exceptions: InterviewExceptionCollection,
    ) -> Generator["Answers", None, None]:
        """Extract the valid results from the list of results.

        It iterates through the tasks and invigilators, and yields the results of the tasks that are done.
        If a task is not done, it raises a ValueError.
        If an exception is raised in the task, it records the exception in the Interview instance except if the task was cancelled, which is expected behavior.

        >>> i = Interview.example()
        >>> result, _ = asyncio.run(i.async_conduct_interview())
        """
        assert len(tasks) == len(invigilators)

        def handle_task(task, invigilator):
            try:
                result = task.result()
            except asyncio.CancelledError as e:  # task was cancelled
                result = invigilator.get_failed_task_result(
                    failure_reason="Task was cancelled."
                )
            except Exception as e:  # any other kind of exception in the task
                result = invigilator.get_failed_task_result(
                    failure_reason=f"Task failed with exception: {str(e)}."
                )
                exception_entry = InterviewExceptionEntry(
                    exception=e,
                    invigilator=invigilator,
                )
                exceptions.add(task.get_name(), exception_entry)
            return result

        for task, invigilator in zip(tasks, invigilators):
            if not task.done():
                raise ValueError(f"Task {task.get_name()} is not done.")

            yield handle_task(task, invigilator)

    def __repr__(self) -> str:
        """Return a string representation of the Interview instance."""
        return f"Interview(agent = {repr(self.agent)}, survey = {repr(self.survey)}, scenario = {repr(self.scenario)}, model = {repr(self.model)})"

    def duplicate(
        self, iteration: int, cache: "Cache", randomize_survey: Optional[bool] = True
    ) -> Interview:
        """Duplicate the interview, but with a new iteration number and cache.

        >>> i = Interview.example()
        >>> i2 = i.duplicate(1, None)
        >>> i.iteration + 1 == i2.iteration
        True

        """
        if randomize_survey:
            new_survey = self.survey.draw()
        else:
            new_survey = self.survey

        return Interview(
            agent=self.agent,
            survey=new_survey,
            scenario=self.scenario,
            model=self.model,
            iteration=iteration,
            cache=self.running_config.cache,
            skip_retry=self.running_config.skip_retry,
            indices=self.indices,
        )

    @classmethod
    def example(self, throw_exception: bool = False) -> Interview:
        """Return an example Interview instance."""
        from edsl.agents import Agent
        from edsl.surveys import Survey
        from edsl.scenarios import Scenario
        from edsl.language_models import LanguageModel

        def f(self, question, scenario):
            return "yes"

        agent = Agent.example()
        agent.add_direct_question_answering_method(f)
        survey = Survey.example()
        scenario = Scenario.example()
        model = LanguageModel.example()
        if throw_exception:
            model = LanguageModel.example(test_model=True, throw_exception=True)
            agent = Agent.example()
            return Interview(agent=agent, survey=survey, scenario=scenario, model=model)
        return Interview(agent=agent, survey=survey, scenario=scenario, model=model)


if __name__ == "__main__":
    import doctest

    # add ellipsis
    doctest.testmod(optionflags=doctest.ELLIPSIS)
