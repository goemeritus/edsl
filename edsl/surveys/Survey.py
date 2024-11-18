"""A Survey is collection of questions that can be administered to an Agent."""

from __future__ import annotations
import re
import tempfile
import requests

from typing import Any, Generator, Optional, Union, List, Literal, Callable
from uuid import uuid4

from edsl.base.Base import Base
from edsl.exceptions import SurveyCreationError, SurveyHasNoRulesError
from edsl.exceptions.surveys import SurveyError

from edsl.questions.QuestionBase import QuestionBase
from edsl.surveys.base import RulePriority, EndOfSurvey
from edsl.surveys.DAG import DAG
from edsl.surveys.descriptors import QuestionsDescriptor
from edsl.surveys.MemoryPlan import MemoryPlan
from edsl.surveys.Rule import Rule
from edsl.surveys.RuleCollection import RuleCollection
from edsl.surveys.SurveyExportMixin import SurveyExportMixin
from edsl.surveys.SurveyFlowVisualizationMixin import SurveyFlowVisualizationMixin
from edsl.utilities.decorators import remove_edsl_version

from edsl.agents.Agent import Agent

from edsl.surveys.instructions.InstructionCollection import InstructionCollection
from edsl.surveys.instructions.Instruction import Instruction
from edsl.surveys.instructions.ChangeInstruction import ChangeInstruction


class ValidatedString(str):
    def __new__(cls, content):
        if "<>" in content:
            raise SurveyCreationError(
                "The expression contains '<>', which is not allowed. You probably mean '!='."
            )
        return super().__new__(cls, content)


