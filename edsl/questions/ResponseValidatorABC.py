from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from typing import Optional, Any, List, TypedDict

from edsl.exceptions import QuestionAnswerValidationError


class BaseResponse(BaseModel):
    answer: Any
    comment: Optional[str] = None
    generated_tokens: Optional[str] = None


class ResponseValidatorABC(ABC):
    required_params: List[str] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        required_class_vars = ["required_params", "valid_examples", "invalid_examples"]
        for var in required_class_vars:
            if not hasattr(cls, var):
                raise ValueError(f"Class {cls.__name__} must have a '{var}' attribute.")

    def __init__(
        self,
        response_model: type[BaseModel],
        exception_to_throw: Optional[Exception] = None,
        override_answer: Optional[dict] = None,
        **kwargs,
    ):
        self.response_model = response_model
        self.exception_to_throw = exception_to_throw  # for testing
        self.override_answer = override_answer  # for testing

        # Validate required parameters
        missing_params = [
            param for param in self.required_params if param not in kwargs
        ]
        if missing_params:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing_params)}"
            )

        # Set attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.fixes_tried = 0

    def _preprocess(self, data):
        if self.exception_to_throw:
            raise self.exception_to_throw
        return self.override_answer if self.override_answer else data

    def _base_validate(self, data) -> BaseModel:
        return self.response_model(**data)

    def post_validation_answer_convert(self, data):
        return data

    class RawEdslAnswerDict(TypedDict):
        answer: Any
        comment: Optional[str]
        generated_tokens: Optional[str]

    class EdslAnswerDict(TypedDict):
        answer: Any
        comment: Optional[str]
        generated_tokens: Optional[str]

    def validate(self, raw_edsl_answer_dict: RawEdslAnswerDict) -> EdslAnswerDict:
        proposed_edsl_answer_dict = self._preprocess(raw_edsl_answer_dict)
        try:
            pydantic_edsl_answer: BaseModel = self._base_validate(
                proposed_edsl_answer_dict
            )
            self._check_constraints(pydantic_edsl_answer)
            edsl_answer_dict = self._extract_answer(pydantic_edsl_answer)
            return self._post_process(edsl_answer_dict)
        except Exception as e:
            return self._handle_exception(e, raw_edsl_answer_dict)

    def _handle_exception(self, e: Exception, raw_edsl_answer_dict) -> EdslAnswerDict:
        if self.fixes_tried == 0 and hasattr(self, "fix"):
            self.fixes_tried += 1
            fixed_data = self.fix(raw_edsl_answer_dict)
            return self.validate(fixed_data)
        else:
            raise QuestionAnswerValidationError(
                str(e), data=raw_edsl_answer_dict, model=self.response_model
            )

    def _check_constraints(self, response) -> dict:
        pass

    def _extract_answer(self, response: BaseModel) -> EdslAnswerDict:
        return response.model_dump()

    def _post_process(self, edsl_answer_dict: EdslAnswerDict) -> EdslAnswerDict:
        return edsl_answer_dict


# Example usage
if __name__ == "__main__":
    pass
