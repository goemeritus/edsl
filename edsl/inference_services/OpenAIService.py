from typing import Any, List
import re
from openai import AsyncOpenAI

from edsl.inference_services.InferenceServiceABC import InferenceServiceABC
from edsl.language_models import LanguageModel
from edsl.inference_services.rate_limits_cache import rate_limits


class OpenAIService(InferenceServiceABC):
    """OpenAI service class."""

    _inference_service_ = "openai"
    _env_key_name_ = "OPENAI_API_KEY"

    # TODO: Make this a coop call
    model_exclude_list = [
        "whisper-1",
        "davinci-002",
        "dall-e-2",
        "tts-1-hd-1106",
        "tts-1-hd",
        "dall-e-3",
        "tts-1",
        "babbage-002",
        "tts-1-1106",
        "text-embedding-3-large",
        "text-embedding-3-small",
        "text-embedding-ada-002",
        "ft:davinci-002:mit-horton-lab::8OfuHgoo",
    ]
    _models_list_cache: List[str] = []

    @classmethod
    def available(cls) -> List[str]:
        from openai import OpenAI

        if not cls._models_list_cache:
            try:
                client = OpenAI()
                cls._models_list_cache = [
                    m.id
                    for m in client.models.list()
                    if m.id not in cls.model_exclude_list
                ]
            except Exception as e:
                raise
                # print(
                #     f"""Error retrieving models: {e}.
                #     See instructions about storing your API keys: https://docs.expectedparrot.com/en/latest/api_keys.html"""
                # )
                # cls._models_list_cache = [
                #     "gpt-3.5-turbo",
                #     "gpt-4-1106-preview",
                #     "gpt-4",
                # ]  # Fallback list
        return cls._models_list_cache

    @classmethod
    def create_model(cls, model_name, model_class_name=None) -> LanguageModel:
        if model_class_name is None:
            model_class_name = cls.to_class_name(model_name)

        class LLM(LanguageModel):
            """
            Child class of LanguageModel for interacting with OpenAI models
            """

            _inference_service_ = cls._inference_service_
            _model_ = model_name
            _parameters_ = {
                "temperature": 0.5,
                "max_tokens": 1000,
                "top_p": 1,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "logprobs": False,
                "top_logprobs": 3,
            }

            @classmethod
            def available(cls) -> list[str]:
                client = openai.OpenAI()
                return client.models.list()

            def get_headers(self) -> dict[str, Any]:
                from openai import OpenAI

                client = OpenAI()
                response = client.chat.completions.with_raw_response.create(
                    messages=[
                        {
                            "role": "user",
                            "content": "Say this is a test",
                        }
                    ],
                    model=self.model,
                )
                return dict(response.headers)

            def get_rate_limits(self) -> dict[str, Any]:
                try:
                    if "openai" in rate_limits:
                        headers = rate_limits["openai"]

                    else:
                        headers = self.get_headers()

                except Exception as e:
                    return {
                        "rpm": 10_000,
                        "tpm": 2_000_000,
                    }
                else:
                    return {
                        "rpm": int(headers["x-ratelimit-limit-requests"]),
                        "tpm": int(headers["x-ratelimit-limit-tokens"]),
                    }

            async def async_execute_model_call(
                self,
                user_prompt: str,
                system_prompt: str = "",
                encoded_image=None,
            ) -> dict[str, Any]:
                """Calls the OpenAI API and returns the API response."""
                content = [{"type": "text", "text": user_prompt}]
                if encoded_image:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            },
                        }
                    )
                self.client = AsyncOpenAI()
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    frequency_penalty=self.frequency_penalty,
                    presence_penalty=self.presence_penalty,
                    logprobs=self.logprobs,
                    top_logprobs=self.top_logprobs if self.logprobs else None,
                )
                return response.model_dump()

            @staticmethod
            def parse_response(raw_response: dict[str, Any]) -> str:
                """Parses the API response and returns the response text."""
                try:
                    response = raw_response["choices"][0]["message"]["content"]
                except KeyError:
                    print("Tried to parse response but failed:")
                    print(raw_response)
                pattern = r"^```json(?:\\n|\n)(.+?)(?:\\n|\n)```$"
                match = re.match(pattern, response, re.DOTALL)
                if match:
                    return match.group(1)
                else:
                    return response

        LLM.__name__ = "LanguageModel"

        return LLM
