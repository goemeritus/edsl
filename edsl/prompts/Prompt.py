from __future__ import annotations
from typing import Optional
from abc import ABC
from typing import Any, List

from jinja2 import Environment, FileSystemLoader
from typing import Union, Dict
from pathlib import Path

from rich.table import Table
from jinja2 import Template, Environment, meta, TemplateSyntaxError, Undefined


class PreserveUndefined(Undefined):
    def __str__(self):
        return "{{ " + str(self._undefined_name) + " }}"


from edsl.exceptions.prompts import TemplateRenderError
from edsl.base.Base import PersistenceMixin, RichPrintingMixin

MAX_NESTING = 100


class Prompt(PersistenceMixin, RichPrintingMixin):
    """Class for creating a prompt to be used in a survey."""

    default_instructions: Optional[str] = "Do good things, friendly LLM!"

    def _repr_html_(self):
        """Return an HTML representation of the Prompt."""
        from edsl.utilities.utilities import data_to_html

        return data_to_html(self.to_dict())

    def __len__(self):
        """Return the length of the prompt text."""
        return len(self.text)

    @classmethod
    def prompt_attributes(cls) -> List[str]:
        """Return the prompt class attributes."""
        return {k: v for k, v in cls.__dict__.items() if not k.startswith("_")}

    def __init__(self, text: Optional[str] = None):
        """Create a `Prompt` object.

        :param text: The text of the prompt.
        """
        if text is None:
            if hasattr(self, "default_instructions"):
                text = self.default_instructions
            else:
                text = ""
        if isinstance(text, Prompt):
            # make it idempotent w/ a prompt
            text = text.text
        self._text = text

    @classmethod
    def from_txt(cls, filename: str) -> PromptBase:
        """Create a `Prompt` from text.

        :param text: The text of the prompt.
        """
        with open(filename, "r") as f:
            text = f.read()
        return cls(text=text)

    @classmethod
    def from_template(
        cls,
        file_name: str,
        path_to_folder: Optional[Union[str, Path]] = None,
        **kwargs: Dict[str, Any],
    ) -> "PromptBase":
        """Create a `PromptBase` from a Jinja template.

        Args:
            file_name (str): The name of the Jinja template file.
            path_to_folder (Union[str, Path]): The path to the folder containing the template.
                            Can be absolute or relative.
            **kwargs: Variables to be passed to the template for rendering.

        Returns:
            PromptBase: An instance of PromptBase with the rendered template as text.
        """
        # if file_name lacks the .j2 extension, add it
        if not file_name.endswith(".jinja"):
            file_name += ".jinja"

        # Convert path_to_folder to a Path object if it's a string
        if path_to_folder is None:
            from importlib import resources
            import os

            path_to_folder = resources.path("edsl.questions", "prompt_templates")

        try:
            folder_path = Path(path_to_folder)
        except Exception as e:
            raise ValueError(f"Invalid path: {path_to_folder}. Error: {e}")

        with open(folder_path.joinpath(file_name), "r") as f:
            text = f.read()
        return cls(text=text)

    @property
    def text(self):
        """Return the `Prompt` text."""
        return self._text

    def __add__(self, other_prompt):
        """Add two prompts together.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p2 = Prompt("How are you?")
        >>> p + p2
        Prompt(text=\"""Hello, {{person}}How are you?\""")

        >>> p + "How are you?"
        Prompt(text=\"""Hello, {{person}}How are you?\""")
        """
        if isinstance(other_prompt, str):
            return self.__class__(self.text + other_prompt)
        else:
            return self.__class__(text=self.text + other_prompt.text)

    def __str__(self):
        """Return the `Prompt` text.

        Example:
        >>> p = Prompt("Hello, {{person}}")
        >>> str(p)
        'Hello, {{person}}'
        """
        return self.text

    def __contains__(self, text_to_check):
        """Check if the text_to_check is in the `Prompt` text.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> "person" in p
        True
        >>> "person2" in p
        False
        """
        return text_to_check in self.text

    def __repr__(self):
        """Return the `Prompt` text.

        Example:
        >>> p = Prompt("Hello, {{person}}")
        >>> p
        Prompt(text=\"""Hello, {{person}}\""")
        """
        return f'Prompt(text="""{self.text}""")'

    def template_variables(self) -> list[str]:
        """Return the the variables in the template.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p.template_variables()
        ['person']

        """
        return self._template_variables(self.text)

    @staticmethod
    def _template_variables(template: str) -> list[str]:
        """Find and return the template variables.

        :param template: The template to find the variables in.

        """
        env = Environment(undefined=PreserveUndefined)
        ast = env.parse(template)
        return list(meta.find_undeclared_variables(ast))

    def undefined_template_variables(self, replacement_dict: dict):
        """Return the variables in the template that are not in the replacement_dict.

        :param replacement_dict: A dictionary of replacements to populate the template.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p.undefined_template_variables({"person": "John"})
        []

        >>> p = Prompt("Hello, {{title}} {{person}}")
        >>> p.undefined_template_variables({"person": "John"})
        ['title']
        """
        return [var for var in self.template_variables() if var not in replacement_dict]

    def unused_traits(self, traits: dict):
        """Return the traits that are not used in the template."""
        return [trait for trait in traits if trait not in self.template_variables()]

    @property
    def has_variables(self) -> bool:
        """Return True if the prompt has variables.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p.has_variables
        True

        >>> p = Prompt("Hello, person")
        >>> p.has_variables
        False
        """
        return len(self.template_variables()) > 0

    def render(self, primary_replacement: dict, **additional_replacements) -> str:
        """Render the prompt with the replacements.

        :param primary_replacement: The primary replacement dictionary.
        :param additional_replacements: Additional replacement dictionaries.

        >>> p = Prompt("Hello, {{person}}")
        >>> p.render({"person": "John"})
        Prompt(text=\"""Hello, John\""")

        >>> p.render({"person": "Mr. {{last_name}}", "last_name": "Horton"})
        Prompt(text=\"""Hello, Mr. Horton\""")

        >>> p.render({"person": "Mr. {{last_name}}", "last_name": "Ho{{letter}}ton"}, max_nesting = 1)
        Prompt(text=\"""Hello, Mr. Ho{{ letter }}ton\""")

        >>> p.render({"person": "Mr. {{last_name}}"})
        Prompt(text=\"""Hello, Mr. {{ last_name }}\""")
        """
        try:
            new_text = self._render(
                self.text, primary_replacement, **additional_replacements
            )
            return self.__class__(text=new_text)
        except Exception as e:
            print(f"Error rendering prompt: {e}")
            return self

    @staticmethod
    def _render(
        text: str, primary_replacement, **additional_replacements
    ) -> "PromptBase":
        """Render the template text with variables replaced from the provided named dictionaries.

        :param text: The text to render.
        :param primary_replacement: The primary replacement dictionary.
        :param additional_replacements: Additional replacement dictionaries.

        Allows for nested variable resolution up to a specified maximum nesting depth.

        Example:

        >>> codebook = {"age": "Age"}
        >>> p = Prompt("You are an agent named {{ name }}. {{ codebook['age']}}: {{ age }}")
        >>> p.render({"name": "John", "age": 44}, codebook=codebook)
        Prompt(text=\"""You are an agent named John. Age: 44\""")
        """
        env = Environment(undefined=PreserveUndefined)
        try:
            previous_text = None
            for _ in range(MAX_NESTING):
                # breakpoint()
                rendered_text = env.from_string(text).render(
                    primary_replacement, **additional_replacements
                )
                if rendered_text == previous_text:
                    # No more changes, so return the rendered text
                    return rendered_text
                previous_text = text
                text = rendered_text

            # If the loop exits without returning, it indicates too much nesting
            raise TemplateRenderError(
                "Too much nesting - you created an infinite loop here, pal"
            )
        except TemplateSyntaxError as e:
            raise TemplateRenderError(
                f"Template syntax error: {e}. Bad template: {text}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the `Prompt` as a dictionary.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p.to_dict()
        {'text': 'Hello, {{person}}', 'class_name': 'Prompt'}

        """
        return {"text": self.text, "class_name": self.__class__.__name__}

    @classmethod
    def from_dict(cls, data) -> PromptBase:
        """Create a `Prompt` from a dictionary.

        Example:

        >>> p = Prompt("Hello, {{person}}")
        >>> p2 = Prompt.from_dict(p.to_dict())
        >>> p2
        Prompt(text=\"""Hello, {{person}}\""")

        """
        # class_name = data["class_name"]
        return Prompt(text=data["text"])

    def rich_print(self):
        """Display an object as a table."""
        table = Table(title="Prompt")
        table.add_column("Attribute", style="bold")
        table.add_column("Value")

        to_display = self.__dict__.copy()
        for attr_name, attr_value in to_display.items():
            table.add_row(attr_name, repr(attr_value))
        table.add_row("Component type", str(self.component_type))
        table.add_row("Model", str(getattr(self, "model", "Not specified")))
        return table

    @classmethod
    def example(cls):
        """Return an example of the prompt."""
        return cls(cls.default_instructions)


if __name__ == "__main__":
    print("Running doctests...")
    import doctest

    doctest.testmod()

# from edsl.prompts.library.question_multiple_choice import *
# from edsl.prompts.library.agent_instructions import *
# from edsl.prompts.library.agent_persona import *

# from edsl.prompts.library.question_budget import *
# from edsl.prompts.library.question_checkbox import *
# from edsl.prompts.library.question_freetext import *
# from edsl.prompts.library.question_linear_scale import *
# from edsl.prompts.library.question_numerical import *
# from edsl.prompts.library.question_rank import *
# from edsl.prompts.library.question_extract import *
# from edsl.prompts.library.question_list import *
