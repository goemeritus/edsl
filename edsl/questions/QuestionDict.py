from __future__ import annotations
from typing import Union, Optional, Dict, List, Any, Type
from pydantic import BaseModel, Field, field_validator
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pathlib import Path

from edsl.questions.QuestionBase import QuestionBase
from edsl.questions.descriptors import (
    AnswerKeysDescriptor,
    ValueTypesDescriptor,
    ValueDescriptionsDescriptor,
    QuestionTextDescriptor,
)
from edsl.questions.response_validator_abc import ResponseValidatorABC
from edsl.exceptions.questions import QuestionCreationValidationError
from edsl.questions.decorators import inject_exception


class DictResponseValidator(ResponseValidatorABC):
    required_params = ["answer_keys", "permissive"]

    valid_examples = [
        (
            {
                "answer": {
                    "name": "Hot Chocolate",
                    "num_ingredients": 5,
                    "ingredients": ["milk", "cocoa", "sugar"]
                }
            },
            {
                "answer_keys": ["name", "num_ingredients", "ingredients"],
                "value_types": ["str", "int", "list[str]"]
            },
        )
    ]
    invalid_examples = [
        (
            {"answer": {"name": 123}},  # Name should be a string
            {"answer_keys": ["name"], "value_types": ["str"]},
            "Key 'name' has value of type int, expected str",
        ),
        (
            {"answer": {"ingredients": "milk"}},  # Should be a list
            {"answer_keys": ["ingredients"], "value_types": ["list"]},
            "Key 'ingredients' should be a list, got str",
        )
    ]


