from typing import Union, Optional, TYPE_CHECKING
from edsl.exceptions.surveys import SurveyError

if TYPE_CHECKING:
    from edsl.questions.QuestionBase import QuestionBase

from edsl.exceptions.surveys import SurveyError, SurveyCreationError
from .Rule import Rule
from .base import RulePriority, EndOfSurvey


class EditSurvey:

    def __init__(self, survey):
        self.survey = survey

    def move_question(self, identifier: Union[str, int], new_index: int) -> "Survey":
        if isinstance(identifier, str):
            if identifier not in self.survey.question_names:
                raise SurveyError(
                    f"Question name '{identifier}' does not exist in the survey."
                )
            index = self.survey.question_name_to_index[identifier]
        elif isinstance(identifier, int):
            if identifier < 0 or identifier >= len(self.survey.questions):
                raise SurveyError(f"Index {identifier} is out of range.")
            index = identifier
        else:
            raise SurveyError(
                "Identifier must be either a string (question name) or an integer (question index)."
            )

        moving_question = self.survey._questions[index]

        new_survey = self.survey.delete_question(index)
        new_survey.add_question(moving_question, new_index)
        return new_survey

    def add_question(
        self, question: "QuestionBase", index: Optional[int] = None
    ) -> "Survey":

        if question.question_name in self.survey.question_names:
            raise SurveyCreationError(
                f"""Question name '{question.question_name}' already exists in survey. Existing names are {self.survey.question_names}."""
            )
        if index is None:
            index = len(self.survey.questions)

        if index > len(self.survey.questions):
            raise SurveyCreationError(
                f"Index {index} is greater than the number of questions in the survey."
            )
        if index < 0:
            raise SurveyCreationError(f"Index {index} is less than 0.")

        interior_insertion = index != len(self.survey.questions)

        # index = len(self.survey.questions)
        # TODO: This is a bit ugly because the user
        # doesn't "know" about _questions - it's generated by the
        # descriptor.
        self.survey._questions.insert(index, question)

        if interior_insertion:
            for question_name, old_index in self.survey._pseudo_indices.items():
                if old_index >= index:
                    self.survey._pseudo_indices[question_name] = old_index + 1

        self.survey._pseudo_indices[question.question_name] = index

        ## Re-do question_name to index - this is done automatically
        # for question_name, old_index in self.survey.question_name_to_index.items():
        #     if old_index >= index:
        #         self.survey.question_name_to_index[question_name] = old_index + 1

        ## Need to re-do the rule collection and the indices of the questions

        ## If a rule is before the insertion index and next_q is also before the insertion index, no change needed.
        ## If the rule is before the insertion index but next_q is after the insertion index, increment the next_q by 1
        ## If the rule is after the insertion index, increment the current_q by 1 and the next_q by 1

        # using index + 1 presumes there is a next question
        if interior_insertion:
            for rule in self.survey.rule_collection:
                if rule.current_q >= index:
                    rule.current_q += 1
                if rule.next_q >= index:
                    rule.next_q += 1

        # add a new rule
        self.survey.rule_collection.add_rule(
            Rule(
                current_q=index,
                expression="True",
                next_q=index + 1,
                question_name_to_index=self.survey.question_name_to_index,
                priority=RulePriority.DEFAULT.value,
            )
        )

        # a question might be added before the memory plan is created
        # it's ok because the memory plan will be updated when it is created
        if hasattr(self.survey, "memory_plan"):
            self.survey.memory_plan.add_question(question)

        return self.survey

    def delete_question(self, identifier: Union[str, int]) -> "Survey":
        """
        Delete a question from the survey.

        :param identifier: The name or index of the question to delete.
        :return: The updated Survey object.

        >>> from edsl import QuestionMultipleChoice, Survey
        >>> q1 = QuestionMultipleChoice(question_text="Q1", question_options=["A", "B"], question_name="q1")
        >>> q2 = QuestionMultipleChoice(question_text="Q2", question_options=["C", "D"], question_name="q2")
        >>> s = Survey().add_question(q1).add_question(q2)
        >>> _ = s.delete_question("q1")
        >>> len(s.questions)
        1
        >>> _ = s.delete_question(0)
        >>> len(s.questions)
        0
        """
        if isinstance(identifier, str):
            if identifier not in self.survey.question_names:
                raise SurveyError(
                    f"Question name '{identifier}' does not exist in the survey."
                )
            index = self.survey.question_name_to_index[identifier]
        elif isinstance(identifier, int):
            if identifier < 0 or identifier >= len(self.survey.questions):
                raise SurveyError(f"Index {identifier} is out of range.")
            index = identifier
        else:
            raise SurveyError(
                "Identifier must be either a string (question name) or an integer (question index)."
            )

        # Remove the question
        deleted_question = self.survey._questions.pop(index)
        del self.survey._pseudo_indices[deleted_question.question_name]

        # Update indices
        for question_name, old_index in self.survey._pseudo_indices.items():
            if old_index > index:
                self.survey._pseudo_indices[question_name] = old_index - 1

        # Update rules
        from .RuleCollection import RuleCollection

        new_rule_collection = RuleCollection()
        for rule in self.survey.rule_collection:
            if rule.current_q == index:
                continue  # Remove rules associated with the deleted question
            if rule.current_q > index:
                rule.current_q -= 1
            if rule.next_q > index:
                rule.next_q -= 1

            if rule.next_q == index:
                if index == len(self.survey.questions):
                    rule.next_q = EndOfSurvey
                else:
                    rule.next_q = index

            new_rule_collection.add_rule(rule)
        self.survey.rule_collection = new_rule_collection

        # Update memory plan if it exists
        if hasattr(self.survey, "memory_plan"):
            self.survey.memory_plan.remove_question(deleted_question.question_name)

        return self.survey

    def add_instruction(
        self, instruction: Union["Instruction", "ChangeInstruction"]
    ) -> "Survey":
        """
        Add an instruction to the survey.

        :param instruction: The instruction to add to the survey.

        >>> from edsl import Instruction
        >>> from edsl.surveys.Survey import Survey
        >>> i = Instruction(text="Pay attention to the following questions.", name="intro")
        >>> s = Survey().add_instruction(i)
        >>> s.instruction_names_to_instructions
        {'intro': Instruction(name="intro", text="Pay attention to the following questions.")}
        >>> s._pseudo_indices
        {'intro': -0.5}
        """
        import math

        if instruction.name in self.survey.instruction_names_to_instructions:
            raise SurveyCreationError(
                f"""Instruction name '{instruction.name}' already exists in survey. Existing names are {self.survey.instruction_names_to_instructions.keys()}."""
            )
        self.survey.instruction_names_to_instructions[instruction.name] = instruction

        # was the last thing added an instruction or a question?
        if self.survey._last_item_was_instruction:
            pseudo_index = (
                self.survey.max_pseudo_index
                + (
                    math.ceil(self.survey.max_pseudo_index)
                    - self.survey.max_pseudo_index
                )
                / 2
            )
        else:
            pseudo_index = self.survey.max_pseudo_index + 1.0 / 2.0
        self.survey._pseudo_indices[instruction.name] = pseudo_index

        return self.survey


if __name__ == "__main__":
    import doctest

    doctest.testmod()
