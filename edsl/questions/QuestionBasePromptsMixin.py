from importlib import resources
from typing import Optional
from edsl.prompts import Prompt
from edsl.exceptions.questions import QuestionAnswerValidationError


class QuestionBasePromptsMixin:

    @classmethod
    def applicable_prompts(
        cls, model: Optional[str] = None
    ) -> list[type["PromptBase"]]:
        """Get the prompts that are applicable to the question type.

        :param model: The language model to use.

        >>> from edsl.questions import QuestionFreeText
        >>> QuestionFreeText.applicable_prompts()
        [<class 'edsl.prompts.library.question_freetext.FreeText'>]

        :param model: The language model to use. If None, assumes does not matter.

        """
        from edsl.prompts.registry import get_classes as prompt_lookup

        applicable_prompts = prompt_lookup(
            component_type="question_instructions",
            question_type=cls.question_type,
            model=model,
        )
        return applicable_prompts

    @property
    def model_instructions(self) -> dict:
        """Get the model-specific instructions for the question."""
        if not hasattr(self, "_model_instructions"):
            self._model_instructions = {}
        return self._model_instructions

    def _all_text(self) -> str:
        """Return the question text.

        >>> from edsl import QuestionMultipleChoice as Q
        >>> Q.example()._all_text()
        "how_feelingHow are you?['Good', 'Great', 'OK', 'Bad']"
        """
        txt = ""
        for key, value in self.data.items():
            if isinstance(value, str):
                txt += value
            elif isinstance(value, list):
                txt += "".join(str(value))
        return txt

    @model_instructions.setter
    def model_instructions(self, data: dict):
        """Set the model-specific instructions for the question."""
        self._model_instructions = data

    def add_model_instructions(
        self, *, instructions: str, model: Optional[str] = None
    ) -> None:
        """Add model-specific instructions for the question that override the default instructions.

        :param instructions: The instructions to add. This is typically a jinja2 template.
        :param model: The language model for this instruction.

        >>> from edsl.questions import QuestionFreeText
        >>> q = QuestionFreeText(question_name = "color", question_text = "What is your favorite color?")
        >>> q.add_model_instructions(instructions = "{{question_text}}. Answer in valid JSON like so {'answer': 'comment: <>}", model = "gpt3")
        >>> q.get_instructions(model = "gpt3")
        Prompt(text=\"""{{question_text}}. Answer in valid JSON like so {'answer': 'comment: <>}\""")
        """
        from edsl import Model

        if not hasattr(self, "_model_instructions"):
            self._model_instructions = {}
        if model is None:
            # if not model is passed, all the models are mapped to this instruction, including 'None'
            self._model_instructions = {
                model_name: instructions
                for model_name in Model.available(name_only=True)
            }
            self._model_instructions.update({model: instructions})
        else:

            self._model_instructions.update({model: instructions})

    @classmethod
    def path_to_folder(cls) -> str:
        return resources.files(f"edsl.questions.templates", cls.question_type)

    @property
    def response_model(self) -> type["BaseModel"]:
        if self._response_model is not None:
            return self._response_model
        else:
            return self.create_response_model()

    @property
    def use_code(self) -> bool:
        if hasattr(self, "_use_code"):
            return self._use_code
        return True

    @use_code.setter
    def use_code(self, value: bool) -> None:
        self._use_code = value

    @property
    def include_comment(self) -> bool:
        if hasattr(self, "_include_comment"):
            return self._include_comment
        return True

    @include_comment.setter
    def include_comment(self, value: bool) -> None:
        self._include_comment = value

    @property
    def answering_instructions(self) -> str:
        if self._answering_instructions is None:
            return self.default_answering_instructions()
        return self._answering_instructions

    @answering_instructions.setter
    def answering_instructions(self, value) -> None:
        self._answering_instructions = value

    @classmethod
    def default_answering_instructions(cls) -> str:
        with resources.open_text(
            f"edsl.questions.templates.{cls.question_type}",
            "answering_instructions.jinja",
        ) as file:
            return Prompt(text=file.read())

    @classmethod
    def default_question_presentation(cls):
        with resources.open_text(
            f"edsl.questions.templates.{cls.question_type}",
            "question_presentation.jinja",
        ) as file:
            return Prompt(text=file.read())

    @property
    def question_presentation(self):
        if self._question_presentation is None:
            return self.default_question_presentation()
        return self._question_presentation

    @question_presentation.setter
    def question_presentation(self, value):
        self._question_presentation = value

    def prompt_preview(self, scenario=None, agent=None):
        return self.new_default_instructions.render(
            self.data
            | {
                "include_comment": getattr(self, "_include_comment", True),
                "use_code": getattr(self, "_use_code", True),
            }
            | ({"scenario": scenario} or {})
            | ({"agent": agent} or {})
        )

    @classmethod
    def self_check(cls):
        q = cls.example()
        for answer, params in q.response_validator.valid_examples:
            for key, value in params.items():
                setattr(q, key, value)
            q._validate_answer(answer)
        for answer, params, reason in q.response_validator.invalid_examples:
            for key, value in params.items():
                setattr(q, key, value)
            try:
                q._validate_answer(answer)
            except QuestionAnswerValidationError:
                pass
            else:
                raise ValueError(f"Example {answer} should have failed for {reason}.")

    @property
    def new_default_instructions(self) -> "Prompt":
        "This is set up as a property because there are mutable question values that determine how it is rendered."
        return self.question_presentation + self.answering_instructions

    @property
    def parameters(self) -> set[str]:
        """Return the parameters of the question."""
        from jinja2 import Environment, meta

        env = Environment()
        # Parse the template
        txt = self._all_text()
        # txt = self.question_text
        # if hasattr(self, "question_options"):
        #    txt += " ".join(self.question_options)
        parsed_content = env.parse(txt)
        # Extract undeclared variables
        variables = meta.find_undeclared_variables(parsed_content)
        # Return as a list
        return set(variables)

    def get_instructions(self, model: Optional[str] = None) -> type["PromptBase"]:
        """Get the mathcing question-answering instructions for the question.

        :param model: The language model to use.
        """
        from edsl.prompts.Prompt import Prompt

        if model in self.model_instructions:
            return Prompt(text=self.model_instructions[model])
        else:
            if hasattr(self, "new_default_instructions"):
                return self.new_default_instructions
            else:
                return self.applicable_prompts(model)[0]()
