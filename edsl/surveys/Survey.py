"""A Survey is collection of questions that can be administered to an Agent."""

from __future__ import annotations
import re
import random

from typing import (
    Any,
    Generator,
    Optional,
    Union,
    List,
    Literal,
    Callable,
    TYPE_CHECKING,
)
from uuid import uuid4
from edsl.Base import Base
from edsl.exceptions.surveys import SurveyCreationError, SurveyHasNoRulesError
from edsl.exceptions.surveys import SurveyError
from collections import UserDict


class PseudoIndices(UserDict):
    @property
    def max_pseudo_index(self) -> float:
        """Return the maximum pseudo index in the survey.
        >>> Survey.example()._pseudo_indices.max_pseudo_index
        2
        """
        if len(self) == 0:
            return -1
        return max(self.values())

    @property
    def last_item_was_instruction(self) -> bool:
        """Return whether the last item added to the survey was an instruction.

        This is used to determine the pseudo-index of the next item added to the survey.

        Example:

        >>> s = Survey.example()
        >>> s._pseudo_indices.last_item_was_instruction
        False
        >>> from edsl.surveys.instructions.Instruction import Instruction
        >>> s = s.add_instruction(Instruction(text="Pay attention to the following questions.", name="intro"))
        >>> s._pseudo_indices.last_item_was_instruction
        True
        """
        return isinstance(self.max_pseudo_index, float)


if TYPE_CHECKING:
    from edsl.questions.QuestionBase import QuestionBase
    from edsl.agents.Agent import Agent
    from edsl.surveys.DAG import DAG
    from edsl.language_models.LanguageModel import LanguageModel
    from edsl.scenarios.Scenario import Scenario
    from edsl.data.Cache import Cache

    # This is a hack to get around the fact that TypeAlias is not available in typing until Python 3.10
    try:
        from typing import TypeAlias
    except ImportError:
        from typing import _GenericAlias as TypeAlias

    QuestionType: TypeAlias = Union[QuestionBase, Instruction, ChangeInstruction]
    QuestionGroupType: TypeAlias = dict[str, tuple[int, int]]


from edsl.utilities.remove_edsl_version import remove_edsl_version

from edsl.surveys.instructions.InstructionCollection import InstructionCollection
from edsl.surveys.instructions.Instruction import Instruction
from edsl.surveys.instructions.ChangeInstruction import ChangeInstruction

from edsl.surveys.base import EndOfSurvey
from edsl.surveys.descriptors import QuestionsDescriptor
from edsl.surveys.MemoryPlan import MemoryPlan
from edsl.surveys.RuleCollection import RuleCollection
from edsl.surveys.SurveyExportMixin import SurveyExportMixin
from edsl.surveys.SurveyFlowVisualization import SurveyFlowVisualization
from edsl.surveys.InstructionHandler import InstructionHandler
from edsl.surveys.EditSurvey import EditSurvey
from edsl.surveys.Simulator import Simulator
from edsl.surveys.MemoryManagement import MemoryManagement
from edsl.surveys.RuleManager import RuleManager


