from __future__ import annotations
from typing import Any, Optional
from uuid import uuid4
from edsl.questions.QuestionBase import QuestionBase

from pydantic import field_validator
from edsl.questions.ResponseValidatorABC import ResponseValidatorABC
from edsl.questions.ResponseValidatorABC import BaseResponse

from edsl.exceptions import QuestionAnswerValidationError
import textwrap


class FreeTextResponse(BaseResponse):
    """
    >>> nr = FreeTextResponse(answer = "You dude")
    >>> nr.dict()
    {'answer': 'You dude', 'comment': None}
    """

    answer: str


class FreeTextResponseValidator(ResponseValidatorABC):

    required_params = []

    valid_examples = [({"answer": "This is great"}, {})]

    invalid_examples = [
        (
            {"answer": None},
            {},
            "Answer code must not be missing.",
        ),
    ]

    def custom_validate(self, response) -> FreeTextResponse:
        return response.dict()


class QuestionFreeText(QuestionBase):
    """This question prompts the agent to respond with free text."""

    question_type = "free_text"
    _response_model = FreeTextResponse
    response_validator_class = FreeTextResponseValidator

    def __init__(self, question_name: str, question_text: str):
        """Instantiate a new QuestionFreeText.

        :param question_name: The name of the question.
        :param question_text: The text of the question.
        """
        self.question_name = question_name
        self.question_text = question_text

    @property
    def question_html_content(self) -> str:
        from jinja2 import Template

        question_html_content = Template(
            """
        <div>
        <textarea id="{{ question_name }}" name="{{ question_name }}"></textarea>
        </div>
        """
        ).render(question_name=self.question_name)
        return question_html_content

    @classmethod
    def example(cls, randomize: bool = False) -> QuestionFreeText:
        """Return an example instance of a free text question."""
        addition = "" if not randomize else str(uuid4())
        return cls(question_name="how_are_you", question_text=f"How are you?{addition}")


def main():
    """Create an example question and demonstrate its functionality."""
    from edsl.questions.QuestionFreeText import QuestionFreeText

    q = QuestionFreeText.example()
    q.question_text
    q.question_name
    # q.instructions
    # validate an answer
    q._validate_answer({"answer": "I like custard"})
    # translate answer code
    q._translate_answer_code_to_answer({"answer"})
    # simulate answer
    q._simulate_answer()
    q._simulate_answer(human_readable=False)
    q._validate_answer(q._simulate_answer(human_readable=False))
    # serialization (inherits from Question)
    q.to_dict()
    assert q.from_dict(q.to_dict()) == q

    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
