"""This module contains the descriptors used to validate the attributes of the question classes."""

from abc import ABC, abstractmethod
import re
from typing import Any, Callable, List, Optional
from edsl.exceptions.questions import (
    QuestionCreationValidationError,
    QuestionAnswerValidationError,
)
from edsl.questions.settings import Settings


################################
# Helper functions
################################


def contains_single_braced_substring(s: str) -> bool:
    """Check if the string contains a substring in single braces."""
    pattern = r"(?<!\{)\{[^{}]+\}(?!\})"
    match = re.search(pattern, s)
    return bool(match)


def is_number(value: Any) -> bool:
    """Check if an object is a number."""
    return isinstance(value, int) or isinstance(value, float)


def is_number_or_none(value: Any) -> bool:
    """Check if an object is a number or None."""
    return value is None or is_number(value)


################################
# Descriptor ABC
################################


class BaseDescriptor(ABC):
    """ABC for something."""

    @abstractmethod
    def validate(self, value: Any) -> None:
        """Validate the value. If it is invalid, raises an exception. If it is valid, does nothing."""
        pass

    def __get__(self, instance, owner):
        """Get the value of the attribute."""
        if self.name not in instance.__dict__:
            return {}
        return instance.__dict__[self.name]

    def __set__(self, instance, value: Any) -> None:
        """Set the value of the attribute."""
        new_value = self.validate(value, instance)

        if new_value is not None:
            instance.__dict__[self.name] = new_value
        else:
            instance.__dict__[self.name] = value

    def __set_name__(self, owner, name: str) -> None:
        """Set the name of the attribute."""
        self.name = "_" + name


################################
# General descriptors
################################


class FunctionDescriptor(BaseDescriptor):
    """Validate that a value is a function."""

    def validate(self, value: Any, instance) -> Callable:
        """Validate the value is a function, and if so, returns it."""
        if not callable(value):
            raise QuestionCreationValidationError(
                f"Expected a function (got {value}).)"
            )
        return value


class IntegerDescriptor(BaseDescriptor):
    """
    Validate that a value is an integer.

    - `none_allowed` is whether None is allowed as a value.
    """

    def __init__(self, none_allowed: bool = False):
        """Initialize the descriptor."""
        self.none_allowed = none_allowed

    def validate(self, value, instance):
        """Validate the value is an integer."""
        if self.none_allowed:
            if not (isinstance(value, int) or value is None):
                raise QuestionAnswerValidationError(
                    f"Expected an integer or None (got {value})."
                )
        else:
            if not isinstance(value, int):
                raise QuestionAnswerValidationError(
                    f"Expected an integer (got {value})."
                )


class IntegerOrNoneDescriptor(BaseDescriptor):
    """Validate that a value is an integer or None."""

    def validate(self, value, instance):
        """Validate the value is an integer or None."""
        if not (isinstance(value, int) or value is None):
            raise QuestionCreationValidationError(
                f"Expected an integer or None (got {value})."
            )


class NumericalOrNoneDescriptor(BaseDescriptor):
    """Validate that a value is a number or None."""

    def validate(self, value, instance):
        """Validate the value is a number or None."""
        if not is_number_or_none(value):
            raise QuestionAnswerValidationError(
                f"Expected a number or None (got {value})."
            )


################################
# Attribute-specific descriptors
################################


class AnswerTemplateDescriptor(BaseDescriptor):
    """Validate that the answer template is a dictionary with string keys and string values."""

    def validate(self, value: Any, instance) -> None:
        """Validate the answer template."""
        if not isinstance(value, dict):
            raise QuestionCreationValidationError(
                f"`answer_template` must be a dictionary (got {value}).)"
            )
        if not all(isinstance(x, str) for x in value.keys()):
            raise QuestionCreationValidationError(
                f"`answer_template` keys must be strings (got {value})."
            )


class InstructionsDescriptor(BaseDescriptor):
    """Validate that the `instructions` attribute is a string."""

    def validate(self, value, instance):
        """Validate the value is a string."""
        # if not isinstance(value, str):
        #     raise QuestionCreationValidationError(
        #         f"Question `instructions` must be a string (got {value})."
        #     )
        pass


class NumSelectionsDescriptor(BaseDescriptor):
    """Validate that `num_selections` is an integer, is less than the number of options, and is positive."""

    def validate(self, value, instance):
        """Validate the value is an integer, is less than the number of options, and is positive."""
        if not (isinstance(value, int)):
            raise QuestionCreationValidationError(
                f"`num_selections` must be an integer (got {value})."
            )
        if value > len(instance.question_options):
            raise QuestionAnswerValidationError(
                f"`num_selections` must be less than the number of options (got {value})."
            )
        if value < 1:
            raise QuestionAnswerValidationError(
                f"`num_selections` must a positive integer (got {value})."
            )