class Survey(SurveyExportMixin, Base):
    """A collection of questions that supports skip logic."""

    __documentation__ = """https://docs.expectedparrot.com/en/latest/surveys.html"""

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
        questions: Optional[List["QuestionType"]] = None,
        memory_plan: Optional["MemoryPlan"] = None,
        rule_collection: Optional["RuleCollection"] = None,
        question_groups: Optional["QuestionGroupType"] = None,
        name: Optional[str] = None,
        questions_to_randomize: Optional[List[str]] = None,
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

        true_questions = self._process_raw_questions(self.raw_passed_questions)

        self.rule_collection = RuleCollection(
            num_questions=len(true_questions) if true_questions else None
        )
        # the RuleCollection needs to be present while we add the questions; we might override this later
        # if a rule_collection is provided. This allows us to serialize the survey with the rule_collection.

        # this is where the Questions constructor is called.
        self.questions = true_questions
        # self.instruction_names_to_instructions = instruction_names_to_instructions

        self.memory_plan = memory_plan or MemoryPlan(self)
        if question_groups is not None:
            self.question_groups = question_groups
        else:
            self.question_groups = {}

        # if a rule collection is provided, use it instead of the constructed one
        if rule_collection is not None:
            self.rule_collection = rule_collection

        if name is not None:
            import warnings

            warnings.warn("name parameter to a survey is deprecated.")

        if questions_to_randomize is not None:
            self.questions_to_randomize = questions_to_randomize
        else:
            self.questions_to_randomize = []

        self._seed = None

    def draw(self) -> "Survey":
        """Return a new survey with a randomly selected permutation of the options."""
        if self._seed is None:  # only set once
            self._seed = hash(self)
            random.seed(self._seed)

        if len(self.questions_to_randomize) == 0:
            return self

        new_questions = []
        for question in self.questions:
            if question.question_name in self.questions_to_randomize:
                new_questions.append(question.draw())
            else:
                new_questions.append(question.duplicate())

        d = self.to_dict()
        d["questions"] = [q.to_dict() for q in new_questions]
        return Survey.from_dict(d)

    def _process_raw_questions(self, questions: Optional[List["QuestionType"]]) -> list:
        """Process the raw questions passed to the survey."""
        handler = InstructionHandler(self)
        components = handler.separate_questions_and_instructions(questions or [])
        self._instruction_names_to_instructions = (
            components.instruction_names_to_instructions
        )
        self._pseudo_indices = PseudoIndices(components.pseudo_indices)
        return components.true_questions

    # region: Survey instruction handling
    @property
    def _relevant_instructions_dict(self) -> InstructionCollection:
        """Return a dictionary with keys as question names and values as instructions that are relevant to the question.

        >>> s = Survey.example(include_instructions=True)
        >>> s._relevant_instructions_dict
        {'q0': [Instruction(name="attention", text="Please pay attention!")], 'q1': [Instruction(name="attention", text="Please pay attention!")], 'q2': [Instruction(name="attention", text="Please pay attention!")]}

        """
        return InstructionCollection(
            self._instruction_names_to_instructions, self.questions
        )

    def _relevant_instructions(self, question: QuestionBase) -> dict:
        """This should be a dictionry with keys as question names and values as instructions that are relevant to the question.

        :param question: The question to get the relevant instructions for.

        # Did the instruction come before the question and was it not modified by a change instruction?

        """
        return InstructionCollection(
            self._instruction_names_to_instructions, self.questions
        )[question]

    def show_flow(self, filename: Optional[str] = None) -> None:
        """Show the flow of the survey."""
        SurveyFlowVisualization(self).show_flow(filename=filename)

    def add_instruction(
        self, instruction: Union["Instruction", "ChangeInstruction"]
    ) -> Survey:
        """
        Add an instruction to the survey.

        :param instruction: The instruction to add to the survey.

        >>> from edsl import Instruction
        >>> i = Instruction(text="Pay attention to the following questions.", name="intro")
        >>> s = Survey().add_instruction(i)
        >>> s._instruction_names_to_instructions
        {'intro': Instruction(name="intro", text="Pay attention to the following questions.")}
        >>> s._pseudo_indices
        {'intro': -0.5}
        """
        return EditSurvey(self).add_instruction(instruction)

    # endregion
    @classmethod
    def random_survey(cls):
        return Simulator.random_survey()

    def simulate(self) -> dict:
        """Simulate the survey and return the answers."""
        return Simulator(self).simulate()

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

    def _get_question_by_name(self, question_name: str) -> QuestionBase:
        """
        Return the question object given the question name.

        :param question_name: The name of the question to get.

        >>> s = Survey.example()
        >>> s._get_question_by_name("q0")
        Question('multiple_choice', question_name = \"""q0\""", question_text = \"""Do you like school?\""", question_options = ['yes', 'no'])
        """
        if question_name not in self.question_name_to_index:
            raise SurveyError(f"Question name {question_name} not found in survey.")
        return self._questions[self.question_name_to_index[question_name]]

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
    def to_dict(self, add_edsl_version=True) -> dict[str, Any]:
        """Serialize the Survey object to a dictionary.

        >>> s = Survey.example()
        >>> s.to_dict(add_edsl_version = False).keys()
        dict_keys(['questions', 'memory_plan', 'rule_collection', 'question_groups'])
        """
        from edsl import __version__

        d = {
            "questions": [
                q.to_dict(add_edsl_version=add_edsl_version)
                for q in self._recombined_questions_and_instructions()
            ],
            "memory_plan": self.memory_plan.to_dict(add_edsl_version=add_edsl_version),
            "rule_collection": self.rule_collection.to_dict(
                add_edsl_version=add_edsl_version
            ),
            "question_groups": self.question_groups,
        }
        if self.questions_to_randomize != []:
            d["questions_to_randomize"] = self.questions_to_randomize

        if add_edsl_version:
            d["edsl_version"] = __version__
            d["edsl_class_name"] = "Survey"
        return d

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
            from edsl.questions.QuestionBase import QuestionBase

            if (class_name := pass_dict.get("edsl_class_name")) == "QuestionBase":
                return QuestionBase
            elif pass_dict.get("edsl_class_name") == "QuestionDict":
                from edsl.questions.QuestionDict import QuestionDict

                return QuestionDict
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
        if "questions_to_randomize" in data:
            questions_to_randomize = data["questions_to_randomize"]
        else:
            questions_to_randomize = None
        survey = cls(
            questions=questions,
            memory_plan=memory_plan,
            rule_collection=RuleCollection.from_dict(data["rule_collection"]),
            question_groups=data["question_groups"],
            questions_to_randomize=questions_to_randomize,
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

    def move_question(self, identifier: Union[str, int], new_index: int) -> Survey:
        """
        >>> from edsl import QuestionMultipleChoice, Survey
        >>> s = Survey.example()
        >>> s.question_names
        ['q0', 'q1', 'q2']
        >>> s.move_question("q0", 2).question_names
        ['q1', 'q2', 'q0']
        """
        return EditSurvey(self).move_question(identifier, new_index)

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
        return EditSurvey(self).delete_question(identifier)

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
        return EditSurvey(self).add_question(question, index)

    def _recombined_questions_and_instructions(
        self,
    ) -> list[Union[QuestionBase, "Instruction"]]:
        """Return a list of questions and instructions sorted by pseudo index."""
        questions_and_instructions = self._questions + list(
            self._instruction_names_to_instructions.values()
        )
        return sorted(
            questions_and_instructions, key=lambda x: self._pseudo_indices[x.name]
        )

    # endregion

    # region: Memory plan methods
    def set_full_memory_mode(self) -> Survey:
        """Add instructions to a survey that the agent should remember all of the answers to the questions in the survey.

        >>> s = Survey.example().set_full_memory_mode()

        """
        MemoryManagement(self)._set_memory_plan(lambda i: self.question_names[:i])
        return self

    def set_lagged_memory(self, lags: int) -> Survey:
        """Add instructions to a survey that the agent should remember the answers to the questions in the survey.

        The agent should remember the answers to the questions in the survey from the previous lags.
        """
        MemoryManagement(self)._set_memory_plan(
            lambda i: self.question_names[max(0, i - lags) : i]
        )
        return self

    def _set_memory_plan(self, prior_questions_func: Callable) -> None:
        """Set memory plan based on a provided function determining prior questions.

        :param prior_questions_func: A function that takes the index of the current question and returns a list of prior questions to remember.

        >>> s = Survey.example()
        >>> s._set_memory_plan(lambda i: s.question_names[:i])

        """
        MemoryManagement(self)._set_memory_plan(prior_questions_func)

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
        return MemoryManagement(self).add_targeted_memory(
            focal_question, prior_question
        )

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
        return MemoryManagement(self).add_memory_collection(
            focal_question, prior_questions
        )

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
        Dataset([{'current_q': [0, 0, 1, 2]}, {'expression': ['True', "q0 == 'yes'", 'True', 'True']}, {'next_q': [1, 2, 2, 3]}, {'priority': [-1, 0, -1, -1]}, {'before_rule': [False, False, False, False]}])
        """
        return self.rule_collection.show_rules()

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
        return RuleManager(self).add_stop_rule(question, expression)

    def clear_non_default_rules(self) -> Survey:
        """Remove all non-default rules from the survey.

        >>> Survey.example().show_rules()
        Dataset([{'current_q': [0, 0, 1, 2]}, {'expression': ['True', "q0 == 'yes'", 'True', 'True']}, {'next_q': [1, 2, 2, 3]}, {'priority': [-1, 0, -1, -1]}, {'before_rule': [False, False, False, False]}])
        >>> Survey.example().clear_non_default_rules().show_rules()
        Dataset([{'current_q': [0, 1, 2]}, {'expression': ['True', 'True', 'True']}, {'next_q': [1, 2, 3]}, {'priority': [-1, -1, -1]}, {'before_rule': [False, False, False]}])
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
        return RuleManager(self).add_rule(
            question, expression, question_index + 1, before_rule=True
        )

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
        return RuleManager(self).add_rule(
            question, expression, next_question, before_rule=before_rule
        )

    # endregion

    # region: Forward methods
    def by(self, *args: Union["Agent", "Scenario", "LanguageModel"]) -> "Jobs":
        """Add Agents, Scenarios, and LanguageModels to a survey and returns a runnable Jobs object.

        :param args: The Agents, Scenarios, and LanguageModels to add to the survey.

        This takes the survey and adds an Agent and a Scenario via 'by' which converts to a Jobs object:

        >>> s = Survey.example(); from edsl.agents import Agent; from edsl import Scenario
        >>> s.by(Agent.example()).by(Scenario.example())
        Jobs(...)
        """
        from edsl.jobs.Jobs import Jobs

        return Jobs(survey=self).by(*args)

    def to_jobs(self):
        """Convert the survey to a Jobs object.
        >>> s = Survey.example()
        >>> s.to_jobs()
        Jobs(...)
        """
        from edsl.jobs.Jobs import Jobs

        return Jobs(survey=self)

    def show_prompts(self):
        """Show the prompts for the survey."""
        return self.to_jobs().show_prompts()

    # endregion

    # region: Running the survey

    def __call__(
        self,
        model=None,
        agent=None,
        cache=None,
        verbose=False,
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

        return self.get_job(model, agent, **kwargs).run(
            cache=cache,
            verbose=verbose,
            disable_remote_cache=disable_remote_cache,
            disable_remote_inference=disable_remote_inference,
        )

    async def run_async(
        self,
        model: Optional["LanguageModel"] = None,
        agent: Optional["Agent"] = None,
        cache: Optional["Cache"] = None,
        disable_remote_inference: bool = False,
        disable_remote_cache: bool = False,
        **kwargs,
    ):
        """Run the survey with default model, taking the required survey as arguments.

        >>> import asyncio
        >>> from edsl.questions import QuestionFunctional
        >>> def f(scenario, agent_traits): return "yes" if scenario["period"] == "morning" else "no"
        >>> q = QuestionFunctional(question_name = "q0", func = f)
        >>> s = Survey([q])
        >>> async def test_run_async(): result = await s.run_async(period="morning", disable_remote_inference = True, disable_remote_cache=True); print(result.select("answer.q0").first())
        >>> asyncio.run(test_run_async())
        yes
        >>> import asyncio
        >>> from edsl.questions import QuestionFunctional
        >>> def f(scenario, agent_traits): return "yes" if scenario["period"] == "morning" else "no"
        >>> q = QuestionFunctional(question_name = "q0", func = f)
        >>> s = Survey([q])
        >>> async def test_run_async(): result = await s.run_async(period="evening", disable_remote_inference = True, disable_remote_cache = True); print(result.select("answer.q0").first())
        >>> results = asyncio.run(test_run_async())
        no
        """
        # TODO: temp fix by creating a cache
        if cache is None:
            from edsl.data import Cache
            c = Cache()
        else:
            c = cache

        

        jobs: "Jobs" = self.get_job(model=model, agent=agent, **kwargs).using(c)
        return await jobs.run_async(
            disable_remote_inference=disable_remote_inference,
            disable_remote_cache=disable_remote_cache,
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

    def using(self, obj: Union["Cache", "KeyLookup", "BucketCollection"]) -> "Jobs":
        """Turn the survey into a Job and appends the arguments to the Job."""
        from edsl.jobs.Jobs import Jobs

        return Jobs(survey=self).using(obj)

    def duplicate(self):
        """Duplicate the survey.

        >>> s = Survey.example()
        >>> s2 = s.duplicate()
        >>> s == s2
        True
        >>> s is s2
        False

        """
        return Survey.from_dict(self.to_dict())

    # region: Survey flow
    def next_question(
        self,
        current_question: Optional[Union[str, QuestionBase]] = None,
        answers: Optional[dict] = None,
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
        if current_question is None:
            return self.questions[0]

        if isinstance(current_question, str):
            current_question = self._get_question_by_name(current_question)

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
        Dataset([{'current_q': [0, 0, 1, 2]}, {'expression': ['True', "q0 == 'yes'", 'True', 'True']}, {'next_q': [1, 2, 2, 3]}, {'priority': [-1, 0, -1, -1]}, {'before_rule': [False, False, False, False]}])

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
            answer = yield question
            self.answers.update(answer)
            # print(f"Answers: {self.answers}")
            ## TODO: This should also include survey and agent attributes
            question = self.next_question(question, self.answers)

    # endregion

    def dag(self, textify: bool = False) -> DAG:
        """Return the DAG of the survey, which reflects both skip-logic and memory.

        :param textify: Whether to return the DAG with question names instead of indices.

        >>> s = Survey.example()
        >>> d = s.dag()
        >>> d
        {1: {0}, 2: {0}}

        """
        from edsl.surveys.ConstructDAG import ConstructDAG

        return ConstructDAG(self).dag(textify)

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

    # def _diff(self, other):
    #     """Used for debugging. Print out the differences between two surveys."""
    #     from rich import print

    #     for key, value in self.to_dict().items():
    #         if value != other.to_dict()[key]:
    #             print(f"Key: {key}")
    #             print("\n")
    #             print(f"Self: {value}")
    #             print("\n")
    #             print(f"Other: {other.to_dict()[key]}")
    #             print("\n\n")

    def __repr__(self) -> str:
        """Return a string representation of the survey."""

        # questions_string = ", ".join([repr(q) for q in self._questions])
        questions_string = ", ".join([repr(q) for q in self.raw_passed_questions or []])
        # question_names_string = ", ".join([repr(name) for name in self.question_names])
        return f"Survey(questions=[{questions_string}], memory_plan={self.memory_plan}, rule_collection={self.rule_collection}, question_groups={self.question_groups}, questions_to_randomize={self.questions_to_randomize})"

    def _summary(self) -> dict:
        return {
            "# questions": len(self),
            "question_name list": self.question_names,
        }

    def tree(self, node_list: Optional[List[str]] = None):
        return self.to_scenario_list().tree(node_list=node_list)

    def table(self, *fields, tablefmt=None) -> Table:
        return self.to_scenario_list().to_dataset().table(*fields, tablefmt=tablefmt)

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
            from edsl.language_models.model import Model

            model = Model()

        from edsl.scenarios.Scenario import Scenario

        s = Scenario(kwargs)

        if not agent:
            from edsl.agents.Agent import Agent

            agent = Agent()

        return self.by(s).by(agent).by(model)


def main():
    """Run the example survey."""

    def example_survey():
        """Return an example survey."""
        from edsl import QuestionMultipleChoice, QuestionList, QuestionNumerical, Survey

        q0 = QuestionMultipleChoice(
            question_name="q0",
            question_text="What is the capital of France?",
            question_options=["London", "Paris", "Rome", "Boston", "I don't know"]
        )
        q1 = QuestionList(
            question_name="q1",
            question_text="Name some cities in France.",
            max_list_items = 5
        )
        q2 = QuestionNumerical(
            question_name="q2",
            question_text="What is the population of {{ q0.answer }}?"
        )
        s = Survey(questions=[q0, q1, q2])
        s = s.add_rule(q0, "q0 == 'Paris'", q2)
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