class QuestionDict(QuestionBase):
    question_type = "dict"
    question_text: str = QuestionTextDescriptor()
    answer_keys: List[str] = AnswerKeysDescriptor()
    value_types: Optional[List[str]] = ValueTypesDescriptor()
    value_descriptions: Optional[List[str]] = ValueDescriptionsDescriptor()

    _response_model = None
    response_validator_class = DictResponseValidator

    def _get_default_answer(self) -> Dict[str, Any]:
        """Get default answer based on types."""
        answer = {}
        if not self.value_types:
            return {
                "title": "Sample Recipe",
                "ingredients": ["ingredient1", "ingredient2"],
                "num_ingredients": 2,
                "instructions": "Sample instructions"
            }

        for key, type_str in zip(self.answer_keys, self.value_types):
            if type_str.startswith(('list[', 'list')):
                if '[' in type_str:
                    element_type = type_str[type_str.index('[') + 1:type_str.rindex(']')].lower()
                    if element_type == 'str':
                        answer[key] = ["sample_string"]
                    elif element_type == 'int':
                        answer[key] = [1]
                    elif element_type == 'float':
                        answer[key] = [1.0]
                    else:
                        answer[key] = []
                else:
                    answer[key] = []
            else:
                if type_str == 'str':
                    answer[key] = "sample_string"
                elif type_str == 'int':
                    answer[key] = 1
                elif type_str == 'float':
                    answer[key] = 1.0
                else:
                    answer[key] = None
                    
        return answer

    def create_response_model(
        self,
    ) -> Type[BaseModel]:
        """Create a response model for dict questions."""
        default_answer = self._get_default_answer()
        
        class DictResponse(BaseModel):
            answer: Dict[str, Any] = Field(
                default_factory=lambda: default_answer.copy()
            )
            comment: Optional[str] = None
            
            @field_validator("answer")
            def validate_answer(cls, v, values, **kwargs):
                # Ensure all keys exist
                missing_keys = set(self.answer_keys) - set(v.keys())
                if missing_keys:
                    raise ValueError(f"Missing required keys: {missing_keys}")
                    
                # Validate value types if not permissive
                if not self.permissive and self.value_types:
                    for key, type_str in zip(self.answer_keys, self.value_types):
                        if key not in v:
                            continue
                            
                        value = v[key]
                        type_str = type_str.lower()  # Normalize to lowercase
                        
                        # Handle list types
                        if type_str.startswith(('list[', 'list')):
                            if not isinstance(value, list):
                                raise ValueError(f"Key '{key}' should be a list, got {type(value).__name__}")
                                
                            # If it's a parameterized list, check element types
                            if '[' in type_str:
                                element_type = type_str[type_str.index('[') + 1:type_str.rindex(']')]
                                element_type = element_type.lower().strip()
                                
                                for i, elem in enumerate(value):
                                    expected_type = {
                                        'str': str,
                                        'int': int,
                                        'float': float,
                                        'list': list
                                    }.get(element_type)
                                    
                                    if expected_type and not isinstance(elem, expected_type):
                                        raise ValueError(
                                            f"List element at index {i} for key '{key}' "
                                            f"has type {type(elem).__name__}, expected {element_type}"
                                        )
                        else:
                            # Handle basic types
                            expected_type = {
                                'str': str,
                                'int': int,
                                'float': float,
                                'list': list,
                            }.get(type_str)
                            
                            if expected_type and not isinstance(value, expected_type):
                                raise ValueError(
                                    f"Key '{key}' has value of type {type(value).__name__}, expected {type_str}"
                                )
                return v

            model_config = {
                "json_schema_extra": {
                    "examples": [{
                        "answer": default_answer,
                        "comment": None
                    }]
                }
            }

        DictResponse.__name__ = "DictResponse"
        return DictResponse

    def __init__(
        self,
        question_name: str,
        question_text: str,
        answer_keys: List[str],
        value_types: Optional[List[Union[str, type]]] = None,
        value_descriptions: Optional[List[str]] = None,
        include_comment: bool = True,
        question_presentation: Optional[str] = None,
        answering_instructions: Optional[str] = None,
        permissive: bool = False,
    ):
        self.question_name = question_name
        self.question_text = question_text
        self.answer_keys = answer_keys
        self.value_types = self._normalize_value_types(value_types)
        self.value_descriptions = value_descriptions
        self.include_comment = include_comment
        self.question_presentation = question_presentation or self._render_template(
            "question_presentation.jinja"
        )
        self.answering_instructions = answering_instructions or self._render_template(
            "answering_instructions.jinja"
        )
        self.permissive = permissive

        # Validation
        if self.value_types and len(self.value_types) != len(self.answer_keys):
            raise QuestionCreationValidationError(
                "Length of value_types must match length of answer_keys."
            )
        if self.value_descriptions and len(self.value_descriptions) != len(self.answer_keys):
            raise QuestionCreationValidationError(
                "Length of value_descriptions must match length of answer_keys."
            )

    @staticmethod
    def _normalize_value_types(value_types: Optional[List[Union[str, type]]]) -> Optional[List[str]]:
        """Convert all value_types to string representations, including type hints."""
        if not value_types:
            return None

        def normalize_type(t) -> str:
            # Handle string representations of List
            t_str = str(t)
            if t_str == 'List':
                return 'list'
                
            # Handle string inputs
            if isinstance(t, str):
                t = t.lower()
                # Handle list types
                if t.startswith(('list[', 'list')):
                    if '[' in t:
                        # Normalize the inner type
                        inner_type = t[t.index('[') + 1:t.rindex(']')].strip().lower()
                        return f"list[{inner_type}]"
                    return "list"
                return t

            # Handle List the same as list
            if t_str == "<class 'List'>":
                return "list"

            # If it's list type
            if t is list:
                return "list"

            # If it's a basic type
            if hasattr(t, "__name__"):
                return t.__name__.lower()
            
            # If it's a typing.List
            if t_str.startswith(('list[', 'list')):
                return t_str.replace('typing.', '').lower()

            # Handle generic types
            if hasattr(t, "__origin__"):
                origin = t.__origin__.__name__.lower()
                args = [
                    arg.__name__.lower() if hasattr(arg, "__name__") else str(arg).lower()
                    for arg in t.__args__
                ]
                return f"{origin}[{', '.join(args)}]"

            raise QuestionCreationValidationError(
                f"Invalid type in value_types: {t}. Must be a type or string."
            )

        normalized = []
        for t in value_types:
            try:
                normalized.append(normalize_type(t))
            except Exception as e:
                raise QuestionCreationValidationError(f"Error normalizing type {t}: {str(e)}")
        
        return normalized

    def _render_template(self, template_name: str) -> str:
        """Render a template using Jinja."""
        try:
            template_dir = Path(__file__).parent / "templates" / "dict"
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template(template_name)
            return template.render(
                question_name=self.question_name,
                question_text=self.question_text,
                answer_keys=self.answer_keys,
                value_types=self.value_types,
                value_descriptions=self.value_descriptions,
                include_comment=self.include_comment,
            )
        except TemplateNotFound:
            return f"Template {template_name} not found in {template_dir}."

    def to_dict(self, add_edsl_version: bool = True) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "question_type": self.question_type,
            "question_name": self.question_name,
            "question_text": self.question_text,
            "answer_keys": self.answer_keys,
            "value_types": self.value_types or [],
            "value_descriptions": self.value_descriptions or [],
            "include_comment": self.include_comment,
            "permissive": self.permissive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'QuestionDict':
        """Recreate from a dictionary."""
        return cls(
            question_name=data["question_name"],
            question_text=data["question_text"],
            answer_keys=data["answer_keys"],
            value_types=data.get("value_types"),
            value_descriptions=data.get("value_descriptions"),
            include_comment=data.get("include_comment", True),
            permissive=data.get("permissive", False),
        )

    @classmethod
    @inject_exception
    def example(cls) -> 'QuestionDict':
        """Return an example question."""
        return cls(
            question_name="example",
            question_text="Please provide a simple recipe for hot chocolate.",
            answer_keys=["title", "ingredients", "num_ingredients", "instructions"],
            value_types=["str", "list[str]", "int", "str"],
            value_descriptions=[
                "The title of the recipe.",
                "A list of ingredients.",
                "The number of ingredients.",
                "The instructions for making the recipe."
            ],
        )

    def _simulate_answer(self) -> dict:
            """Simulate an answer for the question."""
            return {
                "answer": self._get_default_answer(),
                "comment": None
            }

if __name__ == "__main__":
    q = QuestionDict.example()
    print(q.to_dict())