class OptionLabelDescriptor(BaseDescriptor):
    """Validate that the `option_label` attribute is a string.

    >>> class TestQuestion:
    ...     option_label = OptionLabelDescriptor()
    ...     def __init__(self, option_label: str):
    ...         self.option_label = option_label

    >>> _ = TestQuestion("{{Option}}")

    """

    def validate(self, value, instance):
        """Validate the value is a string."""
        if isinstance(value, str):
            if "{{" in value and "}}" in value:
                # they're trying to use a dynamic question name - let's let this play out
                return None

        key_values = [int(v) for v in value.keys()]

        if value and (key_values := [float(v) for v in value.keys()]) != []:
            if min(key_values) != min(instance.question_options):
                raise QuestionCreationValidationError(
                    f"First option needs a label (got {value})"
                )
            if max(key_values) != max(instance.question_options):
                raise QuestionCreationValidationError(
                    f"Last option needs a label (got {value})"
                )
            if not all(isinstance(x, str) for x in value.values()):
                raise QuestionCreationValidationError(
                    "Option labels must be strings (got {value})."
                )
            for key in key_values:
                if key not in instance.question_options:
                    raise QuestionCreationValidationError(
                        f"Option label key ({key}) is not in question options ({instance.question_options})."
                    )

            if len(value.values()) != len(set(value.values())):
                raise QuestionCreationValidationError(
                    f"Option labels must be unique (got {value})."
                )


class QuestionNameDescriptor(BaseDescriptor):
    """Validate that the `question_name` attribute is a valid variable name."""

    def validate(self, value, instance):
        """Validate the value is a valid variable name."""
        from edsl.utilities.utilities import is_valid_variable_name

        if "{{" in value and "}}" in value:
            # they're trying to use a dynamic question name - let's let this play out
            return None

        if value.endswith("_comment") or value.endswith("_generated_tokens"):
            raise QuestionCreationValidationError(
                f"`question_name` cannot end with '_comment' or '_generated_tokens - (got {value})."
            )

        if not is_valid_variable_name(value):
            raise QuestionCreationValidationError(
                f"`question_name` is not a valid variable name (got {value})."
            )


class QuestionOptionsDescriptor(BaseDescriptor):
    """Validate that `question_options` is a list, does not exceed the min/max lengths, and has unique items."""

    @classmethod
    def example(cls):
        class TestQuestion:
            question_options = QuestionOptionsDescriptor()

            def __init__(self, question_options: List[str]):
                self.question_options = question_options

        return TestQuestion

    def __init__(
        self,
        num_choices: int = None,
        linear_scale: bool = False,
        q_budget: bool = False,
    ):
        """Initialize the descriptor."""
        self.num_choices = num_choices
        self.linear_scale = linear_scale
        self.q_budget = q_budget

    def validate(self, value: Any, instance) -> None:
        """Validate the question options.

        >>> q_class = QuestionOptionsDescriptor.example()
        >>> _ = q_class(["a", "b", "c"])
        >>> _ = q_class(["a", "b", "c", "d", "d"])
        Traceback (most recent call last):
        ...
        edsl.exceptions.questions.QuestionCreationValidationError: Question options must be unique (got ['a', 'b', 'c', 'd', 'd']).

        We allow dynamic question options, which are strings of the form '{{ question_options }}'.

        >>> _ = q_class("{{dynamic_options}}")
        >>> _ = q_class("dynamic_options")
        Traceback (most recent call last):
        ...
        edsl.exceptions.questions.QuestionCreationValidationError: ...
        """
        if isinstance(value, str):
            # Check if the string is a dynamic question option
            if "{{" in value and "}}" in value:
                return None
            else:
                raise QuestionCreationValidationError(
                    f"Dynamic question options must have jinja2 braces - instead received: {value}."
                )
        if not isinstance(value, list):
            raise QuestionCreationValidationError(
                f"Question options must be a list (got {value})."
            )
        if len(value) > Settings.MAX_NUM_OPTIONS:
            raise QuestionCreationValidationError(
                f"Too many question options (got {value})."
            )
        if len(value) < Settings.MIN_NUM_OPTIONS:
            raise QuestionCreationValidationError(
                f"Too few question options (got {value})."
            )
        # handle the case when question_options is a list of lists (a list of list can be converted to set)
        tmp_value = [str(x) for x in value]
        if len(tmp_value) != len(set(tmp_value)):
            raise QuestionCreationValidationError(
                f"Question options must be unique (got {value})."
            )
        if not self.linear_scale:
            if not self.q_budget:
                pass
            #     if not (
            #         value
            #         and all(type(x) == type(value[0]) for x in value)
            #         and isinstance(value[0], (str, list, int, float))
            #     ):
            #         raise QuestionCreationValidationError(
            #             f"Question options must be all same type (got {value}).)"
            #         )
            else:
                if not all(isinstance(x, (str)) for x in value):
                    raise QuestionCreationValidationError(
                        f"Question options must be strings (got {value}).)"
                    )
            if not all(
                [
                    type(option) != str
                    or (len(option) >= 1 and len(option) < Settings.MAX_OPTION_LENGTH)
                    for option in value
                ]
            ):
                raise QuestionCreationValidationError(
                    f"All question options must be at least 1 character long but less than {Settings.MAX_OPTION_LENGTH} characters long (got {value})."
                )

        if hasattr(instance, "min_selections") and instance.min_selections != None:
            if instance.min_selections > len(value):
                raise QuestionCreationValidationError(
                    f"You asked for at least {instance.min_selections} selections, but provided fewer options (got {value})."
                )
        if hasattr(instance, "max_selections") and instance.max_selections != None:
            if instance.max_selections > len(value):
                raise QuestionCreationValidationError(
                    f"You asked for at most {instance.max_selections} selections, but provided fewer options (got {value})."
                )
        if self.num_choices is not None:
            if len(value) != self.num_choices:
                raise QuestionCreationValidationError(
                    f"You asked for {self.num_choices} selections, but provided {len(value)} options."
                )
        if self.linear_scale:
            if sorted(value) != list(range(min(value), max(value) + 1)):
                raise QuestionCreationValidationError(
                    f"LinearScale.question_options must be a list of successive integers, e.g. [1, 2, 3] (got {value})."
                )


