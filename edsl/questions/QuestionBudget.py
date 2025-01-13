from __future__ import annotations
from typing import Any, Optional, Union, List

from pydantic import Field, BaseModel, validator

from edsl.questions.QuestionBase import QuestionBase
from edsl.questions.descriptors import IntegerDescriptor, QuestionOptionsDescriptor
from edsl.questions.response_validator_abc import ResponseValidatorABC


class BudgetResponseValidator(ResponseValidatorABC):
    valid_examples = []

    invalid_examples = []

    def fix(self, response, verbose=False):
        if verbose:
            print(f"Fixing list response: {response}")
        answer = str(response.get("answer") or response.get("generated_tokens", ""))
        if len(answer.split(",")) > 0:
            return (
                {"answer": answer.split(",")} | {"comment": response.get("comment")}
                if "comment" in response
                else {}
            )


def create_budget_model(
    budget_sum: float, permissive: bool, question_options: List[str]
):
    class BudgetResponse(BaseModel):
        answer: List[float] = Field(
            ...,
            description="List of non-negative numbers representing budget allocation",
            min_items=len(question_options),
            max_items=len(question_options),
        )
        comment: Optional[str] = None
        generated_tokens: Optional[str] = None

        @validator("answer")
        def validate_answer(cls, v):
            if len(v) != len(question_options):
                raise ValueError(f"Must provide {len(question_options)} values")
            if any(x < 0 for x in v):
                raise ValueError("All values must be non-negative")
            total = sum(v)
            if not permissive and total != budget_sum:
                raise ValueError(f"Sum of numbers must equal {budget_sum}")
            elif permissive and total > budget_sum:
                raise ValueError(f"Sum of numbers cannot exceed {budget_sum}")
            return v

        class Config:
            extra = "forbid"

    return BudgetResponse


class QuestionBudget(QuestionBase):
    """This question prompts the agent to allocate a budget among options."""

    question_type = "budget"
    budget_sum: int = IntegerDescriptor(none_allowed=False)
    question_options: list[str] = QuestionOptionsDescriptor(q_budget=True)
    _response_model = None
    response_validator_class = BudgetResponseValidator

    def __init__(
        self,
        question_name: str,
        question_text: str,
        question_options: list[str],
        budget_sum: int,
        include_comment: bool = True,
        question_presentation: Optional[str] = None,
        answering_instructions: Optional[str] = None,
        permissive: bool = False,
    ):
        """Instantiate a new QuestionBudget.

        :param question_name: The name of the question.
        :param question_text: The text of the question.
        :param question_options: The options for allocation of the budget sum.
        :param budget_sum: The total amount of the budget to be allocated among the options.
        """
        self.question_name = question_name
        self.question_text = question_text
        self.question_options = question_options
        self.budget_sum = budget_sum
        self.question_presentation = question_presentation
        self.answering_instructions = answering_instructions
        self.permissive = permissive
        self.include_comment = include_comment

    def create_response_model(self):
        return create_budget_model(
            self.budget_sum, self.permissive, self.question_options
        )

    def _translate_answer_code_to_answer(
        self, answer_code, combined_dict
    ) -> list[dict]:
        """
        Translate the answer codes to the actual answers.

        For example, for a budget question with options ["a", "b", "c"],
        the answer codes are 0, 1, and 2. The LLM will respond with 0.
        This code will translate that to "a".
        """
        translated_codes = []
        for answer_code, question_option in zip(answer_code, self.question_options):
            translated_codes.append({question_option: answer_code})

        return translated_codes

    # def _simulate_answer(self, human_readable=True):
    #     """Simulate a valid answer for debugging purposes (what the validator expects)."""
    #     from edsl.utilities.utilities import random_string

    #     if human_readable:
    #         keys = self.question_options
    #     else:
    #         keys = range(len(self.question_options))
    #     remaining_budget = self.budget_sum
    #     values = []
    #     for _ in range(len(self.question_options)):
    #         if _ == len(self.question_options) - 1:
    #             # Assign remaining budget to the last value
    #             values.append(remaining_budget)
    #         else:
    #             # Generate a random value between 0 and remaining budget
    #             value = random.randint(0, remaining_budget)
    #             values.append(value)
    #             remaining_budget -= value
    #     answer = dict(zip(keys, values))
    #     return {
    #         "answer": answer,
    #         "comment": random_string(),
    #     }

    @property
    def question_html_content(self) -> str:
        from jinja2 import Template

        question_html_content = Template(
            """
        <form id="budgetForm">
        <p>Total Budget: {{ budget_sum }}</p>
        <p>Remaining Budget: <span id="remainingBudget">{{ budget_sum }}</span></p>
        {% for option in question_options %}
        <div>
            <label for="{{ option }}">{{ option }}</label>
            <input type="number" id="{{ option }}" name="{{ question_name }}[{{ option }}]" value="0" min="0" max="{{ budget_sum }}" oninput="updateRemainingBudget()">
        </div>
        {% endfor %}
        </form>
        <script>
        function updateRemainingBudget() {
            let totalBudget = {{ budget_sum }};
            let allocated = 0;

            {% for option in question_options %}
            allocated += parseInt(document.getElementById("{{ option }}").value) || 0;
            {% endfor %}

            let remaining = totalBudget - allocated;
            document.getElementById('remainingBudget').innerText = remaining;

            {% for option in question_options %}
            document.getElementById("{{ option }}").max = remaining + parseInt(document.getElementById("{{ option }}").value);
            {% endfor %}
        }
        </script>
        """
        ).render(
            question_name=self.question_name,
            budget_sum=self.budget_sum,
            question_options=self.question_options,
        )
        return question_html_content

    ################
    # Helpful methods
    ################
    @classmethod
    def example(cls, include_comment: bool = True) -> QuestionBudget:
        """Return an example of a budget question."""
        return cls(
            question_name="food_budget",
            question_text="How would you allocate $100?",
            question_options=["Pizza", "Ice Cream", "Burgers", "Salad"],
            budget_sum=100,
            include_comment=include_comment,
        )


def main():
    """Create an example of a budget question and demonstrate its functionality."""
    from edsl.questions.QuestionBudget import QuestionBudget

    q = QuestionBudget.example()
    q.question_text
    q.question_options
    q.question_name
    # validate an answer
    q._validate_answer(
        {"answer": {0: 100, 1: 0, 2: 0, 3: 0}, "comment": "I like custard"}
    )
    # translate answer code
    q._translate_answer_code_to_answer({0: 100, 1: 0, 2: 0, 3: 0})
    # simulate answer
    q._simulate_answer()
    q._simulate_answer(human_readable=False)
    q._validate_answer(q._simulate_answer(human_readable=False))
    # serialization (inherits from Question)
    q.to_dict()
    assert q.from_dict(q.to_dict()) == q


if __name__ == "__main__":
    # q = QuestionBudget.example()
    # results = q.run()

    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
