"""Mixin with validators for LLM answers to questions."""

import re
from typing import Any, Type, Union
from edsl.exceptions.questions import (
    QuestionAnswerValidationError,
)


class AnswerValidatorMixin:
    """
    Mixin with validators for LLM answers to questions.

    - Template validation: validators for the entire answer object format
    - Value validation: validators for specific values
    - Question specific validation: validators for specific question types
    """

    def failing_job(self):
        from edsl import Agent

        a = Agent()

        def f(self, question, scenario):
            return []

        a.add_direct_question_answering_method(f, validate_response=True)
        from edsl import QuestionNumerical

        q = QuestionNumerical.example()
        results = q.by(a).run()
        return results

    #####################
    # TEMPLATE VALIDATION
    #####################
    def _validate_answer_template_basic(self, answer: Any) -> None:
        """Check that the answer (i) is a dictionary (ii) has an 'answer' key.

        - E.g., both {'answer': 1} and {'answer': {'a': 1}, 'other_key'=[1,2,3]} are valid
        """
        if not isinstance(answer, dict):
            raise QuestionAnswerValidationError(
                f"Answer must be a dictionary (got {answer})."
            )
        if not "answer" in answer:
            raise QuestionAnswerValidationError(
                f"Answer must have an 'answer' key (got {answer})."
            )

    #####################
    # VALUE VALIDATION
    #####################
    def _validate_answer_key_value(
        self, answer: dict[str, Any], key: str, of_type: Type
    ) -> None:
        """Check that the value of a key is of the specified type."""
        if not isinstance(answer.get(key), of_type):
            raise QuestionAnswerValidationError(
                f"""Answer key '{key}' must be of type {of_type.__name__};
                (got {answer.get(key)}) which is of type {type(answer.get(key))}."""
            )

    def _validate_answer_key_value_numeric(
        self, answer: dict[str, Any], key: str
    ) -> None:
        """Check that the value is numeric (int or float).
        Can also deal with strings that contain commas and other characters.

        """
        value = answer.get(key)
        initial_value = value
        if type(value) == str:
            value = value.replace(",", "")
            value = "".join(re.findall(r"[-+]?\d*\.\d+|\d+", value))
            if value.isdigit():
                value = int(value)
            else:
                try:
                    float(value)
                    value = float(value)
                except ValueError:
                    raise QuestionAnswerValidationError(
                        f"Answer should be numerical (int or float). Got '{initial_value}'"
                    )
            return None
        elif type(value) == int or type(value) == float:
            return None
        else:
            raise QuestionAnswerValidationError(
                f"Answer should be numerical (int or float)."
            )

    #####################
    # QUESTION SPECIFIC VALIDATION
    #####################
    def _validate_answer_budget(self, answer: dict[str, Any]) -> None:
        """Validate QuestionBudget-specific answer.

        Check that answer["answer"]:
        - has keys that are in the range of the number of options
        - has values that are non-negative integers
        - has values that sum to `budget_sum`
        - contains all keys in the range of the number of options
        """
        answer = answer.get("answer")
        budget_sum = self.budget_sum
        acceptable_answer_keys = set(range(len(self.question_options)))
        answer_keys = set([int(k) for k in answer.keys()])
        current_sum = sum(answer.values())
        if not current_sum == budget_sum:
            raise QuestionAnswerValidationError(
                f"Budget sum must be {budget_sum}, but got {current_sum}."
            )
        if any(v < 0 for v in answer.values()):
            raise QuestionAnswerValidationError(
                f"Budget values must be positive, but got {answer_keys}."
            )
        if any([int(key) not in acceptable_answer_keys for key in answer.keys()]):
            raise QuestionAnswerValidationError(
                f"Budget keys must be in {acceptable_answer_keys}, but got {answer_keys}."
            )
        if acceptable_answer_keys != answer_keys:
            missing_keys = acceptable_answer_keys - answer_keys
            raise QuestionAnswerValidationError(
                f"All but keys must be represented in the answer. Missing: {missing_keys}."
            )

    def _validate_answer_checkbox(self, answer: dict[str, Union[str, int]]) -> None:
        """Validate QuestionCheckbox-specific answer.

        :param answer: Answer to validate


        Check that answer["answer"]:
        - has elements that are strings, bytes-like objects or real numbers evaluating to integers
        - has elements that are in the range of the number of options
        - has at least `min_selections` elements, if provided
        - has at most `max_selections` elements, if provided
        """
        answer_codes = answer["answer"]
        try:
            answer_codes = [int(k) for k in answer["answer"]]
        except:
            raise QuestionAnswerValidationError(
                f"Answer codes must be a list of strings, bytes-like objects or real numbers (got {answer['answer']})."
            )
        acceptable_values = list(range(len(self.question_options)))
        for answer_code in answer_codes:
            if answer_code not in acceptable_values:
                raise QuestionAnswerValidationError(
                    f"Answer code {answer_code} has elements not in {acceptable_values}."
                )
        if self.min_selections is not None and len(answer_codes) < self.min_selections:
            raise QuestionAnswerValidationError(
                f"Answer codes, {answer_codes}, has fewer than {self.min_selections} options selected."
            )
        if self.max_selections is not None and len(answer_codes) > self.max_selections:
            raise QuestionAnswerValidationError(
                f"Answer codes, {answer_codes}, has more than {self.max_selections} options selected."
            )

    def _validate_answer_extract(self, answer: dict[str, Any]) -> None:
        """Validate QuestionExtract-specific answer.

        Check that answer["answer"]:
        - does not have keys that are not in the answer template
        - has all keys that are in the answer template
        """
        value = answer.get("answer")
        acceptable_answer_keys = set(self.answer_template.keys())
        if any([key not in acceptable_answer_keys for key in value.keys()]):
            raise QuestionAnswerValidationError(
                f"Answer keys must be in {acceptable_answer_keys}, but got {value.keys()}."
            )
        if any([key not in value.keys() for key in acceptable_answer_keys]):
            raise QuestionAnswerValidationError(
                f"Answer must have all keys in {acceptable_answer_keys}, but got {value.keys()}."
            )

    def _validate_answer_list(self, answer: dict[str, Union[list, str]]) -> None:
        """Validate QuestionList-specific answer.

        Check that answer["answer"]:
        - is not empty, if `allow_nonresponse` is False
        - has no more than `max_list_items` elements
        - has no empty strings
        """
        value = answer.get("answer")
        if (
            hasattr(self, "allow_nonresponse")
            and self.allow_nonresponse == False
            and (value == [] or value is None)
        ):
            raise QuestionAnswerValidationError("You must provide a response.")

        if (
            hasattr(self, "max_list_items")
            and self.max_list_items is not None
            and (len(value) > self.max_list_items)
        ):
            raise QuestionAnswerValidationError("Response has too many items.")

        if any([item == "" for item in value]):
            raise QuestionAnswerValidationError(
                f"Answer cannot contain empty strings, but got {value}."
            )

    def _validate_answer_numerical(self, answer: dict) -> None:
        """Validate QuestionNumerical-specific answer.

        Check that answer["answer"]:
        - is not less than `min_value`
        - is not greater than `max_value`
        """
        try:
            value = float(answer.get("answer"))
        except ValueError:
            raise QuestionAnswerValidationError(
                f"Answer must real number or convertible to a real number (got {answer.get('answer')})."
            )
        if self.min_value is not None and value < self.min_value:
            raise QuestionAnswerValidationError(
                f"Value {value} is less than {self.min_value}"
            )
        if self.max_value is not None and value > self.max_value:
            raise QuestionAnswerValidationError(
                f"Value {value} is greater than {self.max_value}"
            )
        return value

    def _validate_answer_multiple_choice(
        self, answer: dict[str, Union[str, int]]
    ) -> None:
        """Validate QuestionMultipleChoice-specific answer.

        Check that answer["answer"]:
        - is a string, bytes-like object or real number
        - is a non-negative integer
        - is in the range of the number of options
        """
        try:
            value = int(answer.get("answer"))
        except:
            raise QuestionAnswerValidationError(
                f"Answer code must be a string, a bytes-like object or a real number (got {answer.get('answer')})."
            )
        if not value >= 0:
            raise QuestionAnswerValidationError(
                f"Answer code must be a non-negative integer (got {value})."
            )
        if int(value) not in range(len(self.question_options)):
            raise QuestionAnswerValidationError(
                f"Answer code {value} must be in {list(range(len(self.question_options)))}."
            )

    def _validate_answer_rank(self, answer: dict[str, Union[str, int]]) -> None:
        """Validate QuestionRank-specific answer.

        Check that answer["answer"]:
        - contains only integers
        - contains only integers in the range of the number of options
        - has the correct number of elements
        """
        value = answer.get("answer")
        acceptable_values = list(range(len(self.question_options)))
        for v in value:
            try:
                answer_code = int(v)
            except ValueError:
                raise QuestionAnswerValidationError(
                    f"Rank answer {value} has elements that are not integers, namely {v}."
                )
            except TypeError:
                raise QuestionAnswerValidationError(
                    f"Rank answer {value} has elements that are not integers, namely {v}."
                )
            if answer_code not in acceptable_values:
                raise QuestionAnswerValidationError(
                    f"Answer {value} has elements not in {acceptable_values}, namely {v}."
                )
        if len(value) != self.num_selections:
            raise QuestionAnswerValidationError(
                f"Rank answer {value}, but exactly {self.num_selections} selections required."
            )

    def _validate_answer_matrix(self, answer: dict[str, Any]) -> None:
        """Validate QuestionMatrix-specific answer.

        Check that answer["answer"]:
        - is a dictionary
        - has all required question_items as keys
        - has values that are valid options from question_options
        - has the correct number of responses (one per item)
        """
        value = answer.get("answer")

        # Check that answer is a dictionary
        if not isinstance(value, dict):
            raise QuestionAnswerValidationError(
                f"Matrix answer must be a dictionary mapping items to responses (got {value})"
            )

        # Check that all required items are present
        required_items = set(self.question_items)
        provided_items = set(value.keys())

        if missing_items := (required_items - provided_items):
            raise QuestionAnswerValidationError(
                f"Missing responses for items: {missing_items}"
            )

        if extra_items := (provided_items - required_items):
            raise QuestionAnswerValidationError(
                f"Unexpected responses for items: {extra_items}"
            )

        # Check that all responses are valid options
        valid_options = set(self.question_options)
        for item, response in value.items():
            if response not in valid_options:
                raise QuestionAnswerValidationError(
                    f"Invalid response '{response}' for item '{item}'. "
                    f"Must be one of: {valid_options}"
                )

    def _validate_answer_dict(self, answer: dict[str, Any]) -> None:
        """Validate QuestionDict-specific answer.

        Check that answer["answer"]:
        - is a dictionary
        - has all required answer_keys as keys
        """
        value = answer.get("answer")

        # Check that answer is a dictionary
        if not isinstance(value, dict):
            raise QuestionAnswerValidationError(
                f"Dict answer must be a dictionary mapping values to specified keys (got {value})"
            )

        # Check that all required answer keys are present
        required_keys = set(self.answer_keys)
        provided_keys = set(value.keys())

        if missing_keys := (required_keys - provided_keys):
            raise QuestionAnswerValidationError(
                f"Missing required keys: {missing_keys}"
            )

        if extra_keys := (provided_keys - required_keys):
            raise QuestionAnswerValidationError(
                f"Unexpected keys: {extra_keys}"
            )


if __name__ == "__main__":
    pass
    # import doctest

    # doctest.testmod(optionflags=doctest.ELLIPSIS)

    # results = AnswerValidatorMixin().failing_job()