class QuestionTextDescriptor(BaseDescriptor):
    """Validate that the `question_text` attribute is a string.


    >>> class TestQuestion:
    ...     question_text = QuestionTextDescriptor()
    ...     def __init__(self, question_text: str):
    ...         self.question_text = question_text

    >>> _ = TestQuestion("What is the capital of France?")
    >>> _ = TestQuestion("What is the capital of France? {{variable}}")
    >>> _ = TestQuestion("What is the capital of France? {{variable name}}")
    Traceback (most recent call last):
    ...
    edsl.exceptions.questions.QuestionCreationValidationError: Question text contains an invalid identifier: 'variable name'
    """

    def validate(self, value, instance):
        """Validate the value is a string."""
        # if len(value) > Settings.MAX_QUESTION_LENGTH:
        #     raise Exception("Question is too long!")
        if len(value) < 1:
            raise Exception("Question is too short!")
        if not isinstance(value, str):
            raise Exception("Question must be a string!")
        if contains_single_braced_substring(value):
            import warnings

            # # warnings.warn(
            # #     f"WARNING: Question text contains a single-braced substring: If you intended to parameterize the question with a Scenario this should be changed to a double-braced substring, e.g. {{variable}}.\nSee details on constructing Scenarios in the docs: https://docs.expectedparrot.com/en/latest/scenarios.html",
            # #     UserWarning,
            # # )
            warnings.warn(
                "WARNING: Question text contains a single-braced substring. "
                "If you intended to parameterize the question with a Scenario, this will "
                "be changed to a double-braced substring, e.g. {{variable}}.\n"
                "See details on constructing Scenarios in the docs: "
                "https://docs.expectedparrot.com/en/latest/scenarios.html",
                UserWarning,
            )
            # Automatically replace single braces with double braces
            # This is here because if the user is using an f-string, the double brace will get converted to a single brace.
            # This undoes that.
            value = re.sub(r"\{([^\{\}]+)\}", r"{{\1}}", value)
            return value

        # iterate through all doubles braces and check if they are valid python identifiers
        for match in re.finditer(r"\{\{([^\{\}]+)\}\}", value):
            if " " in match.group(1).strip():
                raise QuestionCreationValidationError(
                    f"Question text contains an invalid identifier: '{match.group(1)}'"
                )

        return None


class ValueTypesDescriptor(BaseDescriptor):
    def validate(self, value, instance):
        """Validate the value is a list of strings or None."""
        if value is None:  # Allow None as a valid value
            return None
        if not isinstance(value, list):
            raise QuestionCreationValidationError(
                f"`value_types` must be a list or None (got {value})."
            )
        # Convert all items in the list to strings
        return [str(item) for item in value]


class ValueDescriptionsDescriptor(BaseDescriptor):
    def validate(self, value, instance):
        """Validate the value is a list of strings or None."""
        if value is None:  # Allow None as a valid value
            return None
        if not isinstance(value, list):
            raise QuestionCreationValidationError(
                f"`value_descriptions` must be a list or None (got {value})."
            )
        if not all(isinstance(x, str) for x in value):
            raise QuestionCreationValidationError(
                f"`value_descriptions` must be a list of strings (got {value})."
            )
        return value


class AnswerKeysDescriptor(BaseDescriptor):
    """Validate that the `answer_keys` attribute is a list of strings or integers."""

    def validate(self, value, instance):
        """Validate the value is a list of strings or integers."""
        if not isinstance(value, list):
            raise QuestionCreationValidationError(
                f"`answer_keys` must be a list (got {value})."
            )
        if not all(isinstance(x, (str, int)) for x in value):
            raise QuestionCreationValidationError(
                f"`answer_keys` must be a list of strings or integers (got {value})."
            )


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
