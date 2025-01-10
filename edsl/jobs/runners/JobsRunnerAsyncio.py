from __future__ import annotations
import time
import asyncio
import threading
import warnings
from typing import TYPE_CHECKING
from edsl.logging_config import setup_logging
import logging

from edsl.results.Results import Results
from edsl.jobs.runners.JobsRunnerStatus import JobsRunnerStatus
from edsl.jobs.tasks.TaskHistory import TaskHistory
from edsl.utilities.decorators import jupyter_nb_handler
from edsl.jobs.async_interview_runner import AsyncInterviewRunner
from edsl.jobs.data_structures import RunEnvironment, RunParameters, RunConfig

if TYPE_CHECKING:
    from edsl.jobs.Jobs import Jobs


class JobsRunnerAsyncio:
    """A class for running a collection of interviews asynchronously.

    It gets instaniated from a Jobs object.
    The Jobs object is a collection of interviews that are to be run.
    """

    def __init__(self, jobs: "Jobs", environment: RunEnvironment):
        setup_logging()
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initializing JobsRunnerAsyncio with {len(jobs)} jobs")
        self.jobs = jobs
        self.environment = environment

    def __len__(self):
        return len(self.jobs)

    async def run_async(self, parameters: RunParameters) -> Results:
        """Used for some other modules that have a non-standard way of running interviews."""

        self.environment.jobs_runner_status = JobsRunnerStatus(self, n=parameters.n)
        data = []
        task_history = TaskHistory(include_traceback=False)

        run_config = RunConfig(parameters=parameters, environment=self.environment)
        result_generator = AsyncInterviewRunner(self.jobs, run_config)

        async for result, interview in result_generator.run():
            data.append(result)
            task_history.add_interview(interview)

        return Results(survey=self.jobs.survey, task_history=task_history, data=data)

    def simple_run(self):
        data = asyncio.run(self.run_async())
        return Results(survey=self.jobs.survey, data=data)

    @jupyter_nb_handler
    async def run(self, parameters: RunParameters) -> Results:
        """Runs a collection of interviews, handling both async and sync contexts."""

        run_config = RunConfig(parameters=parameters, environment=self.environment)

        self.start_time = time.monotonic()
        self.completed = False

        from edsl.coop import Coop

        coop = Coop()
        endpoint_url = coop.get_progress_bar_url()

        def set_up_jobs_runner_status(jobs_runner_status):
            if jobs_runner_status is not None:
                return jobs_runner_status(
                    self,
                    n=parameters.n,
                    endpoint_url=endpoint_url,
                    job_uuid=parameters.job_uuid,
                )
            else:
                return JobsRunnerStatus(
                    self,
                    n=parameters.n,
                    endpoint_url=endpoint_url,
                    job_uuid=parameters.job_uuid,
                )

        run_config.environment.jobs_runner_status = set_up_jobs_runner_status(
            self.environment.jobs_runner_status
        )

        async def get_results(results) -> None:
            """Conducted the interviews and append to the results list."""
            result_generator = AsyncInterviewRunner(self.jobs, run_config)
            async for result, interview in result_generator.run():
                results.append(result)
                results.task_history.add_interview(interview)

            self.completed = True

        def run_progress_bar(stop_event, jobs_runner_status) -> None:
            """Runs the progress bar in a separate thread."""
            jobs_runner_status.update_progress(stop_event)

        def set_up_progress_bar(progress_bar: bool, jobs_runner_status):
            progress_thread = None
            if progress_bar and jobs_runner_status.has_ep_api_key():
                jobs_runner_status.setup()
                progress_thread = threading.Thread(
                    target=run_progress_bar, args=(stop_event, jobs_runner_status)
                )
                progress_thread.start()
            elif progress_bar:
                warnings.warn(
                    "You need an Expected Parrot API key to view job progress bars."
                )
            return progress_thread

        results = Results(
            survey=self.jobs.survey,
            data=[],
            task_history=TaskHistory(),
            cache=self.environment.cache.new_entries_cache(),
        )
        stop_event = threading.Event()
        progress_thread = set_up_progress_bar(
            parameters.progress_bar, run_config.environment.jobs_runner_status
        )

        exception_to_raise = None
        try:
            await get_results(results)
        except KeyboardInterrupt:
            print("Keyboard interrupt received. Stopping gracefully...")
            stop_event.set()
        except Exception as e:
            if parameters.stop_on_exception:
                exception_to_raise = e
            stop_event.set()
        finally:
            stop_event.set()
            if progress_thread is not None:
                progress_thread.join()

            if exception_to_raise:
                raise exception_to_raise

            results.cache = self.environment.cache.new_entries_cache()
            results.bucket_collection = self.environment.bucket_collection

            from edsl.jobs.results_exceptions_handler import ResultsExceptionsHandler

            results_exceptions_handler = ResultsExceptionsHandler(results, parameters)

            results_exceptions_handler.handle_exceptions()
            return results
