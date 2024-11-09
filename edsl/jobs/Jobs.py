# """The Jobs class is a collection of agents, scenarios and models and one survey."""
from __future__ import annotations
import warnings
import requests
from itertools import product
from typing import Literal, Optional, Union, Sequence, Generator

from edsl.Base import Base

from edsl.exceptions import MissingAPIKeyError
from edsl.jobs.buckets.BucketCollection import BucketCollection
from edsl.jobs.interviews.Interview import Interview
from edsl.jobs.runners.JobsRunnerAsyncio import JobsRunnerAsyncio
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version

from edsl.data.RemoteCacheSync import RemoteCacheSync
from edsl.exceptions.coop import CoopServerResponseError


class Jobs(Base):
    """
    A collection of agents, scenarios and models and one survey.
    The actual running of a job is done by a `JobsRunner`, which is a subclass of `JobsRunner`.
    The `JobsRunner` is chosen by the user, and is stored in the `jobs_runner_name` attribute.
    """

    def __init__(
        self,
        survey: "Survey",
        agents: Optional[list["Agent"]] = None,
        models: Optional[list["LanguageModel"]] = None,
        scenarios: Optional[list["Scenario"]] = None,
    ):
        """Initialize a Jobs instance.

        :param survey: the survey to be used in the job
        :param agents: a list of agents
        :param models: a list of models
        :param scenarios: a list of scenarios
        """
        self.survey = survey
        self.agents: "AgentList" = agents
        self.scenarios: "ScenarioList" = scenarios
        self.models = models

        self.__bucket_collection = None

    # these setters and getters are used to ensure that the agents, models, and scenarios are stored as AgentList, ModelList, and ScenarioList objects

    @property
    def models(self):
        return self._models

    @models.setter
    def models(self, value):
        from edsl import ModelList

        if value:
            if not isinstance(value, ModelList):
                self._models = ModelList(value)
            else:
                self._models = value
        else:
            self._models = ModelList([])

    @property
    def agents(self):
        return self._agents

    @agents.setter
    def agents(self, value):
        from edsl import AgentList

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
        from edsl import ScenarioList

        if value:
            if not isinstance(value, ScenarioList):
                self._scenarios = ScenarioList(value)
            else:
                self._scenarios = value
        else:
            self._scenarios = ScenarioList([])

    def by(
        self,
        *args: Union[
            "Agent",
            "Scenario",
            "LanguageModel",
            Sequence[Union["Agent", "Scenario", "LanguageModel"]],
        ],
    ) -> Jobs:
        """
        Add Agents, Scenarios and LanguageModels to a job. If no objects of this type exist in the Jobs instance, it stores the new objects as a list in the corresponding attribute. Otherwise, it combines the new objects with existing objects using the object's `__add__` method.

        This 'by' is intended to create a fluent interface.

        >>> from edsl import Survey
        >>> from edsl import QuestionFreeText
        >>> q = QuestionFreeText(question_name="name", question_text="What is your name?")
        >>> j = Jobs(survey = Survey(questions=[q]))
        >>> j
        Jobs(survey=Survey(...), agents=AgentList([]), models=ModelList([]), scenarios=ScenarioList([]))
        >>> from edsl import Agent; a = Agent(traits = {"status": "Sad"})
        >>> j.by(a).agents
        AgentList([Agent(traits = {'status': 'Sad'})])

        :param args: objects or a sequence (list, tuple, ...) of objects of the same type

        Notes:
        - all objects must implement the 'get_value', 'set_value', and `__add__` methods
        - agents: traits of new agents are combined with traits of existing agents. New and existing agents should not have overlapping traits, and do not increase the # agents in the instance
        - scenarios: traits of new scenarios are combined with traits of old existing. New scenarios will overwrite overlapping traits, and do not increase the number of scenarios in the instance
        - models: new models overwrite old models.
        """
        passed_objects = self._turn_args_to_list(
            args
        )  # objects can also be passed comma-separated

        current_objects, objects_key = self._get_current_objects_of_this_type(
            passed_objects[0]
        )

        if not current_objects:
            new_objects = passed_objects
        else:
            new_objects = self._merge_objects(passed_objects, current_objects)

        setattr(self, objects_key, new_objects)  # update the job
        return self

    def prompts(self) -> "Dataset":
        """Return a Dataset of prompts that will be used.


        >>> from edsl.jobs import Jobs
        >>> Jobs.example().prompts()
        Dataset(...)
        """
        from edsl import Coop

        c = Coop()
        price_lookup = c.fetch_prices()

        interviews = self.interviews()
        # data = []
        interview_indices = []
        question_names = []
        user_prompts = []
        system_prompts = []
        scenario_indices = []
        agent_indices = []
        models = []
        costs = []
        from edsl.results.Dataset import Dataset

        for interview_index, interview in enumerate(interviews):
            invigilators = [
                interview._get_invigilator(question)
                for question in self.survey.questions
            ]
            for _, invigilator in enumerate(invigilators):
                prompts = invigilator.get_prompts()
                user_prompt = prompts["user_prompt"]
                system_prompt = prompts["system_prompt"]
                user_prompts.append(user_prompt)
                system_prompts.append(system_prompt)
                agent_index = self.agents.index(invigilator.agent)
                agent_indices.append(agent_index)
                interview_indices.append(interview_index)
                scenario_index = self.scenarios.index(invigilator.scenario)
                scenario_indices.append(scenario_index)
                models.append(invigilator.model.model)
                question_names.append(invigilator.question.question_name)

                prompt_cost = self.estimate_prompt_cost(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    price_lookup=price_lookup,
                    inference_service=invigilator.model._inference_service_,
                    model=invigilator.model.model,
                )
                costs.append(prompt_cost["cost_usd"])

        d = Dataset(
            [
                {"user_prompt": user_prompts},
                {"system_prompt": system_prompts},
                {"interview_index": interview_indices},
                {"question_name": question_names},
                {"scenario_index": scenario_indices},
                {"agent_index": agent_indices},
                {"model": models},
                {"estimated_cost": costs},
            ]
        )
        return d

    def show_prompts(self, all=False) -> None:
        """Print the prompts."""
        if all:
            self.prompts().to_scenario_list().print(format="rich")
        else:
            self.prompts().select(
                "user_prompt", "system_prompt"
            ).to_scenario_list().print(format="rich")

    @staticmethod
    def estimate_prompt_cost(
        system_prompt: str,
        user_prompt: str,
        price_lookup: dict,
        inference_service: str,
        model: str,
    ) -> dict:
        """Estimates the cost of a prompt. Takes piping into account."""
        import math

        def get_piping_multiplier(prompt: str):
            """Returns 2 if a prompt includes Jinja braces, and 1 otherwise."""

            if "{{" in prompt and "}}" in prompt:
                return 2
            return 1

        # Look up prices per token
        key = (inference_service, model)

        try:
            relevant_prices = price_lookup[key]

            service_input_token_price = float(
                relevant_prices["input"]["service_stated_token_price"]
            )
            service_input_token_qty = float(
                relevant_prices["input"]["service_stated_token_qty"]
            )
            input_price_per_token = service_input_token_price / service_input_token_qty

            service_output_token_price = float(
                relevant_prices["output"]["service_stated_token_price"]
            )
            service_output_token_qty = float(
                relevant_prices["output"]["service_stated_token_qty"]
            )
            output_price_per_token = (
                service_output_token_price / service_output_token_qty
            )

        except KeyError:
            # A KeyError is likely to occur if we cannot retrieve prices (the price_lookup dict is empty)
            # Use a sensible default

            import warnings

            warnings.warn(
                "Price data could not be retrieved. Using default estimates for input and output token prices. Input: $0.15 / 1M tokens; Output: $0.60 / 1M tokens"
            )
            input_price_per_token = 0.00000015  # $0.15 / 1M tokens
            output_price_per_token = 0.00000060  # $0.60 / 1M tokens

        # Compute the number of characters (double if the question involves piping)
        user_prompt_chars = len(str(user_prompt)) * get_piping_multiplier(
            str(user_prompt)
        )
        system_prompt_chars = len(str(system_prompt)) * get_piping_multiplier(
            str(system_prompt)
        )

        # Convert into tokens (1 token approx. equals 4 characters)
        input_tokens = (user_prompt_chars + system_prompt_chars) // 4

        output_tokens = math.ceil(0.75 * input_tokens)

        cost = (
            input_tokens * input_price_per_token
            + output_tokens * output_price_per_token
        )

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        }

    def estimate_job_cost_from_external_prices(
        self, price_lookup: dict, iterations: int = 1
    ) -> dict:
        """
        Estimates the cost of a job according to the following assumptions:

        - 1 token = 4 characters.
        - For each prompt, output tokens = input tokens * 0.75, rounded up to the nearest integer.

        price_lookup is an external pricing dictionary.
        """

        import pandas as pd

        interviews = self.interviews()
        data = []
        for interview in interviews:
            invigilators = [
                interview._get_invigilator(question)
                for question in self.survey.questions
            ]
            for invigilator in invigilators:
                prompts = invigilator.get_prompts()

                # By this point, agent and scenario data has already been added to the prompts
                user_prompt = prompts["user_prompt"]
                system_prompt = prompts["system_prompt"]
                inference_service = invigilator.model._inference_service_
                model = invigilator.model.model

                prompt_cost = self.estimate_prompt_cost(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    price_lookup=price_lookup,
                    inference_service=inference_service,
                    model=model,
                )

                data.append(
                    {
                        "user_prompt": user_prompt,
                        "system_prompt": system_prompt,
                        "estimated_input_tokens": prompt_cost["input_tokens"],
                        "estimated_output_tokens": prompt_cost["output_tokens"],
                        "estimated_cost_usd": prompt_cost["cost_usd"],
                        "inference_service": inference_service,
                        "model": model,
                    }
                )

        df = pd.DataFrame.from_records(data)

        df = (
            df.groupby(["inference_service", "model"])
            .agg(
                {
                    "estimated_cost_usd": "sum",
                    "estimated_input_tokens": "sum",
                    "estimated_output_tokens": "sum",
                }
            )
            .reset_index()
        )
        df["estimated_cost_usd"] = df["estimated_cost_usd"] * iterations
        df["estimated_input_tokens"] = df["estimated_input_tokens"] * iterations
        df["estimated_output_tokens"] = df["estimated_output_tokens"] * iterations

        estimated_costs_by_model = df.to_dict("records")

        estimated_total_cost = sum(
            model["estimated_cost_usd"] for model in estimated_costs_by_model
        )
        estimated_total_input_tokens = sum(
            model["estimated_input_tokens"] for model in estimated_costs_by_model
        )
        estimated_total_output_tokens = sum(
            model["estimated_output_tokens"] for model in estimated_costs_by_model
        )

        output = {
            "estimated_total_cost_usd": estimated_total_cost,
            "estimated_total_input_tokens": estimated_total_input_tokens,
            "estimated_total_output_tokens": estimated_total_output_tokens,
            "model_costs": estimated_costs_by_model,
        }

        return output

    def estimate_job_cost(self, iterations: int = 1) -> dict:
        """
        Estimates the cost of a job according to the following assumptions:

        - 1 token = 4 characters.
        - For each prompt, output tokens = input tokens * 0.75, rounded up to the nearest integer.

        Fetches prices from Coop.
        """
        from edsl import Coop

        c = Coop()
        price_lookup = c.fetch_prices()

        return self.estimate_job_cost_from_external_prices(
            price_lookup=price_lookup, iterations=iterations
        )

    @staticmethod
    def compute_job_cost(job_results: "Results") -> float:
        """
        Computes the cost of a completed job in USD.
        """
        total_cost = 0
        for result in job_results:
            for key in result.raw_model_response:
                if key.endswith("_cost"):
                    result_cost = result.raw_model_response[key]

                    question_name = key.removesuffix("_cost")
                    cache_used = result.cache_used_dict[question_name]

                    if isinstance(result_cost, (int, float)) and not cache_used:
                        total_cost += result_cost

        return total_cost

    @staticmethod
    def _get_container_class(object):
        from edsl.agents.AgentList import AgentList
        from edsl.agents.Agent import Agent
        from edsl.scenarios.Scenario import Scenario
        from edsl.scenarios.ScenarioList import ScenarioList
        from edsl.language_models.ModelList import ModelList

        if isinstance(object, Agent):
            return AgentList
        elif isinstance(object, Scenario):
            return ScenarioList
        elif isinstance(object, ModelList):
            return ModelList
        else:
            return list

    @staticmethod
    def _turn_args_to_list(args):
        """Return a list of the first argument if it is a sequence, otherwise returns a list of all the arguments.

        Example:

        >>> Jobs._turn_args_to_list([1,2,3])
        [1, 2, 3]

        """

        def did_user_pass_a_sequence(args):
            """Return True if the user passed a sequence, False otherwise.

            Example:

            >>> did_user_pass_a_sequence([1,2,3])
            True

            >>> did_user_pass_a_sequence(1)
            False
            """
            return len(args) == 1 and isinstance(args[0], Sequence)

        if did_user_pass_a_sequence(args):
            container_class = Jobs._get_container_class(args[0][0])
            return container_class(args[0])
        else:
            container_class = Jobs._get_container_class(args[0])
            return container_class(args)

    def _get_current_objects_of_this_type(
        self, object: Union["Agent", "Scenario", "LanguageModel"]
    ) -> tuple[list, str]:
        from edsl.agents.Agent import Agent
        from edsl.scenarios.Scenario import Scenario
        from edsl.language_models.LanguageModel import LanguageModel

        """Return the current objects of the same type as the first argument.

        >>> from edsl.jobs import Jobs
        >>> j = Jobs.example()
        >>> j._get_current_objects_of_this_type(j.agents[0])
        (AgentList([Agent(traits = {'status': 'Joyful'}), Agent(traits = {'status': 'Sad'})]), 'agents')
        """
        class_to_key = {
            Agent: "agents",
            Scenario: "scenarios",
            LanguageModel: "models",
        }
        for class_type in class_to_key:
            if isinstance(object, class_type) or issubclass(
                object.__class__, class_type
            ):
                key = class_to_key[class_type]
                break
        else:
            raise ValueError(
                f"First argument must be an Agent, Scenario, or LanguageModel, not {object}"
            )
        current_objects = getattr(self, key, None)
        return current_objects, key

    @staticmethod
    def _get_empty_container_object(object):
        from edsl import AgentList
        from edsl import Agent
        from edsl import Scenario
        from edsl import ScenarioList

        if isinstance(object, Agent):
            return AgentList([])
        elif isinstance(object, Scenario):
            return ScenarioList([])
        else:
            return []

    @staticmethod
    def _merge_objects(passed_objects, current_objects) -> list:
        """
        Combine all the existing objects with the new objects.

        For example, if the user passes in 3 agents,
        and there are 2 existing agents, this will create 6 new agents

        >>> Jobs(survey = [])._merge_objects([1,2,3], [4,5,6])
        [5, 6, 7, 6, 7, 8, 7, 8, 9]
        """
        new_objects = Jobs._get_empty_container_object(passed_objects[0])
        for current_object in current_objects:
            for new_object in passed_objects:
                new_objects.append(current_object + new_object)
        return new_objects

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
        if hasattr(self, "_interviews"):
            return self._interviews
        else:
            return list(self._create_interviews())

    @classmethod
    def from_interviews(cls, interview_list):
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

    def _create_interviews(self) -> Generator[Interview, None, None]:
        """
        Generate interviews.

        Note that this sets the agents, model and scenarios if they have not been set. This is a side effect of the method.
        This is useful because a user can create a job without setting the agents, models, or scenarios, and the job will still run,
        with us filling in defaults.


        """
        # if no agents, models, or scenarios are set, set them to defaults
        from edsl.agents.Agent import Agent
        from edsl.language_models.registry import Model
        from edsl.scenarios.Scenario import Scenario

        self.agents = self.agents or [Agent()]
        self.models = self.models or [Model()]
        self.scenarios = self.scenarios or [Scenario()]
        for agent, scenario, model in product(self.agents, self.scenarios, self.models):
            yield Interview(
                survey=self.survey,
                agent=agent,
                scenario=scenario,
                model=model,
                skip_retry=self.skip_retry,
                raise_validation_errors=self.raise_validation_errors,
            )

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
        bucket_collection = BucketCollection()
        for model in self.models:
            bucket_collection.add_model(model)
        return bucket_collection

    @property
    def bucket_collection(self) -> BucketCollection:
        """Return the bucket collection. If it does not exist, create it."""
        if self.__bucket_collection is None:
            self.__bucket_collection = self.create_bucket_collection()
        return self.__bucket_collection

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

        return dict_hash(self._to_dict())

    def _output(self, message) -> None:
        """Check if a Job is verbose. If so, print the message."""
        if hasattr(self, "verbose") and self.verbose:
            print(message)

    def _check_parameters(self, strict=False, warn=False) -> None:
        """Check if the parameters in the survey and scenarios are consistent.

        >>> from edsl import QuestionFreeText
        >>> from edsl import Survey
        >>> from edsl import Scenario
        >>> q = QuestionFreeText(question_text = "{{poo}}", question_name = "ugly_question")
        >>> j = Jobs(survey = Survey(questions=[q]))
        >>> with warnings.catch_warnings(record=True) as w:
        ...     j._check_parameters(warn = True)
        ...     assert len(w) == 1
        ...     assert issubclass(w[-1].category, UserWarning)
        ...     assert "The following parameters are in the survey but not in the scenarios" in str(w[-1].message)

        >>> q = QuestionFreeText(question_text = "{{poo}}", question_name = "ugly_question")
        >>> s = Scenario({'plop': "A", 'poo': "B"})
        >>> j = Jobs(survey = Survey(questions=[q])).by(s)
        >>> j._check_parameters(strict = True)
        Traceback (most recent call last):
        ...
        ValueError: The following parameters are in the scenarios but not in the survey: {'plop'}

        >>> q = QuestionFreeText(question_text = "Hello", question_name = "ugly_question")
        >>> s = Scenario({'ugly_question': "B"})
        >>> j = Jobs(survey = Survey(questions=[q])).by(s)
        >>> j._check_parameters()
        Traceback (most recent call last):
        ...
        ValueError: The following names are in both the survey question_names and the scenario keys: {'ugly_question'}. This will create issues.
        """
        survey_parameters: set = self.survey.parameters
        scenario_parameters: set = self.scenarios.parameters

        msg0, msg1, msg2 = None, None, None

        # look for key issues
        if intersection := set(self.scenarios.parameters) & set(
            self.survey.question_names
        ):
            msg0 = f"The following names are in both the survey question_names and the scenario keys: {intersection}. This will create issues."

            raise ValueError(msg0)

        if in_survey_but_not_in_scenarios := survey_parameters - scenario_parameters:
            msg1 = f"The following parameters are in the survey but not in the scenarios: {in_survey_but_not_in_scenarios}"
        if in_scenarios_but_not_in_survey := scenario_parameters - survey_parameters:
            msg2 = f"The following parameters are in the scenarios but not in the survey: {in_scenarios_but_not_in_survey}"

        if msg1 or msg2:
            message = "\n".join(filter(None, [msg1, msg2]))
            if strict:
                raise ValueError(message)
            else:
                if warn:
                    warnings.warn(message)

        if self.scenarios.has_jinja_braces:
            warnings.warn(
                "The scenarios have Jinja braces ({{ and }}). Converting to '<<' and '>>'. If you want a different conversion, use the convert_jinja_braces method first to modify the scenario."
            )
            self.scenarios = self.scenarios.convert_jinja_braces()

    @property
    def skip_retry(self):
        if not hasattr(self, "_skip_retry"):
            return False
        return self._skip_retry

    @property
    def raise_validation_errors(self):
        if not hasattr(self, "_raise_validation_errors"):
            return False
        return self._raise_validation_errors

    def create_remote_inference_job(
        self,
        iterations: int = 1,
        remote_inference_description: Optional[str] = None,
        remote_inference_results_visibility: Optional[VisibilityType] = "unlisted",
    ):
        """ """
        from edsl.coop.coop import Coop

        coop = Coop()
        self._output("Remote inference activated. Sending job to server...")
        remote_job_creation_data = coop.remote_inference_create(
            self,
            description=remote_inference_description,
            status="queued",
            iterations=iterations,
            initial_results_visibility=remote_inference_results_visibility,
        )
        job_uuid = remote_job_creation_data.get("uuid")
        print(f"Job sent to server. (Job uuid={job_uuid}).")
        return remote_job_creation_data

    @staticmethod
    def check_status(job_uuid):
        from edsl.coop.coop import Coop

        coop = Coop()
        return coop.remote_inference_get(job_uuid)

    def poll_remote_inference_job(
        self, remote_job_creation_data: dict
    ) -> Union[Results, None]:
        from edsl.coop.coop import Coop
        import time
        from datetime import datetime
        from edsl.config import CONFIG

        expected_parrot_url = CONFIG.get("EXPECTED_PARROT_URL")

        job_uuid = remote_job_creation_data.get("uuid")

        coop = Coop()
        job_in_queue = True
        while job_in_queue:
            remote_job_data = coop.remote_inference_get(job_uuid)
            status = remote_job_data.get("status")
            if status == "cancelled":
                print("\r" + " " * 80 + "\r", end="")
                print("Job cancelled by the user.")
                print(
                    f"See {expected_parrot_url}/home/remote-inference for more details."
                )
                return None
            elif status == "failed":
                print("\r" + " " * 80 + "\r", end="")
                print("Job failed.")
                print(
                    f"See {expected_parrot_url}/home/remote-inference for more details."
                )
                return None
            elif status == "completed":
                results_uuid = remote_job_data.get("results_uuid")
                results = coop.get(results_uuid, expected_object_type="results")
                print("\r" + " " * 80 + "\r", end="")
                url = f"{expected_parrot_url}/content/{results_uuid}"
                print(f"Job completed and Results stored on Coop: {url}.")
                return results
            else:
                duration = 5
                time_checked = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                start_time = time.time()
                i = 0
                while time.time() - start_time < duration:
                    print(
                        f"\r{frames[i % len(frames)]} Job status: {status} - last update: {time_checked}",
                        end="",
                        flush=True,
                    )
                    time.sleep(0.1)
                    i += 1

    def use_remote_inference(self, disable_remote_inference: bool):
        if disable_remote_inference:
            return False
        if not disable_remote_inference:
            try:
                from edsl import Coop

                user_edsl_settings = Coop().edsl_settings
                return user_edsl_settings.get("remote_inference", False)
            except requests.ConnectionError:
                pass
            except CoopServerResponseError as e:
                pass

        return False

    def use_remote_cache(self, disable_remote_cache: bool):
        if disable_remote_cache:
            return False
        if not disable_remote_cache:
            try:
                from edsl import Coop

                user_edsl_settings = Coop().edsl_settings
                return user_edsl_settings.get("remote_caching", False)
            except requests.ConnectionError:
                pass
            except CoopServerResponseError as e:
                pass

        return False

    def check_api_keys(self):
        from edsl import Model

        for model in self.models + [Model()]:
            if not model.has_valid_api_key():
                raise MissingAPIKeyError(
                    model_name=str(model.model),
                    inference_service=model._inference_service_,
                )

    def get_missing_api_keys(self) -> set:
        """
        Returns a list of the api keys that a user needs to run this job, but does not currently have in their .env file.
        """

        missing_api_keys = set()

        from edsl import Model
        from edsl.enums import service_to_api_keyname

        for model in self.models + [Model()]:
            if not model.has_valid_api_key():
                key_name = service_to_api_keyname.get(
                    model._inference_service_, "NOT FOUND"
                )
                missing_api_keys.add(key_name)

        return missing_api_keys

    def user_has_all_model_keys(self):
        """
        Returns True if the user has all model keys required to run their job.

        Otherwise, returns False.
        """

        try:
            self.check_api_keys()
            return True
        except MissingAPIKeyError:
            return False
        except Exception:
            raise

    def user_has_ep_api_key(self):
        """
        Returns True if the user has an EXPECTED_PARROT_API_KEY in their env.

        Otherwise, returns False.
        """

        import os

        coop_api_key = os.getenv("EXPECTED_PARROT_API_KEY")

        if coop_api_key is not None:
            return True
        else:
            return False

    def needs_external_llms(self) -> bool:
        """
        Returns True if the job needs external LLMs to run.

        Otherwise, returns False.
        """
        # These cases are necessary to skip the API key check during doctests

        # Accounts for Results.example()
        all_agents_answer_questions_directly = len(self.agents) > 0 and all(
            [hasattr(a, "answer_question_directly") for a in self.agents]
        )

        # Accounts for InterviewExceptionEntry.example()
        only_model_is_test = set([m.model for m in self.models]) == set(["test"])

        # Accounts for Survey.__call__
        all_questions_are_functional = set(
            [q.question_type for q in self.survey.questions]
        ) == set(["functional"])

        if (
            all_agents_answer_questions_directly
            or only_model_is_test
            or all_questions_are_functional
        ):
            return False
        else:
            return True

    def run(
        self,
        n: int = 1,
        progress_bar: bool = False,
        stop_on_exception: bool = False,
        cache: Union[Cache, bool] = None,
        check_api_keys: bool = False,
        sidecar_model: Optional[LanguageModel] = None,
        verbose: bool = False,
        print_exceptions=True,
        remote_cache_description: Optional[str] = None,
        remote_inference_description: Optional[str] = None,
        remote_inference_results_visibility: Optional[
            Literal["private", "public", "unlisted"]
        ] = "unlisted",
        skip_retry: bool = False,
        raise_validation_errors: bool = False,
        disable_remote_cache: bool = False,
        disable_remote_inference: bool = False,
    ) -> Results:
        """
        Runs the Job: conducts Interviews and returns their results.

        :param n: How many times to run each interview
        :param progress_bar: Whether to show a progress bar
        :param stop_on_exception: Stops the job if an exception is raised
        :param cache: A Cache object to store results
        :param check_api_keys: Raises an error if API keys are invalid
        :param verbose: Prints extra messages
        :param remote_cache_description: Specifies a description for this group of entries in the remote cache
        :param remote_inference_description: Specifies a description for the remote inference job
        :param remote_inference_results_visibility: The initial visibility of the Results object on Coop. This will only be used for remote jobs!
        :param disable_remote_cache: If True, the job will not use remote cache. This only works for local jobs!
        :param disable_remote_inference: If True, the job will not use remote inference
        """
        from edsl.coop.coop import Coop

        self._check_parameters()
        self._skip_retry = skip_retry
        self._raise_validation_errors = raise_validation_errors

        self.verbose = verbose

        if (
            not self.user_has_all_model_keys()
            and not self.user_has_ep_api_key()
            and self.needs_external_llms()
        ):
            import secrets
            from dotenv import load_dotenv
            from edsl import CONFIG
            from edsl.coop.coop import Coop
            from edsl.utilities.utilities import write_api_key_to_env

            missing_api_keys = self.get_missing_api_keys()

            edsl_auth_token = secrets.token_urlsafe(16)

            print("You're missing some of the API keys needed to run this job:")
            for api_key in missing_api_keys:
                print(f"     🔑 {api_key}")
            print(
                "\nYou can either add the missing keys to your .env file, or use remote inference."
            )
            print("Remote inference allows you to run jobs on our server.")
            print("\n🚀 To use remote inference, sign up at the following link:")
            print(
                f"    {CONFIG.EXPECTED_PARROT_URL}/login?edsl_auth_token={edsl_auth_token}"
            )
            print(
                "\nOnce you log in, we will automatically retrieve your Expected Parrot API key and continue your job remotely."
            )

            coop = Coop()
            api_key = coop._poll_for_api_key(edsl_auth_token)

            if api_key is None:
                print("\nTimed out waiting for login. Please try again.")
                return

            write_api_key_to_env(api_key)
            print("✨ API key retrieved and written to .env file.\n")

            # Retrieve API key so we can continue running the job
            load_dotenv()

        if remote_inference := self.use_remote_inference(disable_remote_inference):
            remote_job_creation_data = self.create_remote_inference_job(
                iterations=n,
                remote_inference_description=remote_inference_description,
                remote_inference_results_visibility=remote_inference_results_visibility,
            )
            results = self.poll_remote_inference_job(remote_job_creation_data)
            if results is None:
                self._output("Job failed.")
            return results

        if check_api_keys:
            self.check_api_keys()

        # handle cache
        if cache is None or cache is True:
            from edsl.data.CacheHandler import CacheHandler

            cache = CacheHandler().get_cache()
        if cache is False:
            from edsl.data.Cache import Cache

            cache = Cache()

        remote_cache = self.use_remote_cache(disable_remote_cache)
        with RemoteCacheSync(
            coop=Coop(),
            cache=cache,
            output_func=self._output,
            remote_cache=remote_cache,
            remote_cache_description=remote_cache_description,
        ) as r:
            results = self._run_local(
                n=n,
                progress_bar=progress_bar,
                cache=cache,
                stop_on_exception=stop_on_exception,
                sidecar_model=sidecar_model,
                print_exceptions=print_exceptions,
                raise_validation_errors=raise_validation_errors,
            )

        results.cache = cache.new_entries_cache()
        return results

    def _run_local(self, *args, **kwargs):
        """Run the job locally."""

        results = JobsRunnerAsyncio(self).run(*args, **kwargs)
        return results

    async def run_async(self, cache=None, n=1, **kwargs):
        """Run asynchronously."""
        results = await JobsRunnerAsyncio(self).run_async(cache=cache, n=n, **kwargs)
        return results

    def all_question_parameters(self):
        """Return all the fields in the questions in the survey.
        >>> from edsl.jobs import Jobs
        >>> Jobs.example().all_question_parameters()
        {'period'}
        """
        return set.union(*[question.parameters for question in self.survey.questions])

    #######################
    # Dunder methods
    #######################
    def print(self):
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __repr__(self) -> str:
        """Return an eval-able string representation of the Jobs instance."""
        return f"Jobs(survey={repr(self.survey)}, agents={repr(self.agents)}, models={repr(self.models)}, scenarios={repr(self.scenarios)})"

    def _repr_html_(self) -> str:
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __len__(self) -> int:
        """Return the maximum number of questions that will be asked while running this job.
        Note that this is the maximum number of questions, not the actual number of questions that will be asked, as some questions may be skipped.

        >>> from edsl.jobs import Jobs
        >>> len(Jobs.example())
        8
        """
        number_of_questions = (
            len(self.agents or [1])
            * len(self.scenarios or [1])
            * len(self.models or [1])
            * len(self.survey)
        )
        return number_of_questions

    #######################
    # Serialization methods
    #######################

    def _to_dict(self):
        return {
            "survey": self.survey._to_dict(),
            "agents": [agent._to_dict() for agent in self.agents],
            "models": [model._to_dict() for model in self.models],
            "scenarios": [scenario._to_dict() for scenario in self.scenarios],
        }

    @add_edsl_version
    def to_dict(self) -> dict:
        """Convert the Jobs instance to a dictionary."""
        return self._to_dict()

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict) -> Jobs:
        """Creates a Jobs instance from a dictionary."""
        from edsl import Survey
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
        return self.to_dict() == other.to_dict()

    #######################
    # Example methods
    #######################
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
        from edsl.questions import QuestionMultipleChoice
        from edsl.agents.Agent import Agent
        from edsl.scenarios.Scenario import Scenario

        addition = "" if not randomize else str(uuid4())

        if test_model:
            from edsl.language_models import LanguageModel

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
        from edsl import Survey, ScenarioList

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

    def rich_print(self):
        """Print a rich representation of the Jobs instance."""
        from rich.table import Table

        table = Table(title="Jobs")
        table.add_column("Jobs")
        table.add_row(self.survey.rich_print())
        return table

    def code(self):
        """Return the code to create this instance."""
        raise NotImplementedError


def main():
    """Run the module's doctests."""
    from edsl.jobs import Jobs
    from edsl.data.Cache import Cache

    job = Jobs.example()
    len(job) == 8
    results = job.run(cache=Cache())
    len(results) == 8
    results


if __name__ == "__main__":
    """Run the module's doctests."""
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
