from __future__ import annotations
from typing import Optional

from edsl.questions.descriptors import QuestionOptionsDescriptor, OptionLabelDescriptor
from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice

from edsl.questions.decorators import inject_exception


class QuestionLinearScale(QuestionMultipleChoice):
    """This question prompts the agent to respond to a statement on a linear scale."""

    question_type = "linear_scale"
    option_labels: Optional[dict[int, str]] = OptionLabelDescriptor()
    question_options = QuestionOptionsDescriptor(linear_scale=True)

    def __init__(
        self,
        question_name: str,
        question_text: str,
        question_options: list[int],
        option_labels: Optional[dict[int, str]] = None,
        answering_instructions: Optional[str] = None,
        question_presentation: Optional[str] = None,
        include_comment: Optional[bool] = True,
    ):
        """Instantiate a new QuestionLinearScale.

        :param question_name: The name of the question.
        :param question_text: The text of the question.
        :param question_options: The options the respondent should select from.
        :param option_labels: Maps question_options to labels.
        :param instructions: Instructions for the question. If not provided, the default instructions are used. To view them, run `QuestionLinearScale.default_instructions`.
        """
        super().__init__(
            question_name=question_name,
            question_text=question_text,
            question_options=question_options,
            use_code=False,  # question linear scale will have its own code
            include_comment=include_comment,
        )
        self.question_options = question_options
        if isinstance(option_labels, str):
            self.option_labels = option_labels
        else:
            self.option_labels = (
                {int(k): v for k, v in option_labels.items()} if option_labels else {}
            )
        self.answering_instructions = answering_instructions
        self.question_presentation = question_presentation

    ################
    # Helpful
    ################
    @classmethod
    @inject_exception
    def example(cls, include_comment: bool = True) -> QuestionLinearScale:
        """Return an example of a linear scale question."""
        return cls(
            question_text="How much do you like ice cream?",
            question_options=[1, 2, 3, 4, 5],
            question_name="ice_cream",
            option_labels={1: "I hate it", 5: "I love it"},
            include_comment=include_comment,
        )


def main():
    """Create an example of a linear scale question and demonstrate its functionality."""
    from edsl.questions.derived.QuestionLinearScale import QuestionLinearScale

    q = QuestionLinearScale.example()
    q.question_text
    q.question_options
    q.question_name
    # validate an answer
    q._validate_answer({"answer": 3, "comment": "I like custard"})
    # translate answer code
    q._translate_answer_code_to_answer(3, {})
    # simulate answer
    q._simulate_answer()
    q._simulate_answer(human_readable=False)
    q._validate_answer(q._simulate_answer(human_readable=False))
    # serialization (inherits from Question)
    q.to_dict()
    assert q.from_dict(q.to_dict()) == q

    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
