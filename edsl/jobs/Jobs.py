# """The Jobs class is a collection of agents, scenarios and models and one survey."""
from __future__ import annotations
import asyncio
from inspect import signature
from typing import (
    Literal,
    Optional,
    Union,
    Sequence,
    Generator,
    TYPE_CHECKING,
    Callable,
    Tuple,
)

from edsl.Base import Base

from edsl.jobs.buckets.BucketCollection import BucketCollection
from edsl.jobs.JobsPrompts import JobsPrompts
from edsl.jobs.interviews.Interview import Interview
from edsl.utilities.remove_edsl_version import remove_edsl_version
from edsl.jobs.runners.JobsRunnerAsyncio import JobsRunnerAsyncio
from edsl.data.RemoteCacheSync import RemoteCacheSync
from edsl.exceptions.coop import CoopServerResponseError

from edsl.jobs.JobsChecks import JobsChecks
from edsl.jobs.data_structures import RunEnvironment, RunParameters, RunConfig

if TYPE_CHECKING:
    from edsl.agents.Agent import Agent
    from edsl.agents.AgentList import AgentList
    from edsl.language_models.LanguageModel import LanguageModel
    from edsl.scenarios.Scenario import Scenario
    from edsl.scenarios.ScenarioList import ScenarioList
    from edsl.surveys.Survey import Survey
    from edsl.results.Results import Results
    from edsl.results.Dataset import Dataset
    from edsl.language_models.ModelList import ModelList
    from edsl.data.Cache import Cache
    from edsl.language_models.key_management.KeyLookup import KeyLookup

VisibilityType = Literal["private", "public", "unlisted"]

from dataclasses import dataclass
from typing import Optional, Union, TypeVar, Callable, cast
from functools import wraps

try:
    from typing import ParamSpec
except ImportError:
    from typing_extensions import ParamSpec


P = ParamSpec("P")
T = TypeVar("T")


from edsl.jobs.check_survey_scenario_compatibility import (
    CheckSurveyScenarioCompatibility,
)


def with_config(f: Callable[P, T]) -> Callable[P, T]:
    "This decorator make it so that the run function parameters match the RunConfig dataclass."
    parameter_fields = {
        name: field.default
        for name, field in RunParameters.__dataclass_fields__.items()
    }
    environment_fields = {
        name: field.default
        for name, field in RunEnvironment.__dataclass_fields__.items()
    }
    combined = {**parameter_fields, **environment_fields}

    @wraps(f)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        environment = RunEnvironment(
            **{k: v for k, v in kwargs.items() if k in environment_fields}
        )
        parameters = RunParameters(
            **{k: v for k, v in kwargs.items() if k in parameter_fields}
        )
        config = RunConfig(environment=environment, parameters=parameters)
        return f(*args, config=config)

    # Update the wrapper's signature to include all RunConfig parameters
    # old_sig = signature(f)
    # wrapper.__signature__ = old_sig.replace(
    #     parameters=list(old_sig.parameters.values())[:-1]
    #     + [
    #         old_sig.parameters["config"].replace(
    #             default=parameter_fields[name], name=name
    #         )
    #         for name in combined
    #     ]
    # )

    return cast(Callable[P, T], wrapper)


