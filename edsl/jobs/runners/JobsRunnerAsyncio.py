from __future__ import annotations
import time
import asyncio
import threading
import warnings
from typing import (
    Coroutine,
    List,
    AsyncGenerator,
    Optional,
    Union,
    Generator,
    Type,
    TYPE_CHECKING,
)
from uuid import UUID
from collections import UserList

from edsl.results.Results import Results
from edsl.jobs.interviews.Interview import Interview
from edsl.jobs.runners.JobsRunnerStatus import JobsRunnerStatus, JobsRunnerStatusBase

from edsl.jobs.tasks.TaskHistory import TaskHistory
from edsl.jobs.buckets.BucketCollection import BucketCollection
from edsl.utilities.decorators import jupyter_nb_handler
from edsl.data.Cache import Cache
from edsl.results.Result import Result
from edsl.language_models.LanguageModel import LanguageModel

from edsl.data_transfer_models import EDSLResultObjectInput

if TYPE_CHECKING:
    from edsl.language_models.key_management.KeyLookup import KeyLookup


# class StatusTracker(UserList):
#     def __init__(self, total_tasks: int):
#         self.total_tasks = total_tasks
#         super().__init__()

#     def current_status(self):
#         return print(f"Completed: {len(self.data)} of {self.total_tasks}", end="\r")


