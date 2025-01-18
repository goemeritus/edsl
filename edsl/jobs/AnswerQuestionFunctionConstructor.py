import copy
import asyncio

from typing import Union, Type, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from edsl.questions.QuestionBase import QuestionBase
    from edsl.jobs.interviews.Interview import Interview
    from edsl.language_models.key_management.KeyLookup import KeyLookup

from edsl.surveys.base import EndOfSurvey
from edsl.jobs.tasks.task_status_enum import TaskStatus

from edsl.jobs.FetchInvigilator import FetchInvigilator
from edsl.exceptions.language_models import LanguageModelNoResponseError
from edsl.exceptions.questions import QuestionAnswerValidationError
from edsl.data_transfer_models import AgentResponseDict, EDSLResultObjectInput

from edsl.jobs.Answers import Answers


class RetryConfig:
    from edsl.config import CONFIG

    EDSL_BACKOFF_START_SEC = float(CONFIG.get("EDSL_BACKOFF_START_SEC"))
    EDSL_BACKOFF_MAX_SEC = float(CONFIG.get("EDSL_BACKOFF_MAX_SEC"))
    EDSL_MAX_ATTEMPTS = int(CONFIG.get("EDSL_MAX_ATTEMPTS"))


class SkipHandler:

    def __init__(self, interview: "Interview"):
        self.interview = interview
        self.question_index = self.interview.to_index

        self.skip_function: Callable = (
            self.interview.survey.rule_collection.skip_question_before_running
        )

    def should_skip(self, current_question: "QuestionBase") -> bool:
        """Determine if the current question should be skipped."""
        current_question_index = self.question_index[current_question.question_name]
        combined_answers = (
            self.interview.answers
            | self.interview.scenario
            | self.interview.agent["traits"]
        )
        return self.skip_function(current_question_index, combined_answers)

    def cancel_skipped_questions(self, current_question: "QuestionBase") -> None:
        """Cancel the tasks for questions that should be skipped."""
        current_question_index: int = self.interview.to_index[
            current_question.question_name
        ]
        answers = (
            self.interview.answers
            | self.interview.scenario
            | self.interview.agent["traits"]
        )

        # Get the index of the next question, which could also be the end of the survey
        next_question: Union[int, EndOfSurvey] = (
            self.interview.survey.rule_collection.next_question(
                q_now=current_question_index,
                answers=answers,
            )
        )

        def cancel_between(start, end):
            """Cancel the tasks for questions between the start and end indices."""
            for i in range(start, end):
                self.interview.tasks[i].cancel()

        if (next_question_index := next_question.next_q) == EndOfSurvey:
            cancel_between(
                current_question_index + 1, len(self.interview.survey.questions)
            )
            return

        if next_question_index > (current_question_index + 1):
            cancel_between(current_question_index + 1, next_question_index)


class AnswerQuestionFunctionConstructor:
    """Constructs a function that answers a question and records the answer."""

    def __init__(self, interview: "Interview", key_lookup: "KeyLookup"):
        self.interview = interview
        self.key_lookup = key_lookup

        self.had_language_model_no_response_error: bool = False
        self.question_index = self.interview.to_index

        self.skip_function: Callable = (
            self.interview.survey.rule_collection.skip_question_before_running
        )

        self.invigilator_fetcher = FetchInvigilator(
            self.interview, key_lookup=self.key_lookup
        )
        self.skip_handler = SkipHandler(self.interview)

    def _handle_exception(
        self, e: Exception, invigilator: "InvigilatorBase", task=None
    ):
        """Handle an exception that occurred while answering a question."""

        from edsl.jobs.interviews.InterviewExceptionEntry import InterviewExceptionEntry

        answers = copy.copy(
            self.interview.answers
        )  # copy to freeze the answers here for logging
        exception_entry = InterviewExceptionEntry(
            exception=e,
            invigilator=invigilator,
            answers=answers,
        )
        if task:
            task.task_status = TaskStatus.FAILED

        self.interview.exceptions.add(
            invigilator.question.question_name, exception_entry
        )

        if self.interview.raise_validation_errors and isinstance(
            e, QuestionAnswerValidationError
        ):
            raise e

        stop_on_exception = getattr(self.interview, "stop_on_exception", False)
        if stop_on_exception:
            raise e

    # def __call__(self):
    #     return self.answer_question_and_record_task

    async def answer_question_and_record_task(
        self,
        *,
        question: "QuestionBase",
        task=None,
    ) -> "EDSLResultObjectInput":

        from tenacity import (
            retry,
            stop_after_attempt,
            wait_exponential,
            retry_if_exception_type,
            RetryError,
        )

        @retry(
            stop=stop_after_attempt(RetryConfig.EDSL_MAX_ATTEMPTS),
            wait=wait_exponential(
                multiplier=RetryConfig.EDSL_BACKOFF_START_SEC,
                max=RetryConfig.EDSL_BACKOFF_MAX_SEC,
            ),
            retry=retry_if_exception_type(LanguageModelNoResponseError),
            reraise=True,
        )
        async def attempt_answer():
            invigilator = self.invigilator_fetcher(question)

            if self.skip_handler.should_skip(question):
                return invigilator.get_failed_task_result(
                    failure_reason="Question skipped."
                )

            try:
                print(
                    "Awaiting on the invigilator (inside the AnswerQuestionFunctionConstructor.py file)"
                )
                response: EDSLResultObjectInput = (
                    await invigilator.async_answer_question()
                )
                print("Got a response back")
                if response.validated:
                    self.interview.answers.add_answer(
                        response=response, question=question
                    )

                    self.skip_handler.cancel_skipped_questions(question)
                else:
                    if (
                        hasattr(response, "exception_occurred")
                        and response.exception_occurred
                    ):
                        raise response.exception_occurred

            except QuestionAnswerValidationError as e:
                self._handle_exception(e, invigilator, task)
                return invigilator.get_failed_task_result(
                    failure_reason="Question answer validation failed."
                )

            except asyncio.TimeoutError as e:
                self._handle_exception(e, invigilator, task)
                had_language_model_no_response_error = True
                raise LanguageModelNoResponseError(
                    f"Language model timed out for question '{question.question_name}.'"
                )

            except Exception as e:
                self._handle_exception(e, invigilator, task)

            if "response" not in locals():
                had_language_model_no_response_error = True
                raise LanguageModelNoResponseError(
                    f"Language model did not return a response for question '{question.question_name}.'"
                )

            if (
                question.question_name in self.interview.exceptions
                and had_language_model_no_response_error
            ):
                self.interview.exceptions.record_fixed_question(question.question_name)

            return response

        try:
            return await attempt_answer()
        except RetryError as retry_error:
            original_error = retry_error.last_attempt.exception()
            self._handle_exception(
                original_error, self.invigilator_fetcher(question), task
            )
            raise original_error
