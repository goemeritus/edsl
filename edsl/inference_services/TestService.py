from typing import Any, List
import os
import asyncio
from edsl.inference_services.InferenceServiceABC import InferenceServiceABC
from edsl.language_models import LanguageModel
from edsl.inference_services.rate_limits_cache import rate_limits
from edsl.utilities.utilities import fix_partial_correct_response

from edsl.enums import InferenceServiceType


class TestService(InferenceServiceABC):
    """OpenAI service class."""

    key_sequence = None
    model_exclude_list = []
    _inference_service_ = "test"

    @classmethod
    def available(cls) -> list[str]:
        return ["test"]

    @classmethod
    def create_model(cls, model_name, model_class_name=None) -> LanguageModel:

        throw_exception = False

        class TestLanguageModelGood(LanguageModel):
            use_cache = False
            _model_ = "test"
            _parameters_ = {"temperature": 0.5}
            _inference_service_ = InferenceServiceType.TEST.value
            key_sequence = ["message", 0, "text"]

            async def async_execute_model_call(
                self, user_prompt: str, system_prompt: str
            ) -> dict[str, Any]:
                await asyncio.sleep(0.1)
                # return {"message": """{"answer": "Hello, world"}"""}
                if throw_exception:
                    raise Exception("This is a test error")
                return {"message": [{"text": f"{self.canned_response}"}]}

        return TestLanguageModelGood

    # _inference_service_ = "openai"
    # _env_key_name_ = "OPENAI_API_KEY"
    # _base_url_ = None

    # _sync_client_ = openai.OpenAI
    # _async_client_ = openai.AsyncOpenAI

    # _sync_client_instance = None
    # _async_client_instance = None

    # key_sequence = ["choices", 0, "message", "content"]