class Jobs(Base):
    """
    A collection of agents, scenarios and models and one survey that creates 'interviews'
    """

    __documentation__ = "https://docs.expectedparrot.com/en/latest/jobs.html"

    def __init__(
        self,
        survey: "Survey",
        agents: Optional[Union[list[Agent], AgentList]] = None,
        models: Optional[Union[ModelList, list[LanguageModel]]] = None,
        scenarios: Optional[Union[ScenarioList, list[Scenario]]] = None,
    ):
        """Initialize a Jobs instance.

        :param survey: the survey to be used in the job
        :param agents: a list of agents
        :param models: a list of models
        :param scenarios: a list of scenarios
        """
        self.run_config = RunConfig(
            environment=RunEnvironment(), parameters=RunParameters()
        )

        self.survey = survey
        self.agents: AgentList = agents
        self.scenarios: ScenarioList = scenarios
        self.models: ModelList = models

    def add_running_env(self, running_env: RunEnvironment):
        self.run_config.add_environment(running_env)
        return self

    def using_cache(self, cache: "Cache") -> Jobs:
        """
        Add a Cache to the job.

        :param cache: the cache to add
        """
        self.run_config.add_cache(cache)
        return self

    def using_bucket_collection(self, bucket_collection: BucketCollection) -> Jobs:
        """
        Add a BucketCollection to the job.

        :param bucket_collection: the bucket collection to add
        """
        self.run_config.add_bucket_collection(bucket_collection)
        return self

    def using_key_lookup(self, key_lookup: KeyLookup) -> Jobs:
        """
        Add a KeyLookup to the job.

        :param key_lookup: the key lookup to add
        """
        self.run_config.add_key_lookup(key_lookup)
        return self

    def using(self, obj: Union[Cache, BucketCollection, KeyLookup]) -> Jobs:
        """
        Add a Cache, BucketCollection, or KeyLookup to the job.

        :param obj: the object to add
        """
        from edsl.data.Cache import Cache
        from edsl.language_models.key_management.KeyLookup import KeyLookup

        if isinstance(obj, Cache):
            self.using_cache(obj)
        elif isinstance(obj, BucketCollection):
            self.using_bucket_collection(obj)
        elif isinstance(obj, KeyLookup):
            self.using_key_lookup(obj)
        return self

    @property
    def models(self):
        return self._models

    @models.setter
    def models(self, value):
        from edsl.language_models.ModelList import ModelList

        if value:
            if not isinstance(value, ModelList):
                self._models = ModelList(value)
            else:
                self._models = value
        else:
            self._models = ModelList([])

        # update the bucket collection if it exists
        if self.run_config.environment.bucket_collection is None:
            self.run_config.environment.bucket_collection = (
                self.create_bucket_collection()
            )

    @property
    def agents(self):
        return self._agents

    @agents.setter
    def agents(self, value):
        from edsl.agents.AgentList import AgentList

        if value:
            if not isinstance(value, AgentList):
                self._agents = AgentList(value)
            else:
                self._agents = value
        else:
            self._agents = AgentList([])

    @property
    def scenarios(self):
        return self._scenarios

    @scenarios.setter
    def scenarios(self, value):
        from edsl.scenarios.ScenarioList import ScenarioList
        from edsl.results.Dataset import Dataset

        if value:
            if isinstance(
                value, Dataset
            ):  # if the user passes in a Dataset, convert it to a ScenarioList
                value = value.to_scenario_list()

            if not isinstance(value, ScenarioList):
                self._scenarios = ScenarioList(value)
            else:
                self._scenarios = value
        else:
            self._scenarios = ScenarioList([])

    def by(
        self,
        *args: Union[
            Agent,
            Scenario,
            LanguageModel,
            Sequence[Union["Agent", "Scenario", "LanguageModel"]],
        ],
    ) -> Jobs:
        """
        Add Agents, Scenarios and LanguageModels to a job.

        :param args: objects or a sequence (list, tuple, ...) of objects of the same type

        If no objects of this type exist in the Jobs instance, it stores the new objects as a list in the corresponding attribute.
        Otherwise, it combines the new objects with existing objects using the object's `__add__` method.

        This 'by' is intended to create a fluent interface.

        >>> from edsl.surveys.Survey import Survey
        >>> from edsl.questions.QuestionFreeText import QuestionFreeText
        >>> q = QuestionFreeText(question_name="name", question_text="What is your name?")
        >>> j = Jobs(survey = Survey(questions=[q]))
        >>> j
        Jobs(survey=Survey(...), agents=AgentList([]), models=ModelList([]), scenarios=ScenarioList([]))
        >>> from edsl.agents.Agent import Agent; a = Agent(traits = {"status": "Sad"})
        >>> j.by(a).agents
        AgentList([Agent(traits = {'status': 'Sad'})])


        Notes:
        - all objects must implement the 'get_value', 'set_value', and `__add__` methods
        - agents: traits of new agents are combined with traits of existing agents. New and existing agents should not have overlapping traits, and do not increase the # agents in the instance
        - scenarios: traits of new scenarios are combined with traits of old existing. New scenarios will overwrite overlapping traits, and do not increase the number of scenarios in the instance
        - models: new models overwrite old models.
        """
        from edsl.jobs.JobsComponentConstructor import JobsComponentConstructor

        return JobsComponentConstructor(self).by(*args)

    def prompts(self) -> "Dataset":
        """Return a Dataset of prompts that will be used.


        >>> from edsl.jobs import Jobs
        >>> Jobs.example().prompts()
        Dataset(...)
        """
        return JobsPrompts(self).prompts()

    def show_prompts(self, all: bool = False) -> None:
        """Print the prompts."""
        if all:
            return self.prompts().to_scenario_list().table()
        else:
            return (
                self.prompts().to_scenario_list().table("user_prompt", "system_prompt")
            )

    @staticmethod
    def estimate_prompt_cost(
        system_prompt: str,
        user_prompt: str,
        price_lookup: dict,
        inference_service: str,
        model: str,
    ) -> dict:
        """
        Estimate the cost of running the prompts.
        :param iterations: the number of iterations to run
        :param system_prompt: the system prompt
        :param user_prompt: the user prompt
        :param price_lookup: the price lookup
        :param inference_service: the inference service
        :param model: the model name
        """
        return JobsPrompts.estimate_prompt_cost(
            system_prompt, user_prompt, price_lookup, inference_service, model
        )

    def estimate_job_cost(self, iterations: int = 1) -> dict:
        """
        Estimate the cost of running the job.

        :param iterations: the number of iterations to run
        """
        return JobsPrompts(self).estimate_job_cost(iterations)

    def estimate_job_cost_from_external_prices(
        self, price_lookup: dict, iterations: int = 1
    ) -> dict:
        return JobsPrompts(self).estimate_job_cost_from_external_prices(
            price_lookup, iterations
        )

    @staticmethod
    def compute_job_cost(job_results: Results) -> float:
        """
        Computes the cost of a completed job in USD.
        """
        return job_results.compute_job_cost()

    def replace_missing_objects(self) -> None:
        from edsl.agents.Agent import Agent
        from edsl.language_models.model import Model
        from edsl.scenarios.Scenario import Scenario

        self.agents = self.agents or [Agent()]
        self.models = self.models or [Model()]
        self.scenarios = self.scenarios or [Scenario()]

    def generate_interviews(self) -> Generator[Interview, None, None]:
        """
        Generate interviews.

        Note that this sets the agents, model and scenarios if they have not been set. This is a side effect of the method.
        This is useful because a user can create a job without setting the agents, models, or scenarios, and the job will still run,
        with us filling in defaults.

        """
        from edsl.jobs.InterviewsConstructor import InterviewsConstructor

        self.replace_missing_objects()
        yield from InterviewsConstructor(
            self, cache=self.run_config.environment.cache
        ).create_interviews()

    def interviews(self) -> list[Interview]:
        """
        Return a list of :class:`edsl.jobs.interviews.Interview` objects.

        It returns one Interview for each combination of Agent, Scenario, and LanguageModel.
        If any of Agents, Scenarios, or LanguageModels are missing, it fills in with defaults.

        >>> from edsl.jobs import Jobs
        >>> j = Jobs.example()
        >>> len(j.interviews())
        4
        >>> j.interviews()[0]
        Interview(agent = Agent(traits = {'status': 'Joyful'}), survey = Survey(...), scenario = Scenario({'period': 'morning'}), model = Model(...))
        """
        return list(self.generate_interviews())

    @classmethod
    def from_interviews(cls, interview_list) -> "Jobs":
        """Return a Jobs instance from a list of interviews.

        This is useful when you have, say, a list of failed interviews and you want to create
        a new job with only those interviews.
        """
        survey = interview_list[0].survey
        # get all the models
        models = list(set([interview.model for interview in interview_list]))
        jobs = cls(survey)
        jobs.models = models
        jobs._interviews = interview_list
        return jobs

    def create_bucket_collection(self) -> BucketCollection:
        """
        Create a collection of buckets for each model.

        These buckets are used to track API calls and token usage.

        >>> from edsl.jobs import Jobs
        >>> from edsl import Model
        >>> j = Jobs.example().by(Model(temperature = 1), Model(temperature = 0.5))
        >>> bc = j.create_bucket_collection()
        >>> bc
        BucketCollection(...)
        """
        return BucketCollection.from_models(self.models)

    def html(self):
        """Return the HTML representations for each scenario"""
        links = []
        for index, scenario in enumerate(self.scenarios):
            links.append(
                self.survey.html(
                    scenario=scenario, return_link=True, cta=f"Scenario {index}"
                )
            )
        return links

    def __hash__(self):
        """Allow the model to be used as a key in a dictionary.

        >>> from edsl.jobs import Jobs
        >>> hash(Jobs.example())
        846655441787442972

        """
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(add_edsl_version=False))

    def _output(self, message) -> None:
        """Check if a Job is verbose. If so, print the message."""
        if self.run_config.parameters.verbose:
            print(message)
        # if hasattr(self, "verbose") and self.verbose:
        #    print(message)

    def all_question_parameters(self) -> set:
        """Return all the fields in the questions in the survey.
        >>> from edsl.jobs import Jobs
        >>> Jobs.example().all_question_parameters()
        {'period'}
        """
        return set.union(*[question.parameters for question in self.survey.questions])

    def use_remote_cache(self) -> bool:
        import requests

        if self.run_config.parameters.disable_remote_cache:
            return False
        if not self.run_config.parameters.disable_remote_cache:
            try:
                from edsl.coop.coop import Coop

                user_edsl_settings = Coop().edsl_settings
                return user_edsl_settings.get("remote_caching", False)
            except requests.ConnectionError:
                pass
            except CoopServerResponseError as e:
                pass

        return False

    def _remote_results(
        self,
    ) -> Union["Results", None]:
        from edsl.jobs.JobsRemoteInferenceHandler import JobsRemoteInferenceHandler

        jh = JobsRemoteInferenceHandler(
            self, verbose=self.run_config.parameters.verbose
        )
        if jh.use_remote_inference(self.run_config.parameters.disable_remote_inference):
            job_info = jh.create_remote_inference_job(
                iterations=self.run_config.parameters.n,
                remote_inference_description=self.run_config.parameters.remote_inference_description,
                remote_inference_results_visibility=self.run_config.parameters.remote_inference_results_visibility,
            )
            results = jh.poll_remote_inference_job(job_info)
            return results
        else:
            return None

    def _prepare_to_run(self) -> None:
        "This makes sure that the job is ready to run and that keys are in place for a remote job."
        CheckSurveyScenarioCompatibility(self.survey, self.scenarios).check()

    def _check_if_remote_keys_ok(self):
        jc = JobsChecks(self)
        if jc.needs_key_process():
            jc.key_process()

    def _check_if_local_keys_ok(self):
        jc = JobsChecks(self)
        if self.run_config.parameters.check_api_keys:
            jc.check_api_keys()

    async def _execute_with_remote_cache(self, run_job_async: bool) -> Results:
        use_remote_cache = self.use_remote_cache()

        from edsl.coop.coop import Coop
        from edsl.jobs.runners.JobsRunnerAsyncio import JobsRunnerAsyncio
        from edsl.data.Cache import Cache

        assert isinstance(self.run_config.environment.cache, Cache)

        # with RemoteCacheSync(
        #     coop=Coop(),
        #     cache=self.run_config.environment.cache,
        #     output_func=self._output,
        #     remote_cache=use_remote_cache,
        #     remote_cache_description=self.run_config.parameters.remote_cache_description,
        # ):
        runner = JobsRunnerAsyncio(self, environment=self.run_config.environment)
        if run_job_async:
            results = await runner.run_async(self.run_config.parameters)
        else:
            results = runner.run(self.run_config.parameters)
        return results

    def _setup_and_check(self) -> Tuple[RunConfig, Optional[Results]]:
        self._prepare_to_run()
        self._check_if_remote_keys_ok()

        # first try to run the job remotely
        if results := self._remote_results():
            return results

        self._check_if_local_keys_ok()
        return None

    @property
    def num_interviews(self):
        if self.run_config.parameters.n is None:
            return len(self)
        else:
            return len(self) * self.run_config.parameters.n

    def _run(self, config: RunConfig):
        "Shared code for run and run_async"
        if config.environment.cache is not None:
            self.run_config.environment.cache = config.environment.cache
        if config.environment.jobs_runner_status is not None:
            self.run_config.environment.jobs_runner_status = (
                config.environment.jobs_runner_status
            )

        if config.environment.bucket_collection is not None:
            self.run_config.environment.bucket_collection = (
                config.environment.bucket_collection
            )

        if config.environment.key_lookup is not None:
            self.run_config.environment.key_lookup = config.environment.key_lookup

        # replace the parameters with the ones from the config
        self.run_config.parameters = config.parameters

        self.replace_missing_objects()

        # try to run remotely first
        self._prepare_to_run()
        self._check_if_remote_keys_ok()

        if (
            self.run_config.environment.cache is None
            or self.run_config.environment.cache is True
        ):
            from edsl.data.CacheHandler import CacheHandler

            self.run_config.environment.cache = CacheHandler().get_cache()

        if self.run_config.environment.cache is False:
            from edsl.data.Cache import Cache

            self.run_config.environment.cache = Cache(immediate_write=False)

        # first try to run the job remotely
        if results := self._remote_results():
            return results

        self._check_if_local_keys_ok()

        if config.environment.bucket_collection is None:
            self.run_config.environment.bucket_collection = (
                self.create_bucket_collection()
            )

    @with_config
    def run(self, *, config: RunConfig) -> "Results":
        """
        Runs the Job: conducts Interviews and returns their results.

        :param n: How many times to run each interview
        :param progress_bar: Whether to show a progress bar
        :param stop_on_exception: Stops the job if an exception is raised
        :param check_api_keys: Raises an error if API keys are invalid
        :param verbose: Prints extra messages
        :param remote_cache_description: Specifies a description for this group of entries in the remote cache
        :param remote_inference_description: Specifies a description for the remote inference job
        :param remote_inference_results_visibility: The initial visibility of the Results object on Coop. This will only be used for remote jobs!
        :param disable_remote_cache: If True, the job will not use remote cache. This only works for local jobs!
        :param disable_remote_inference: If True, the job will not use remote inference
        :param cache: A Cache object to store results
        :param bucket_collection: A BucketCollection object to track API calls
        :param key_lookup: A KeyLookup object to manage API keys
        """
        self._run(config)

        return asyncio.run(self._execute_with_remote_cache(run_job_async=False))

    @with_config
    async def run_async(self, *, config: RunConfig) -> "Results":
        """
        Runs the Job: conducts Interviews and returns their results.

        :param n: How many times to run each interview
        :param progress_bar: Whether to show a progress bar
        :param stop_on_exception: Stops the job if an exception is raised
        :param check_api_keys: Raises an error if API keys are invalid
        :param verbose: Prints extra messages
        :param remote_cache_description: Specifies a description for this group of entries in the remote cache
        :param remote_inference_description: Specifies a description for the remote inference job
        :param remote_inference_results_visibility: The initial visibility of the Results object on Coop. This will only be used for remote jobs!
        :param disable_remote_cache: If True, the job will not use remote cache. This only works for local jobs!
        :param disable_remote_inference: If True, the job will not use remote inference
        :param cache: A Cache object to store results
        :param bucket_collection: A BucketCollection object to track API calls
        :param key_lookup: A KeyLookup object to manage API keys
        """
        self._run(config)

        return await self._execute_with_remote_cache(run_job_async=True)

    def __repr__(self) -> str:
        """Return an eval-able string representation of the Jobs instance."""
        return f"Jobs(survey={repr(self.survey)}, agents={repr(self.agents)}, models={repr(self.models)}, scenarios={repr(self.scenarios)})"

    def _summary(self):
        return {
            "questions": len(self.survey),
            "agents": len(self.agents or [1]),
            "models": len(self.models or [1]),
            "scenarios": len(self.scenarios or [1]),
        }

    def __len__(self) -> int:
        """Return the number of interviews that will be conducted for one iteration of this job.
        An interview is the result of one survey, taken by one agent, with one model, with one scenario.

        >>> from edsl.jobs import Jobs
        >>> len(Jobs.example())
        4
        """
        number_of_interviews = (
            len(self.agents or [1])
            * len(self.scenarios or [1])
            * len(self.models or [1])
        )
        return number_of_interviews

    def to_dict(self, add_edsl_version=True):
        d = {
            "survey": self.survey.to_dict(add_edsl_version=add_edsl_version),
            "agents": [
                agent.to_dict(add_edsl_version=add_edsl_version)
                for agent in self.agents
            ],
            "models": [
                model.to_dict(add_edsl_version=add_edsl_version)
                for model in self.models
            ],
            "scenarios": [
                scenario.to_dict(add_edsl_version=add_edsl_version)
                for scenario in self.scenarios
            ],
        }
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = "Jobs"

        return d

    def table(self):
        return self.prompts().to_scenario_list().table()

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict) -> Jobs:
        """Creates a Jobs instance from a dictionary."""
        from edsl.surveys.Survey import Survey
        from edsl.agents.Agent import Agent
        from edsl.language_models.LanguageModel import LanguageModel
        from edsl.scenarios.Scenario import Scenario

        return cls(
            survey=Survey.from_dict(data["survey"]),
            agents=[Agent.from_dict(agent) for agent in data["agents"]],
            models=[LanguageModel.from_dict(model) for model in data["models"]],
            scenarios=[Scenario.from_dict(scenario) for scenario in data["scenarios"]],
        )

    def __eq__(self, other: Jobs) -> bool:
        """Return True if the Jobs instance is equal to another Jobs instance.

        >>> from edsl.jobs import Jobs
        >>> Jobs.example() == Jobs.example()
        True

        """
        return hash(self) == hash(other)

    @classmethod
    def example(
        cls,
        throw_exception_probability: float = 0.0,
        randomize: bool = False,
        test_model=False,
    ) -> Jobs:
        """Return an example Jobs instance.

        :param throw_exception_probability: the probability that an exception will be thrown when answering a question. This is useful for testing error handling.
        :param randomize: whether to randomize the job by adding a random string to the period
        :param test_model: whether to use a test model

        >>> Jobs.example()
        Jobs(...)

        """
        import random
        from uuid import uuid4
        from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice
        from edsl.agents.Agent import Agent
        from edsl.scenarios.Scenario import Scenario

        addition = "" if not randomize else str(uuid4())

        if test_model:
            from edsl.language_models.LanguageModel import LanguageModel

            m = LanguageModel.example(test_model=True)

        # (status, question, period)
        agent_answers = {
            ("Joyful", "how_feeling", "morning"): "OK",
            ("Joyful", "how_feeling", "afternoon"): "Great",
            ("Joyful", "how_feeling_yesterday", "morning"): "Great",
            ("Joyful", "how_feeling_yesterday", "afternoon"): "Good",
            ("Sad", "how_feeling", "morning"): "Terrible",
            ("Sad", "how_feeling", "afternoon"): "OK",
            ("Sad", "how_feeling_yesterday", "morning"): "OK",
            ("Sad", "how_feeling_yesterday", "afternoon"): "Terrible",
        }

        def answer_question_directly(self, question, scenario):
            """Return the answer to a question. This is a method that can be added to an agent."""

            if random.random() < throw_exception_probability:
                raise Exception("Error!")
            return agent_answers[
                (self.traits["status"], question.question_name, scenario["period"])
            ]

        sad_agent = Agent(traits={"status": "Sad"})
        joy_agent = Agent(traits={"status": "Joyful"})

        sad_agent.add_direct_question_answering_method(answer_question_directly)
        joy_agent.add_direct_question_answering_method(answer_question_directly)

        q1 = QuestionMultipleChoice(
            question_text="How are you this {{ period }}?",
            question_options=["Good", "Great", "OK", "Terrible"],
            question_name="how_feeling",
        )
        q2 = QuestionMultipleChoice(
            question_text="How were you feeling yesterday {{ period }}?",
            question_options=["Good", "Great", "OK", "Terrible"],
            question_name="how_feeling_yesterday",
        )
        from edsl.surveys.Survey import Survey
        from edsl.scenarios.ScenarioList import ScenarioList

        base_survey = Survey(questions=[q1, q2])

        scenario_list = ScenarioList(
            [
                Scenario({"period": f"morning{addition}"}),
                Scenario({"period": "afternoon"}),
            ]
        )
        if test_model:
            job = base_survey.by(m).by(scenario_list).by(joy_agent, sad_agent)
        else:
            job = base_survey.by(scenario_list).by(joy_agent, sad_agent)

        return job

    def code(self):
        """Return the code to create this instance."""
        raise NotImplementedError


def main():
    """Run the module's doctests."""
    from edsl.jobs.Jobs import Jobs
    from edsl.data.Cache import Cache

    job = Jobs.example()
    len(job) == 4
    results = job.run(cache=Cache())
    len(results) == 4
    results


if __name__ == "__main__":
    """Run the module's doctests."""
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