class JobsRunnerAsyncio:
    """A class for running a collection of interviews asynchronously.

    It gets instaniated from a Jobs object.
    The Jobs object is a collection of interviews that are to be run.
    """

    def __init__(
        self,
        jobs: "Jobs",
        bucket_collection: "BucketCollection",
        key_lookup: Optional[KeyLookup] = None,
        cache: Optional[Cache] = None,
    ):
        self.jobs = jobs
        self.interviews: List["Interview"] = jobs.interviews()

        # These are running environment configuration parameters
        self.cache = cache
        self.bucket_collection: "BucketCollection" = bucket_collection
        self.key_lookup = key_lookup

        # total_interviews is to deal with the n = ... possibility of running the same interview multiple times
        self.total_interviews: List["Interview"] = []
        self._initialized = threading.Event()

        from edsl.config import CONFIG

        self.MAX_CONCURRENT = int(CONFIG.get("EDSL_MAX_CONCURRENT_TASKS"))

    async def run_async_generator(self) -> AsyncGenerator["Result", None]:
        """Creates and processes tasks asynchronously, yielding results as they complete.

        Tasks are created and processed in a streaming fashion rather than building the full list upfront.
        Results are yielded as soon as they are available.

        :param n: how many times to run each interview
        :param stop_on_exception: Whether to stop the interview if an exception is raised
        :param total_interviews: A list of interviews to run can be provided instead.
        :param raise_validation_errors: Whether to raise validation errors
        """
        # Initialize interviews iterator
        # interviews_iter = self._expand_interviews()
        self.total_interviews = list(self._expand_interviews())
        hash_to_order = {
            hash(interview): index
            for index, interview in enumerate(self.total_interviews)
        }
        interviews_iter = iter(self.total_interviews)  # Create fresh iterator

        self._initialized.set()  # Signal that we're ready

        # Keep track of active tasks
        active_tasks = set()

        try:
            while True:
                # Add new tasks if we're below max_concurrent and there are more interviews
                while len(active_tasks) < self.MAX_CONCURRENT:
                    try:
                        interview = next(interviews_iter)
                        task = asyncio.create_task(
                            self._conduct_interview(interview=interview)
                        )
                        active_tasks.add(task)
                        # Add callback to remove task from set when done
                        task.add_done_callback(active_tasks.discard)
                    except StopIteration:
                        break

                if not active_tasks:
                    break

                # Wait for next completed task
                done, _ = await asyncio.wait(
                    active_tasks, return_when=asyncio.FIRST_COMPLETED
                )

                # Process completed tasks
                for task in done:
                    try:
                        result = await task
                        self.jobs_runner_status.add_completed_interview(result)
                        result.order = hash_to_order[result.interview_hash]
                        yield result
                    except Exception as e:
                        if self.stop_on_exception:
                            # Cancel remaining tasks
                            for t in active_tasks:
                                if not t.done():
                                    t.cancel()
                            raise
                        else:
                            # Log error and continue
                            # logger.error(f"Task failed with error: {e}")
                            continue
        finally:
            # Ensure we cancel any remaining tasks if we exit early
            for task in active_tasks:
                if not task.done():
                    task.cancel()

    def _expand_interviews(self) -> Generator["Interview", None, None]:
        """Populates self.total_interviews with n copies of each interview.
        It also has to set the cache for each interview.

        :param n: how many times to run each interview.
        """
        for interview in self.interviews:
            for iteration in range(self.n):
                if iteration > 0:
                    yield interview.duplicate(iteration=iteration, cache=self.cache)
                else:
                    interview.cache = self.cache
                    yield interview

    async def run_async(
        self, cache: Optional[Cache] = None, n: int = 1, **kwargs
    ) -> Results:
        """Used for some other modules that have a non-standard way of running interviews."""
        self.jobs_runner_status = JobsRunnerStatus(self, n=n)
        # self.cache = Cache() if cache is None else cache
        data = []
        async for result in self.run_async_generator(n=n):  # cache=self.cache,
            data.append(result)
        return Results(survey=self.jobs.survey, data=data)

    def simple_run(self):
        data = asyncio.run(self.run_async())
        return Results(survey=self.jobs.survey, data=data)

    async def _conduct_interview(self, interview: Interview) -> "Result":
        """Conducts an interview and returns the result.

        :param interview: the interview to conduct

        :return: the result of the interview

        'extracted_answers' is a dictionary of the answers to the questions in the interview.
        This is not the same as the generated_tokens---it can include substantial cleaning and processing / validation.
        """
        # the model buckets are used to track usage rates
        model_buckets = self.bucket_collection[interview.model]

        # get the results of the interview e.g., {'how_are_you':"Good" 'how_are_you_generated_tokens': "Good"}
        extracted_answers: dict[str, str]
        model_response_objects: List[EDSLResultObjectInput]

        extracted_answers, model_response_objects = (
            await interview.async_conduct_interview(
                model_buckets=model_buckets,
                stop_on_exception=self.stop_on_exception,
                raise_validation_errors=self.raise_validation_errors,
                key_lookup=self.key_lookup,
            )
        )
        return Result.from_interview(
            interview=interview,
            extracted_answers=extracted_answers,
            model_response_objects=model_response_objects,
        )

    @property
    def elapsed_time(self):
        return time.monotonic() - self.start_time

    def sort_results_and_append_task_history(self, raw_results: Results) -> Results:
        """Sorts the results in the order of the original interviews.

        :param raw_results: the raw results to sort.
        """
        task_history = TaskHistory(self.total_interviews, include_traceback=False)

        results = Results(
            survey=self.jobs.survey,
            data=sorted(raw_results, key=lambda x: x.order),
            task_history=task_history,
            # cache=cache,
        )
        results.bucket_collection = self.bucket_collection
        return results

    def handle_results_exceptions(self, results: Results) -> None:
        """Prints exceptions and opens the exception report if necessary."""

        if results.has_unfixed_exceptions and self.print_exceptions:
            from edsl.scenarios.FileStore import HTMLFileStore
            from edsl.config import CONFIG
            from edsl.coop.coop import Coop

            msg = f"Exceptions were raised in {len(results.task_history.indices)} out of {len(self.total_interviews)} interviews.\n"

            if len(results.task_history.indices) > 5:
                msg += f"Exceptions were raised in the following interviews: {results.task_history.indices}.\n"

            import sys

            print(msg, file=sys.stderr)
            from edsl.config import CONFIG

            if CONFIG.get("EDSL_OPEN_EXCEPTION_REPORT_URL") == "True":
                open_in_browser = True
            elif CONFIG.get("EDSL_OPEN_EXCEPTION_REPORT_URL") == "False":
                open_in_browser = False
            else:
                raise Exception(
                    "EDSL_OPEN_EXCEPTION_REPORT_URL", "must be either True or False"
                )

            filepath = results.task_history.html(
                cta="Open report to see details.",
                open_in_browser=open_in_browser,
                return_link=True,
            )

            try:
                coop = Coop()
                user_edsl_settings = coop.edsl_settings
                remote_logging = user_edsl_settings["remote_logging"]
            except Exception as e:
                print(e)
                remote_logging = False

            if remote_logging:
                filestore = HTMLFileStore(filepath)
                coop_details = filestore.push(description="Error report")
                print(coop_details)

            print("Also see: https://docs.expectedparrot.com/en/latest/exceptions.html")

    @jupyter_nb_handler
    async def run(
        self,
        cache: Union[Cache, False, None] = None,
        n: int = 1,
        stop_on_exception: bool = False,
        progress_bar: bool = False,
        print_exceptions: bool = True,
        raise_validation_errors: bool = False,
        jobs_runner_status: Optional[Type[JobsRunnerStatusBase]] = None,
        job_uuid: Optional[UUID] = None,
    ) -> "Coroutine":
        """Runs a collection of interviews, handling both async and sync contexts."""

        self.results = []
        self.start_time = time.monotonic()
        self.completed = False
        # self.cache = cache

        if cache:
            # raise Exception("The cache parameter is not supported in this version.")
            warnings.warn("The cache parameter is not supported in this version.")

        from edsl.coop import Coop

        coop = Coop()
        endpoint_url = coop.get_progress_bar_url()

        self.n = n
        self.stop_on_exception = stop_on_exception
        self.progress_bar = progress_bar
        self.print_exceptions = print_exceptions
        self.raise_validation_errors = raise_validation_errors
        self.job_uuid = job_uuid

        if jobs_runner_status is not None:
            self.jobs_runner_status = jobs_runner_status(
                self, n=self.n, endpoint_url=endpoint_url, job_uuid=self.job_uuid
            )
        else:
            self.jobs_runner_status = JobsRunnerStatus(
                self, n=n, endpoint_url=endpoint_url, job_uuid=job_uuid
            )

        stop_event = threading.Event()

        async def get_results() -> None:
            """Conducted the interviews and append to the results list."""
            async for result in self.run_async_generator():
                self.results.append(result)
            self.completed = True

        def run_progress_bar(stop_event) -> None:
            """Runs the progress bar in a separate thread."""
            self.jobs_runner_status.update_progress(stop_event)

        if progress_bar and self.jobs_runner_status.has_ep_api_key():
            self.jobs_runner_status.setup()
            progress_thread = threading.Thread(
                target=run_progress_bar, args=(stop_event,)
            )
            progress_thread.start()
        elif progress_bar:
            warnings.warn(
                "You need an Expected Parrot API key to view job progress bars."
            )

        exception_to_raise = None
        try:
            await get_results()
        except KeyboardInterrupt:
            print("Keyboard interrupt received. Stopping gracefully...")
            stop_event.set()
        except Exception as e:
            if self.stop_on_exception:
                exception_to_raise = e
            stop_event.set()
        finally:
            stop_event.set()
            if progress_bar and self.jobs_runner_status.has_ep_api_key():
                # self.jobs_runner_status.stop_event.set()
                if progress_thread:
                    progress_thread.join()

            if exception_to_raise:
                raise exception_to_raise

            results = self.sort_results_and_append_task_history(self.results)
            self.handle_results_exceptions(results)
            return results