class Survey(SurveyExportMixin, SurveyFlowVisualizationMixin, Base):
    """A collection of questions that supports skip logic."""

    questions = QuestionsDescriptor()
    """
    A collection of questions that supports skip logic.

    Initalization:
    - `questions`: the questions in the survey (optional)
    - `question_names`: the names of the questions (optional)
    - `name`: the name of the survey (optional)

    Methods:
    -

    Notes:
    - The presumed order of the survey is the order in which questions are added.
    """

    def __init__(
        self,
        questions: Optional[
            list[Union[QuestionBase, Instruction, ChangeInstruction]]
        ] = None,
        memory_plan: Optional[MemoryPlan] = None,
        rule_collection: Optional[RuleCollection] = None,
        question_groups: Optional[dict[str, tuple[int, int]]] = None,
        name: Optional[str] = None,
    ):
        """Create a new survey.

        :param questions: The questions in the survey.
        :param memory_plan: The memory plan for the survey.
        :param rule_collection: The rule collection for the survey.
        :param question_groups: The groups of questions in the survey.
        :param name: The name of the survey - DEPRECATED.


        >>> from edsl import QuestionFreeText
        >>> q1 = QuestionFreeText(question_text = "What is your name?", question_name = "name")
        >>> q2 = QuestionFreeText(question_text = "What is your favorite color?", question_name = "color")
        >>> q3 = QuestionFreeText(question_text = "Is a hot dog a sandwich", question_name = "food")
        >>> s = Survey([q1, q2, q3], question_groups = {"demographics": (0, 1), "substantive":(3)})


        """

        self.raw_passed_questions = questions

        (
            true_questions,
            instruction_names_to_instructions,
            self.pseudo_indices,
        ) = self._separate_questions_and_instructions(questions or [])

        self.rule_collection = RuleCollection(
            num_questions=len(true_questions) if true_questions else None
        )
        # the RuleCollection needs to be present while we add the questions; we might override this later
        # if a rule_collection is provided. This allows us to serialize the survey with the rule_collection.

        self.questions = true_questions
        self.instruction_names_to_instructions = instruction_names_to_instructions

        self.memory_plan = memory_plan or MemoryPlan(self)
        if question_groups is not None:
            self.question_groups = question_groups
        else:
            self.question_groups = {}

        # if a rule collection is provided, use it instead
        if rule_collection is not None:
            self.rule_collection = rule_collection

        if name is not None:
            import warnings

            warnings.warn("name parameter to a survey is deprecated.")

    # region: Suvry instruction handling
    @property
    def relevant_instructions_dict(self) -> InstructionCollection:
        """Return a dictionary with keys as question names and values as instructions that are relevant to the question.

        >>> s = Survey.example(include_instructions=True)
        >>> s.relevant_instructions_dict
        {'q0': [Instruction(name="attention", text="Please pay attention!")], 'q1': [Instruction(name="attention", text="Please pay attention!")], 'q2': [Instruction(name="attention", text="Please pay attention!")]}

        """
        return InstructionCollection(
            self.instruction_names_to_instructions, self.questions
        )

    @staticmethod
    def _separate_questions_and_instructions(questions_and_instructions: list) -> tuple:
        """
        The 'pseudo_indices' attribute is a dictionary that maps question names to pseudo-indices
        that are used to order questions and instructions in the survey.
        Only questions get real indices; instructions get pseudo-indices.
        However, the order of the pseudo-indices is the same as the order questions and instructions are added to the survey.

        We don't have to know how many instructions there are to calculate the pseudo-indices because they are
        calculated by the inverse of one minus the sum of 1/2^n for n in the number of instructions run so far.

        >>> from edsl import Instruction
        >>> i = Instruction(text = "Pay attention to the following questions.", name = "intro")
        >>> i2 = Instruction(text = "How are you feeling today?", name = "followon_intro")
        >>> from edsl import QuestionFreeText; q1 = QuestionFreeText.example()
        >>> from edsl import QuestionMultipleChoice; q2 = QuestionMultipleChoice.example()
        >>> s = Survey([q1, i, i2, q2])
        >>> len(s.instruction_names_to_instructions)
        2
        >>> s.pseudo_indices
        {'how_are_you': 0, 'intro': 0.5, 'followon_intro': 0.75, 'how_feeling': 1}

        >>> from edsl import ChangeInstruction
        >>> q3 = QuestionFreeText(question_text = "What is your favorite color?", question_name = "color")
        >>> i_change = ChangeInstruction(drop = ["intro"])
        >>> s = Survey([q1, i, q2, i_change, q3])
        >>> [i.name for i in s.relevant_instructions(q1)]
        []
        >>> [i.name for i in s.relevant_instructions(q2)]
        ['intro']
        >>> [i.name for i in s.relevant_instructions(q3)]
        []

        >>> i_change = ChangeInstruction(keep = ["poop"], drop = [])
        >>> s = Survey([q1, i, q2, i_change])
        Traceback (most recent call last):
        ...
        ValueError: ChangeInstruction change_instruction_0 references instruction poop which does not exist.
        """
        from edsl.surveys.instructions.Instruction import Instruction
        from edsl.surveys.instructions.ChangeInstruction import ChangeInstruction

        true_questions = []
        instruction_names_to_instructions = {}

        num_change_instructions = 0
        pseudo_indices = {}
        instructions_run_length = 0
        for entry in questions_and_instructions:
            if isinstance(entry, Instruction) or isinstance(entry, ChangeInstruction):
                if isinstance(entry, ChangeInstruction):
                    entry.add_name(num_change_instructions)
                    num_change_instructions += 1
                    for prior_instruction in entry.keep + entry.drop:
                        if prior_instruction not in instruction_names_to_instructions:
                            raise ValueError(
                                f"ChangeInstruction {entry.name} references instruction {prior_instruction} which does not exist."
                            )
                instructions_run_length += 1
                delta = 1 - 1.0 / (2.0**instructions_run_length)
                pseudo_index = (len(true_questions) - 1) + delta
                entry.pseudo_index = pseudo_index
                instruction_names_to_instructions[entry.name] = entry
            elif isinstance(entry, QuestionBase):
                pseudo_index = len(true_questions)
                instructions_run_length = 0
                true_questions.append(entry)
            else:
                raise ValueError(
                    f"Entry {repr(entry)} is not a QuestionBase or an Instruction."
                )

            pseudo_indices[entry.name] = pseudo_index

        return true_questions, instruction_names_to_instructions, pseudo_indices

    def relevant_instructions(self, question) -> dict:
        """This should be a dictionry with keys as question names and values as instructions that are relevant to the question.

        :param question: The question to get the relevant instructions for.

        # Did the instruction come before the question and was it not modified by a change instruction?

        """
        return self.relevant_instructions_dict[question]

    @property
    def max_pseudo_index(self) -> float:
        """Return the maximum pseudo index in the survey.

        Example:

        >>> s = Survey.example()
        >>> s.max_pseudo_index
        2
        """
        if len(self.pseudo_indices) == 0:
            return -1
        return max(self.pseudo_indices.values())

    @property
    def last_item_was_instruction(self) -> bool:
        """Return whether the last item added to the survey was an instruction.
        This is used to determine the pseudo-index of the next item added to the survey.

        Example:

        >>> s = Survey.example()
        >>> s.last_item_was_instruction
        False
        >>> from edsl.surveys.instructions.Instruction import Instruction
        >>> s = s.add_instruction(Instruction(text="Pay attention to the following questions.", name="intro"))
        >>> s.last_item_was_instruction
        True
        """
        return isinstance(self.max_pseudo_index, float)

    def add_instruction(
        self, instruction: Union["Instruction", "ChangeInstruction"]
    ) -> Survey:
        """
        Add an instruction to the survey.

        :param instruction: The instruction to add to the survey.

        >>> from edsl import Instruction
        >>> i = Instruction(text="Pay attention to the following questions.", name="intro")
        >>> s = Survey().add_instruction(i)
        >>> s.instruction_names_to_instructions
        {'intro': Instruction(name="intro", text="Pay attention to the following questions.")}
        >>> s.pseudo_indices
        {'intro': -0.5}
        """
        import math

        if instruction.name in self.instruction_names_to_instructions:
            raise SurveyCreationError(
                f"""Instruction name '{instruction.name}' already exists in survey. Existing names are {self.instruction_names_to_instructions.keys()}."""
            )
        self.instruction_names_to_instructions[instruction.name] = instruction

        # was the last thing added an instruction or a question?
        if self.last_item_was_instruction:
            pseudo_index = (
                self.max_pseudo_index
                + (math.ceil(self.max_pseudo_index) - self.max_pseudo_index) / 2
            )
        else:
            pseudo_index = self.max_pseudo_index + 1.0 / 2.0
        self.pseudo_indices[instruction.name] = pseudo_index

        return self

    # endregion

    # region: Simulation methods

    @classmethod
    def random_survey(self):
        """Create a random survey."""
        from edsl.questions import QuestionMultipleChoice, QuestionFreeText
        from random import choice

        num_questions = 10
        questions = []
        for i in range(num_questions):
            if choice([True, False]):
                q = QuestionMultipleChoice(
                    question_text="nothing",
                    question_name="q_" + str(i),
                    question_options=list(range(3)),
                )
                questions.append(q)
            else:
                questions.append(
                    QuestionFreeText(
                        question_text="nothing", question_name="q_" + str(i)
                    )
                )
        s = Survey(questions)
        start_index = choice(range(num_questions - 1))
        end_index = choice(range(start_index + 1, 10))
        s = s.add_rule(f"q_{start_index}", "True", f"q_{end_index}")
        question_to_delete = choice(range(num_questions))
        s.delete_question(f"q_{question_to_delete}")
        return s

    def simulate(self) -> dict:
        """Simulate the survey and return the answers."""
        i = self.gen_path_through_survey()
        q = next(i)
        num_passes = 0
        while True:
            num_passes += 1
            try:
                answer = q._simulate_answer()
                q = i.send({q.question_name: answer["answer"]})
            except StopIteration:
                break

            if num_passes > 100:
                print("Too many passes.")
                raise Exception("Too many passes.")
        return self.answers

    def create_agent(self) -> "Agent":
        """Create an agent from the simulated answers."""
        answers_dict = self.simulate()

        def construct_answer_dict_function(traits: dict) -> Callable:
            def func(self, question: "QuestionBase", scenario=None):
                return traits.get(question.question_name, None)

            return func

        return Agent(traits=answers_dict).add_direct_question_answering_method(
            construct_answer_dict_function(answers_dict)
        )

    def simulate_results(self) -> "Results":
        """Simulate the survey and return the results."""
        a = self.create_agent()
        return self.by([a]).run()

    # endregion

    # region: Access methods
    def _get_question_index(
        self, q: Union[QuestionBase, str, EndOfSurvey.__class__]
    ) -> Union[int, EndOfSurvey.__class__]:
        """Return the index of the question or EndOfSurvey object.

        :param q: The question or question name to get the index of.

        It can handle it if the user passes in the question name, the question object, or the EndOfSurvey object.

        >>> s = Survey.example()
        >>> s._get_question_index("q0")
        0

        This doesnt' work with questions that don't exist:

        >>> s._get_question_index("poop")
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyError: Question name poop not found in survey. The current question names are {'q0': 0, 'q1': 1, 'q2': 2}.
        ...
        """
        if q == EndOfSurvey:
            return EndOfSurvey
        else:
            question_name = q if isinstance(q, str) else q.question_name
            if question_name not in self.question_name_to_index:
                raise SurveyError(
                    f"""Question name {question_name} not found in survey. The current question names are {self.question_name_to_index}."""
                )
            return self.question_name_to_index[question_name]

    def get(self, question_name: str) -> QuestionBase:
        """
        Return the question object given the question name.

        :param question_name: The name of the question to get.

        >>> s = Survey.example()
        >>> s.get_question("q0")
        Question('multiple_choice', question_name = \"""q0\""", question_text = \"""Do you like school?\""", question_options = ['yes', 'no'])
        """
        if question_name not in self.question_name_to_index:
            raise SurveyError(f"Question name {question_name} not found in survey.")
        index = self.question_name_to_index[question_name]
        return self._questions[index]

    def get_question(self, question_name: str) -> QuestionBase:
        """Return the question object given the question name."""
        # import warnings
        # warnings.warn("survey.get_question is deprecated. Use subscript operator instead.")
        return self.get(question_name)

    def question_names_to_questions(self) -> dict:
        """Return a dictionary mapping question names to question attributes."""
        return {q.question_name: q for q in self.questions}

    @property
    def question_names(self) -> list[str]:
        """Return a list of question names in the survey.

        Example:

        >>> s = Survey.example()
        >>> s.question_names
        ['q0', 'q1', 'q2']
        """
        return [q.question_name for q in self.questions]

    @property
    def question_name_to_index(self) -> dict[str, int]:
        """Return a dictionary mapping question names to question indices.

        Example:

        >>> s = Survey.example()
        >>> s.question_name_to_index
        {'q0': 0, 'q1': 1, 'q2': 2}
        """
        return {q.question_name: i for i, q in enumerate(self.questions)}

    # endregion

    # region: serialization methods
    def __hash__(self) -> int:
        """Return a hash of the question."""
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(add_edsl_version=False))

    def to_dict(self, add_edsl_version=True) -> dict[str, Any]:
        """Serialize the Survey object to a dictionary.

        >>> s = Survey.example()
        >>> s.to_dict(add_edsl_version = False).keys()
        dict_keys(['questions', 'memory_plan', 'rule_collection', 'question_groups'])
        """
        return {
            "questions": [
                q.to_dict(add_edsl_version=add_edsl_version)
                for q in self.recombined_questions_and_instructions()
            ],
            "memory_plan": self.memory_plan.to_dict(add_edsl_version=add_edsl_version),
            "rule_collection": self.rule_collection.to_dict(
                add_edsl_version=add_edsl_version
            ),
            "question_groups": self.question_groups,
        }

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict) -> Survey:
        """Deserialize the dictionary back to a Survey object.

        :param data: The dictionary to deserialize.

        >>> d = Survey.example().to_dict()
        >>> s = Survey.from_dict(d)
        >>> s == Survey.example()
        True

        >>> s = Survey.example(include_instructions = True)
        >>> d = s.to_dict()
        >>> news = Survey.from_dict(d)
        >>> news == s
        True

        """

        def get_class(pass_dict):
            if (class_name := pass_dict.get("edsl_class_name")) == "QuestionBase":
                return QuestionBase
            elif class_name == "Instruction":
                from edsl.surveys.instructions.Instruction import Instruction

                return Instruction
            elif class_name == "ChangeInstruction":
                from edsl.surveys.instructions.ChangeInstruction import (
                    ChangeInstruction,
                )

                return ChangeInstruction
            else:
                return QuestionBase

        questions = [
            get_class(q_dict).from_dict(q_dict) for q_dict in data["questions"]
        ]
        memory_plan = MemoryPlan.from_dict(data["memory_plan"])
        survey = cls(
            questions=questions,
            memory_plan=memory_plan,
            rule_collection=RuleCollection.from_dict(data["rule_collection"]),
            question_groups=data["question_groups"],
        )
        return survey

    # endregion

    # region: Survey template parameters
    @property
    def scenario_attributes(self) -> list[str]:
        """Return a list of attributes that admissible Scenarios should have.

        Here we have a survey with a question that uses a jinja2 style {{ }} template:

        >>> from edsl import QuestionFreeText
        >>> s = Survey().add_question(QuestionFreeText(question_text="{{ greeting }}. What is your name?", question_name="name"))
        >>> s.scenario_attributes
        ['greeting']

        >>> s = Survey().add_question(QuestionFreeText(question_text="{{ greeting }}. What is your {{ attribute }}?", question_name="name"))
        >>> s.scenario_attributes
        ['greeting', 'attribute']


        """
        temp = []
        for question in self.questions:
            question_text = question.question_text
            # extract the contents of all {{ }} in the question text using regex
            matches = re.findall(r"\{\{(.+?)\}\}", question_text)
            # remove whitespace
            matches = [match.strip() for match in matches]
            # add them to the temp list
            temp.extend(matches)
        return temp

    @property
    def parameters(self):
        """Return a set of parameters in the survey.

        >>> s = Survey.example()
        >>> s.parameters
        set()
        """
        return set.union(*[q.parameters for q in self.questions])

    @property
    def parameters_by_question(self):
        """Return a dictionary of parameters by question in the survey.
        >>> from edsl import QuestionFreeText
        >>> q = QuestionFreeText(question_name = "example", question_text = "What is the capital of {{ country}}?")
        >>> s = Survey([q])
        >>> s.parameters_by_question
        {'example': {'country'}}
        """
        return {q.question_name: q.parameters for q in self.questions}

    # endregion

    # region: Survey construction

    # region: Adding questions and combining surveys
    def __add__(self, other: Survey) -> Survey:
        """Combine two surveys.

        :param other: The other survey to combine with this one.
        >>> s1 = Survey.example()
        >>> from edsl import QuestionFreeText
        >>> s2 = Survey([QuestionFreeText(question_text="What is your name?", question_name="yo")])
        >>> s3 = s1 + s2
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: ...
        ...
        >>> s3 = s1.clear_non_default_rules() + s2
        >>> len(s3.questions)
        4

        """
        if (
            len(self.rule_collection.non_default_rules) > 0
            or len(other.rule_collection.non_default_rules) > 0
        ):
            raise SurveyCreationError(
                "Cannot combine two surveys with non-default rules. Please use the 'clear_non_default_rules' method to remove non-default rules from the survey.",
            )

        return Survey(questions=self.questions + other.questions)

    def move_question(self, identifier: Union[str, int], new_index: int):
        if isinstance(identifier, str):
            if identifier not in self.question_names:
                raise SurveyError(
                    f"Question name '{identifier}' does not exist in the survey."
                )
            index = self.question_name_to_index[identifier]
        elif isinstance(identifier, int):
            if identifier < 0 or identifier >= len(self.questions):
                raise SurveyError(f"Index {identifier} is out of range.")
            index = identifier
        else:
            raise SurveyError(
                "Identifier must be either a string (question name) or an integer (question index)."
            )

        moving_question = self._questions[index]

        new_survey = self.delete_question(index)
        new_survey.add_question(moving_question, new_index)
        return new_survey

    def delete_question(self, identifier: Union[str, int]) -> Survey:
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
            if identifier not in self.question_names:
                raise SurveyError(
                    f"Question name '{identifier}' does not exist in the survey."
                )
            index = self.question_name_to_index[identifier]
        elif isinstance(identifier, int):
            if identifier < 0 or identifier >= len(self.questions):
                raise SurveyError(f"Index {identifier} is out of range.")
            index = identifier
        else:
            raise SurveyError(
                "Identifier must be either a string (question name) or an integer (question index)."
            )

        # Remove the question
        deleted_question = self._questions.pop(index)
        del self.pseudo_indices[deleted_question.question_name]

        # Update indices
        for question_name, old_index in self.pseudo_indices.items():
            if old_index > index:
                self.pseudo_indices[question_name] = old_index - 1

        # Update rules
        new_rule_collection = RuleCollection()
        for rule in self.rule_collection:
            if rule.current_q == index:
                continue  # Remove rules associated with the deleted question
            if rule.current_q > index:
                rule.current_q -= 1
            if rule.next_q > index:
                rule.next_q -= 1

            if rule.next_q == index:
                if index == len(self.questions):
                    rule.next_q = EndOfSurvey
                else:
                    rule.next_q = index

            new_rule_collection.add_rule(rule)
        self.rule_collection = new_rule_collection

        # Update memory plan if it exists
        if hasattr(self, "memory_plan"):
            self.memory_plan.remove_question(deleted_question.question_name)

        return self

    def add_question(
        self, question: QuestionBase, index: Optional[int] = None
    ) -> Survey:
        """
        Add a question to survey.

        :param question: The question to add to the survey.
        :param question_name: The name of the question. If not provided, the question name is used.

        The question is appended at the end of the self.questions list
        A default rule is created that the next index is the next question.

        >>> from edsl import QuestionMultipleChoice
        >>> q = QuestionMultipleChoice(question_text = "Do you like school?", question_options=["yes", "no"], question_name="q0")
        >>> s = Survey().add_question(q)

        >>> s = Survey().add_question(q).add_question(q)
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: Question name 'q0' already exists in survey. Existing names are ['q0'].
        ...
        """
        if question.question_name in self.question_names:
            raise SurveyCreationError(
                f"""Question name '{question.question_name}' already exists in survey. Existing names are {self.question_names}."""
            )
        if index is None:
            index = len(self.questions)

        if index > len(self.questions):
            raise SurveyCreationError(
                f"Index {index} is greater than the number of questions in the survey."
            )
        if index < 0:
            raise SurveyCreationError(f"Index {index} is less than 0.")

        interior_insertion = index != len(self.questions)

        # index = len(self.questions)
        # TODO: This is a bit ugly because the user
        # doesn't "know" about _questions - it's generated by the
        # descriptor.
        self._questions.insert(index, question)

        if interior_insertion:
            for question_name, old_index in self.pseudo_indices.items():
                if old_index >= index:
                    self.pseudo_indices[question_name] = old_index + 1

        self.pseudo_indices[question.question_name] = index

        ## Re-do question_name to index - this is done automatically
        # for question_name, old_index in self.question_name_to_index.items():
        #     if old_index >= index:
        #         self.question_name_to_index[question_name] = old_index + 1

        ## Need to re-do the rule collection and the indices of the questions

        ## If a rule is before the insertion index and next_q is also before the insertion index, no change needed.
        ## If the rule is before the insertion index but next_q is after the insertion index, increment the next_q by 1
        ## If the rule is after the insertion index, increment the current_q by 1 and the next_q by 1

        # using index + 1 presumes there is a next question
        if interior_insertion:
            for rule in self.rule_collection:
                if rule.current_q >= index:
                    rule.current_q += 1
                if rule.next_q >= index:
                    rule.next_q += 1

        # add a new rule
        self.rule_collection.add_rule(
            Rule(
                current_q=index,
                expression="True",
                next_q=index + 1,
                question_name_to_index=self.question_name_to_index,
                priority=RulePriority.DEFAULT.value,
            )
        )

        # a question might be added before the memory plan is created
        # it's ok because the memory plan will be updated when it is created
        if hasattr(self, "memory_plan"):
            self.memory_plan.add_question(question)

        return self

    def recombined_questions_and_instructions(
        self,
    ) -> list[Union[QuestionBase, "Instruction"]]:
        """Return a list of questions and instructions sorted by pseudo index."""
        questions_and_instructions = self._questions + list(
            self.instruction_names_to_instructions.values()
        )
        return sorted(
            questions_and_instructions, key=lambda x: self.pseudo_indices[x.name]
        )

    # endregion

    # region: Memory plan methods
    def set_full_memory_mode(self) -> Survey:
        """Add instructions to a survey that the agent should remember all of the answers to the questions in the survey.

        >>> s = Survey.example().set_full_memory_mode()

        """
        self._set_memory_plan(lambda i: self.question_names[:i])
        return self

    def set_lagged_memory(self, lags: int) -> Survey:
        """Add instructions to a survey that the agent should remember the answers to the questions in the survey.

        The agent should remember the answers to the questions in the survey from the previous lags.
        """
        self._set_memory_plan(lambda i: self.question_names[max(0, i - lags) : i])
        return self

    def _set_memory_plan(self, prior_questions_func: Callable):
        """Set memory plan based on a provided function determining prior questions.

        :param prior_questions_func: A function that takes the index of the current question and returns a list of prior questions to remember.

        >>> s = Survey.example()
        >>> s._set_memory_plan(lambda i: s.question_names[:i])

        """
        for i, question_name in enumerate(self.question_names):
            self.memory_plan.add_memory_collection(
                focal_question=question_name,
                prior_questions=prior_questions_func(i),
            )

    def add_targeted_memory(
        self,
        focal_question: Union[QuestionBase, str],
        prior_question: Union[QuestionBase, str],
    ) -> Survey:
        """Add instructions to a survey than when answering focal_question.

        :param focal_question: The question that the agent is answering.
        :param prior_question: The question that the agent should remember when answering the focal question.

        Here we add instructions to a survey than when answering q2 they should remember q1:

        >>> s = Survey.example().add_targeted_memory("q2", "q0")
        >>> s.memory_plan
        {'q2': Memory(prior_questions=['q0'])}

        The agent should also remember the answers to prior_questions listed in prior_questions.
        """
        focal_question_name = self.question_names[
            self._get_question_index(focal_question)
        ]
        prior_question_name = self.question_names[
            self._get_question_index(prior_question)
        ]

        self.memory_plan.add_single_memory(
            focal_question=focal_question_name,
            prior_question=prior_question_name,
        )

        return self

    def add_memory_collection(
        self,
        focal_question: Union[QuestionBase, str],
        prior_questions: List[Union[QuestionBase, str]],
    ) -> Survey:
        """Add prior questions and responses so the agent has them when answering.

        This adds instructions to a survey than when answering focal_question, the agent should also remember the answers to prior_questions listed in prior_questions.

        :param focal_question: The question that the agent is answering.
        :param prior_questions: The questions that the agent should remember when answering the focal question.

        Here we have it so that when answering q2, the agent should remember answers to q0 and q1:

        >>> s = Survey.example().add_memory_collection("q2", ["q0", "q1"])
        >>> s.memory_plan
        {'q2': Memory(prior_questions=['q0', 'q1'])}
        """
        focal_question_name = self.question_names[
            self._get_question_index(focal_question)
        ]

        prior_question_names = [
            self.question_names[self._get_question_index(prior_question)]
            for prior_question in prior_questions
        ]

        self.memory_plan.add_memory_collection(
            focal_question=focal_question_name, prior_questions=prior_question_names
        )
        return self

    # endregion
    # endregion
    # endregion

    # region: Question groups
    def add_question_group(
        self,
        start_question: Union[QuestionBase, str],
        end_question: Union[QuestionBase, str],
        group_name: str,
    ) -> Survey:
        """Add a group of questions to the survey.

        :param start_question: The first question in the group.
        :param end_question: The last question in the group.
        :param group_name: The name of the group.

        Example:

        >>> s = Survey.example().add_question_group("q0", "q1", "group1")
        >>> s.question_groups
        {'group1': (0, 1)}

        The name of the group must be a valid identifier:

        >>> s = Survey.example().add_question_group("q0", "q2", "1group1")
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: Group name 1group1 is not a valid identifier.
        ...
        >>> s = Survey.example().add_question_group("q0", "q1", "q0")
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: ...
        ...
        >>> s = Survey.example().add_question_group("q1", "q0", "group1")
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: ...
        ...
        """

        if not group_name.isidentifier():
            raise SurveyCreationError(
                f"Group name {group_name} is not a valid identifier."
            )

        if group_name in self.question_groups:
            raise SurveyCreationError(
                f"Group name {group_name} already exists in the survey."
            )

        if group_name in self.question_name_to_index:
            raise SurveyCreationError(
                f"Group name {group_name} already exists as a question name in the survey."
            )

        start_index = self._get_question_index(start_question)
        end_index = self._get_question_index(end_question)

        if start_index > end_index:
            raise SurveyCreationError(
                f"Start index {start_index} is greater than end index {end_index}."
            )

        for existing_group_name, (
            existing_start_index,
            existing_end_index,
        ) in self.question_groups.items():
            if start_index < existing_start_index and end_index > existing_end_index:
                raise SurveyCreationError(
                    f"Group {group_name} contains the questions in the new group."
                )
            if start_index > existing_start_index and end_index < existing_end_index:
                raise SurveyCreationError(
                    f"Group {group_name} is contained in the new group."
                )
            if start_index < existing_start_index and end_index > existing_start_index:
                raise SurveyCreationError(
                    f"Group {group_name} overlaps with the new group."
                )
            if start_index < existing_end_index and end_index > existing_end_index:
                raise SurveyCreationError(
                    f"Group {group_name} overlaps with the new group."
                )

        self.question_groups[group_name] = (start_index, end_index)
        return self

    # endregion

    # region: Survey rules
    def show_rules(self) -> None:
        """Print out the rules in the survey.

        >>> s = Survey.example()
        >>> s.show_rules()
        ┏━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
        ┃ current_q ┃ expression  ┃ next_q ┃ priority ┃ before_rule ┃
        ┡━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
        │ 0         │ True        │ 1      │ -1       │ False       │
        │ 0         │ q0 == 'yes' │ 2      │ 0        │ False       │
        │ 1         │ True        │ 2      │ -1       │ False       │
        │ 2         │ True        │ 3      │ -1       │ False       │
        └───────────┴─────────────┴────────┴──────────┴─────────────┘
        """
        self.rule_collection.show_rules()

    def add_stop_rule(
        self, question: Union[QuestionBase, str], expression: str
    ) -> Survey:
        """Add a rule that stops the survey.
        The rule is evaluated *after* the question is answered. If the rule is true, the survey ends.

        :param question: The question to add the stop rule to.
        :param expression: The expression to evaluate.

        If this rule is true, the survey ends.

        Here, answering "yes" to q0 ends the survey:

        >>> s = Survey.example().add_stop_rule("q0", "q0 == 'yes'")
        >>> s.next_question("q0", {"q0": "yes"})
        EndOfSurvey

        By comparison, answering "no" to q0 does not end the survey:

        >>> s.next_question("q0", {"q0": "no"}).question_name
        'q1'

        >>> s.add_stop_rule("q0", "q1 <> 'yes'")
        Traceback (most recent call last):
        ...
        edsl.exceptions.surveys.SurveyCreationError: The expression contains '<>', which is not allowed. You probably mean '!='.
        ...
        """
        expression = ValidatedString(expression)
        prior_question_appears = False
        for prior_question in self.questions:
            if prior_question.question_name in expression:
                prior_question_appears = True

        if not prior_question_appears:
            import warnings

            warnings.warn(
                f"The expression {expression} does not contain any prior question names. This is probably a mistake."
            )
        self.add_rule(question, expression, EndOfSurvey)
        return self

    def clear_non_default_rules(self) -> Survey:
        """Remove all non-default rules from the survey.

        >>> Survey.example().show_rules()
        ┏━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
        ┃ current_q ┃ expression  ┃ next_q ┃ priority ┃ before_rule ┃
        ┡━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
        │ 0         │ True        │ 1      │ -1       │ False       │
        │ 0         │ q0 == 'yes' │ 2      │ 0        │ False       │
        │ 1         │ True        │ 2      │ -1       │ False       │
        │ 2         │ True        │ 3      │ -1       │ False       │
        └───────────┴─────────────┴────────┴──────────┴─────────────┘
        >>> Survey.example().clear_non_default_rules().show_rules()
        ┏━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
        ┃ current_q ┃ expression ┃ next_q ┃ priority ┃ before_rule ┃
        ┡━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
        │ 0         │ True       │ 1      │ -1       │ False       │
        │ 1         │ True       │ 2      │ -1       │ False       │
        │ 2         │ True       │ 3      │ -1       │ False       │
        └───────────┴────────────┴────────┴──────────┴─────────────┘
        """
        s = Survey()
        for question in self.questions:
            s.add_question(question)
        return s

    def add_skip_rule(
        self, question: Union[QuestionBase, str], expression: str
    ) -> Survey:
        """
        Adds a per-question skip rule to the survey.

        :param question: The question to add the skip rule to.
        :param expression: The expression to evaluate.

        This adds a rule that skips 'q0' always, before the question is answered:

        >>> from edsl import QuestionFreeText
        >>> q0 = QuestionFreeText.example()
        >>> q0.question_name = "q0"
        >>> q1 = QuestionFreeText.example()
        >>> q1.question_name = "q1"
        >>> s = Survey([q0, q1]).add_skip_rule("q0", "True")
        >>> s.next_question("q0", {}).question_name
        'q1'

        Note that this is different from a rule that jumps to some other question *after* the question is answered.

        """
        question_index = self._get_question_index(question)
        self._add_rule(question, expression, question_index + 1, before_rule=True)
        return self

    def _get_new_rule_priority(
        self, question_index: int, before_rule: bool = False
    ) -> int:
        """Return the priority for the new rule.

        :param question_index: The index of the question to add the rule to.
        :param before_rule: Whether the rule is evaluated before the question is answered.

        >>> s = Survey.example()
        >>> s._get_new_rule_priority(0)
        1
        """
        current_priorities = [
            rule.priority
            for rule in self.rule_collection.applicable_rules(
                question_index, before_rule
            )
        ]
        if len(current_priorities) == 0:
            return RulePriority.DEFAULT.value + 1

        max_priority = max(current_priorities)
        # newer rules take priority over older rules
        new_priority = (
            RulePriority.DEFAULT.value
            if len(current_priorities) == 0
            else max_priority + 1
        )
        return new_priority

    def add_rule(
        self,
        question: Union[QuestionBase, str],
        expression: str,
        next_question: Union[QuestionBase, int],
        before_rule: bool = False,
    ) -> Survey:
        """
        Add a rule to a Question of the Survey.

        :param question: The question to add the rule to.
        :param expression: The expression to evaluate.
        :param next_question: The next question to go to if the rule is true.
        :param before_rule: Whether the rule is evaluated before the question is answered.

        This adds a rule that if the answer to q0 is 'yes', the next question is q2 (as opposed to q1)

        >>> s = Survey.example().add_rule("q0", "{{ q0 }} == 'yes'", "q2")
        >>> s.next_question("q0", {"q0": "yes"}).question_name
        'q2'

        """
        return self._add_rule(
            question, expression, next_question, before_rule=before_rule
        )

    def _add_rule(
        self,
        question: Union[QuestionBase, str],
        expression: str,
        next_question: Union[QuestionBase, str, int],
        before_rule: bool = False,
    ) -> Survey:
        """
        Add a rule to a Question of the Survey with the appropriate priority.

        :param question: The question to add the rule to.
        :param expression: The expression to evaluate.
        :param next_question: The next question to go to if the rule is true.
        :param before_rule: Whether the rule is evaluated before the question is answered.


        - The last rule added for the question will have the highest priority.
        - If there are no rules, the rule added gets priority -1.
        """
        question_index = self._get_question_index(question)

        # Might not have the name of the next question yet
        if isinstance(next_question, int):
            next_question_index = next_question
        else:
            next_question_index = self._get_question_index(next_question)

        new_priority = self._get_new_rule_priority(question_index, before_rule)

        self.rule_collection.add_rule(
            Rule(
                current_q=question_index,
                expression=expression,
                next_q=next_question_index,
                question_name_to_index=self.question_name_to_index,
                priority=new_priority,
                before_rule=before_rule,
            )
        )

        return self

    # endregion

    # region: Forward methods
    def by(self, *args: Union["Agent", "Scenario", "LanguageModel"]) -> "Jobs":
        """Add Agents, Scenarios, and LanguageModels to a survey and returns a runnable Jobs object.

        :param args: The Agents, Scenarios, and LanguageModels to add to the survey.

        This takes the survey and adds an Agent and a Scenario via 'by' which converts to a Jobs object:

        >>> s = Survey.example(); from edsl import Agent; from edsl import Scenario
        >>> s.by(Agent.example()).by(Scenario.example())
        Jobs(...)
        """
        from edsl.jobs.Jobs import Jobs

        job = Jobs(survey=self)
        return job.by(*args)

    def to_jobs(self):
        """Convert the survey to a Jobs object."""
        from edsl.jobs.Jobs import Jobs

        return Jobs(survey=self)

    def show_prompts(self):
        return self.to_jobs().show_prompts()

    # endregion

    # region: Running the survey

    def __call__(
        self,
        model=None,
        agent=None,
        cache=None,
        disable_remote_cache: bool = False,
        disable_remote_inference: bool = False,
        **kwargs,
    ):
        """Run the survey with default model, taking the required survey as arguments.

        >>> from edsl.questions import QuestionFunctional
        >>> def f(scenario, agent_traits): return "yes" if scenario["period"] == "morning" else "no"
        >>> q = QuestionFunctional(question_name = "q0", func = f)
        >>> s = Survey([q])
        >>> s(period = "morning", cache = False, disable_remote_cache = True, disable_remote_inference = True).select("answer.q0").first()
        'yes'
        >>> s(period = "evening", cache = False, disable_remote_cache = True, disable_remote_inference = True).select("answer.q0").first()
        'no'
        """
        job = self.get_job(model, agent, **kwargs)
        return job.run(
            cache=cache,
            disable_remote_cache=disable_remote_cache,
            disable_remote_inference=disable_remote_inference,
        )

    async def run_async(
        self,
        model: Optional["Model"] = None,
        agent: Optional["Agent"] = None,
        cache: Optional["Cache"] = None,
        disable_remote_inference: bool = False,
        **kwargs,
    ):
        """Run the survey with default model, taking the required survey as arguments.

        >>> import asyncio
        >>> from edsl.questions import QuestionFunctional
        >>> def f(scenario, agent_traits): return "yes" if scenario["period"] == "morning" else "no"
        >>> q = QuestionFunctional(question_name = "q0", func = f)
        >>> s = Survey([q])
        >>> async def test_run_async(): result = await s.run_async(period="morning", disable_remote_inference = True); print(result.select("answer.q0").first())
        >>> asyncio.run(test_run_async())
        yes
        >>> import asyncio
        >>> from edsl.questions import QuestionFunctional
        >>> def f(scenario, agent_traits): return "yes" if scenario["period"] == "morning" else "no"
        >>> q = QuestionFunctional(question_name = "q0", func = f)
        >>> s = Survey([q])
        >>> async def test_run_async(): result = await s.run_async(period="evening", disable_remote_inference = True); print(result.select("answer.q0").first())
        >>> asyncio.run(test_run_async())
        no
        """
        # TODO: temp fix by creating a cache
        if cache is None:
            from edsl.data import Cache

            c = Cache()
        else:
            c = cache
        jobs: "Jobs" = self.get_job(model=model, agent=agent, **kwargs)
        return await jobs.run_async(
            cache=c, disable_remote_inference=disable_remote_inference
        )

    def run(self, *args, **kwargs) -> "Results":
        """Turn the survey into a Job and runs it.

        >>> from edsl import QuestionFreeText
        >>> s = Survey([QuestionFreeText.example()])
        >>> from edsl.language_models import LanguageModel
        >>> m = LanguageModel.example(test_model = True, canned_response = "Great!")
        >>> results = s.by(m).run(cache = False, disable_remote_cache = True, disable_remote_inference = True)
        >>> results.select('answer.*')
        Dataset([{'answer.how_are_you': ['Great!']}])
        """
        from edsl.jobs.Jobs import Jobs

        return Jobs(survey=self).run(*args, **kwargs)

    # region: Survey flow
    def next_question(
        self, current_question: Union[str, QuestionBase], answers: dict
    ) -> Union[QuestionBase, EndOfSurvey.__class__]:
        """
        Return the next question in a survey.

        :param current_question: The current question in the survey.
        :param answers: The answers for the survey so far

        - If called with no arguments, it returns the first question in the survey.
        - If no answers are provided for a question with a rule, the next question is returned. If answers are provided, the next question is determined by the rules and the answers.
        - If the next question is the last question in the survey, an EndOfSurvey object is returned.

        >>> s = Survey.example()
        >>> s.next_question("q0", {"q0": "yes"}).question_name
        'q2'
        >>> s.next_question("q0", {"q0": "no"}).question_name
        'q1'

        """
        if isinstance(current_question, str):
            current_question = self.get_question(current_question)

        question_index = self.question_name_to_index[current_question.question_name]
        next_question_object = self.rule_collection.next_question(
            question_index, answers
        )

        if next_question_object.num_rules_found == 0:
            raise SurveyHasNoRulesError

        if next_question_object.next_q == EndOfSurvey:
            return EndOfSurvey
        else:
            if next_question_object.next_q >= len(self.questions):
                return EndOfSurvey
            else:
                return self.questions[next_question_object.next_q]

    def gen_path_through_survey(self) -> Generator[QuestionBase, dict, None]:
        """
        Generate a coroutine that can be used to conduct an Interview.

        The coroutine is a generator that yields a question and receives answers.
        It starts with the first question in the survey.
        The coroutine ends when an EndOfSurvey object is returned.

        For the example survey, this is the rule table:

        >>> s = Survey.example()
        >>> s.show_rules()
        ┏━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
        ┃ current_q ┃ expression  ┃ next_q ┃ priority ┃ before_rule ┃
        ┡━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
        │ 0         │ True        │ 1      │ -1       │ False       │
        │ 0         │ q0 == 'yes' │ 2      │ 0        │ False       │
        │ 1         │ True        │ 2      │ -1       │ False       │
        │ 2         │ True        │ 3      │ -1       │ False       │
        └───────────┴─────────────┴────────┴──────────┴─────────────┘

        Note that q0 has a rule that if the answer is 'yes', the next question is q2. If the answer is 'no', the next question is q1.

        Here is the path through the survey if the answer to q0 is 'yes':

        >>> i = s.gen_path_through_survey()
        >>> next(i)
        Question('multiple_choice', question_name = \"""q0\""", question_text = \"""Do you like school?\""", question_options = ['yes', 'no'])
        >>> i.send({"q0": "yes"})
        Question('multiple_choice', question_name = \"""q2\""", question_text = \"""Why?\""", question_options = ['**lack*** of killer bees in cafeteria', 'other'])

        And here is the path through the survey if the answer to q0 is 'no':

        >>> i2 = s.gen_path_through_survey()
        >>> next(i2)
        Question('multiple_choice', question_name = \"""q0\""", question_text = \"""Do you like school?\""", question_options = ['yes', 'no'])
        >>> i2.send({"q0": "no"})
        Question('multiple_choice', question_name = \"""q1\""", question_text = \"""Why not?\""", question_options = ['killer bees in cafeteria', 'other'])


        """
        self.answers = {}
        question = self._questions[0]
        # should the first question be skipped?
        if self.rule_collection.skip_question_before_running(0, self.answers):
            question = self.next_question(question, self.answers)

        while not question == EndOfSurvey:
            # breakpoint()
            answer = yield question
            self.answers.update(answer)
            # print(f"Answers: {self.answers}")
            ## TODO: This should also include survey and agent attributes
            question = self.next_question(question, self.answers)

    # endregion

    # regions: DAG construction
    def textify(self, index_dag: DAG) -> DAG:
        """Convert the DAG of question indices to a DAG of question names.

        :param index_dag: The DAG of question indices.

        Example:

        >>> s = Survey.example()
        >>> d = s.dag()
        >>> d
        {1: {0}, 2: {0}}
        >>> s.textify(d)
        {'q1': {'q0'}, 'q2': {'q0'}}
        """

        def get_name(index: int):
            """Return the name of the question given the index."""
            if index >= len(self.questions):
                return EndOfSurvey
            try:
                return self.questions[index].question_name
            except IndexError:
                print(
                    f"The index is {index} but the length of the questions is {len(self.questions)}"
                )
                raise SurveyError

        try:
            text_dag = {}
            for child_index, parent_indices in index_dag.items():
                parent_names = {get_name(index) for index in parent_indices}
                child_name = get_name(child_index)
                text_dag[child_name] = parent_names
            return text_dag
        except IndexError:
            raise

    @property
    def piping_dag(self) -> DAG:
        """Figures out the DAG of piping dependencies.

        >>> from edsl import QuestionFreeText
        >>> q0 = QuestionFreeText(question_text="Here is a question", question_name="q0")
        >>> q1 = QuestionFreeText(question_text="You previously answered {{ q0 }}---how do you feel now?", question_name="q1")
        >>> s = Survey([q0, q1])
        >>> s.piping_dag
        {1: {0}}
        """
        d = {}
        for question_name, depenencies in self.parameters_by_question.items():
            if depenencies:
                question_index = self.question_name_to_index[question_name]
                for dependency in depenencies:
                    if dependency not in self.question_name_to_index:
                        pass
                    else:
                        dependency_index = self.question_name_to_index[dependency]
                        if question_index not in d:
                            d[question_index] = set()
                        d[question_index].add(dependency_index)
        return d

    def dag(self, textify: bool = False) -> DAG:
        """Return the DAG of the survey, which reflects both skip-logic and memory.

        :param textify: Whether to return the DAG with question names instead of indices.

        >>> s = Survey.example()
        >>> d = s.dag()
        >>> d
        {1: {0}, 2: {0}}

        """
        memory_dag = self.memory_plan.dag
        rule_dag = self.rule_collection.dag
        piping_dag = self.piping_dag
        if textify:
            memory_dag = DAG(self.textify(memory_dag))
            rule_dag = DAG(self.textify(rule_dag))
            piping_dag = DAG(self.textify(piping_dag))
        return memory_dag + rule_dag + piping_dag

    ###################
    # DUNDER METHODS
    ###################
    def __len__(self) -> int:
        """Return the number of questions in the survey.

        >>> s = Survey.example()
        >>> len(s)
        3
        """
        return len(self._questions)

    def __getitem__(self, index) -> QuestionBase:
        """Return the question object given the question index.

        :param index: The index of the question to get.

        >>> s = Survey.example()
        >>> s[0]
        Question('multiple_choice', question_name = \"""q0\""", question_text = \"""Do you like school?\""", question_options = ['yes', 'no'])

        """
        if isinstance(index, int):
            return self._questions[index]
        elif isinstance(index, str):
            return getattr(self, index)

    def _diff(self, other):
        """Used for debugging. Print out the differences between two surveys."""
        from rich import print

        for key, value in self.to_dict().items():
            if value != other.to_dict()[key]:
                print(f"Key: {key}")
                print("\n")
                print(f"Self: {value}")
                print("\n")
                print(f"Other: {other.to_dict()[key]}")
                print("\n\n")

    def __eq__(self, other) -> bool:
        """Return True if the two surveys have the same to_dict.

        :param other: The other survey to compare to.

        >>> s = Survey.example()
        >>> s == s
        True

        >>> s == "poop"
        False

        """
        if not isinstance(other, Survey):
            return False
        return self.to_dict() == other.to_dict()

    @classmethod
    def from_qsf(
        cls, qsf_file: Optional[str] = None, url: Optional[str] = None
    ) -> Survey:
        """Create a Survey object from a Qualtrics QSF file."""

        if url and qsf_file:
            raise ValueError("Only one of url or qsf_file can be provided.")

        if (not url) and (not qsf_file):
            raise ValueError("Either url or qsf_file must be provided.")

        if url:
            response = requests.get(url)
            response.raise_for_status()  # Ensure the request was successful

            # Save the Excel file to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".qsf", delete=False) as temp_file:
                temp_file.write(response.content)
                qsf_file = temp_file.name

        from edsl.surveys.SurveyQualtricsImport import SurveyQualtricsImport

        so = SurveyQualtricsImport(qsf_file)
        return so.create_survey()

    # region: Display methods
    def print(self):
        """Print the survey in a rich format.

        >>> s = Survey.example()
        >>> s.print()
        {
          "questions": [
          ...
        }
        """
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __repr__(self) -> str:
        """Return a string representation of the survey."""

        # questions_string = ", ".join([repr(q) for q in self._questions])
        questions_string = ", ".join([repr(q) for q in self.raw_passed_questions or []])
        # question_names_string = ", ".join([repr(name) for name in self.question_names])
        return f"Survey(questions=[{questions_string}], memory_plan={self.memory_plan}, rule_collection={self.rule_collection}, question_groups={self.question_groups})"

    def _repr_html_(self) -> str:
        from edsl.utilities.utilities import data_to_html

        return data_to_html(self.to_dict())

    def rich_print(self) -> Table:
        """Print the survey in a rich format.

        >>> t = Survey.example().rich_print()
        >>> print(t) # doctest: +SKIP
        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
        ┃ Questions                                                                                          ┃
        ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
        │ ┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓                                │
        │ ┃ Question Name ┃ Question Type   ┃ Question Text       ┃ Options ┃                                │
        │ ┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩                                │
        │ │ q0            │ multiple_choice │ Do you like school? │ yes, no │                                │
        │ └───────────────┴─────────────────┴─────────────────────┴─────────┘                                │
        │ ┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓              │
        │ ┃ Question Name ┃ Question Type   ┃ Question Text ┃ Options                         ┃              │
        │ ┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩              │
        │ │ q1            │ multiple_choice │ Why not?      │ killer bees in cafeteria, other │              │
        │ └───────────────┴─────────────────┴───────────────┴─────────────────────────────────┘              │
        │ ┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │
        │ ┃ Question Name ┃ Question Type   ┃ Question Text ┃ Options                                      ┃ │
        │ ┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩ │
        │ │ q2            │ multiple_choice │ Why?          │ **lack*** of killer bees in cafeteria, other │ │
        │ └───────────────┴─────────────────┴───────────────┴──────────────────────────────────────────────┘ │
        └────────────────────────────────────────────────────────────────────────────────────────────────────┘
        """
        from rich.table import Table

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Questions", style="dim")

        for question in self._questions:
            table.add_row(question.rich_print())

        return table

    # endregion

    def codebook(self) -> dict[str, str]:
        """Create a codebook for the survey, mapping question names to question text.

        >>> s = Survey.example()
        >>> s.codebook()
        {'q0': 'Do you like school?', 'q1': 'Why not?', 'q2': 'Why?'}
        """
        codebook = {}
        for question in self._questions:
            codebook[question.question_name] = question.question_text
        return codebook

    # region: Export methods
    def to_csv(self, filename: str = None):
        """Export the survey to a CSV file.

        :param filename: The name of the file to save the CSV to.

        >>> s = Survey.example()
        >>> s.to_csv() # doctest: +SKIP
           index question_name        question_text                                question_options    question_type
        0      0            q0  Do you like school?                                       [yes, no]  multiple_choice
        1      1            q1             Why not?               [killer bees in cafeteria, other]  multiple_choice
        2      2            q2                 Why?  [**lack*** of killer bees in cafeteria, other]  multiple_choice
        """
        raw_data = []
        for index, question in enumerate(self._questions):
            d = {"index": index}
            question_dict = question.to_dict()
            _ = question_dict.pop("edsl_version")
            _ = question_dict.pop("edsl_class_name")
            d.update(question_dict)
            raw_data.append(d)
        from pandas import DataFrame

        df = DataFrame(raw_data)
        if filename:
            df.to_csv(filename, index=False)
        else:
            return df

    # endregion

    @classmethod
    def example(
        cls,
        params: bool = False,
        randomize: bool = False,
        include_instructions=False,
        custom_instructions: Optional[str] = None,
    ) -> Survey:
        """Return an example survey.

        >>> s = Survey.example()
        >>> [q.question_text for q in s.questions]
        ['Do you like school?', 'Why not?', 'Why?']
        """
        from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice

        addition = "" if not randomize else str(uuid4())
        q0 = QuestionMultipleChoice(
            question_text=f"Do you like school?{addition}",
            question_options=["yes", "no"],
            question_name="q0",
        )
        q1 = QuestionMultipleChoice(
            question_text="Why not?",
            question_options=["killer bees in cafeteria", "other"],
            question_name="q1",
        )
        q2 = QuestionMultipleChoice(
            question_text="Why?",
            question_options=["**lack*** of killer bees in cafeteria", "other"],
            question_name="q2",
        )
        if params:
            q3 = QuestionMultipleChoice(
                question_text="To the question '{{ q0.question_text}}', you said '{{ q0.answer }}'. Do you still feel this way?",
                question_options=["yes", "no"],
                question_name="q3",
            )
            s = cls(questions=[q0, q1, q2, q3])
            return s

        if include_instructions:
            from edsl import Instruction

            custom_instructions = (
                custom_instructions if custom_instructions else "Please pay attention!"
            )

            i = Instruction(text=custom_instructions, name="attention")
            s = cls(questions=[i, q0, q1, q2])
            return s

        s = cls(questions=[q0, q1, q2])
        s = s.add_rule(q0, "q0 == 'yes'", q2)
        return s

    def get_job(self, model=None, agent=None, **kwargs):
        if model is None:
            from edsl import Model

            model = Model()

        from edsl.scenarios.Scenario import Scenario

        s = Scenario(kwargs)

        if not agent:
            from edsl import Agent

            agent = Agent()

        return self.by(s).by(agent).by(model)


def main():
    """Run the example survey."""

    def example_survey():
        """Return an example survey."""
        from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice
        from edsl.surveys.Survey import Survey

        q0 = QuestionMultipleChoice(
            question_text="Do you like school?",
            question_options=["yes", "no"],
            question_name="q0",
        )
        q1 = QuestionMultipleChoice(
            question_text="Why not?",
            question_options=["killer bees in cafeteria", "other"],
            question_name="q1",
        )
        q2 = QuestionMultipleChoice(
            question_text="Why?",
            question_options=["**lack*** of killer bees in cafeteria", "other"],
            question_name="q2",
        )
        s = Survey(questions=[q0, q1, q2])
        s = s.add_rule(q0, "q0 == 'yes'", q2)
        return s

    s = example_survey()
    survey_dict = s.to_dict()
    s2 = Survey.from_dict(survey_dict)
    results = s2.run()
    print(results)


if __name__ == "__main__":
    import doctest

    # doctest.testmod(optionflags=doctest.ELLIPSIS | doctest.SKIP)
    doctest.testmod(optionflags=doctest.ELLIPSIS)
