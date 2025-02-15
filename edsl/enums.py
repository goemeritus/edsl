"""Enums for the different types of questions, language models, and inference services."""

from enum import Enum
from typing import Literal


class EnumWithChecks(Enum):
    """Base class for all enums with checks."""

    @classmethod
    def is_value_valid(cls, value):
        """Check if the value is valid."""
        return any(value == item.value for item in cls)


class QuestionType(EnumWithChecks):
    """Enum for the question types."""

    MULTIPLE_CHOICE = "multiple_choice"
    YES_NO = "yes_no"
    FREE_TEXT = "free_text"
    RANK = "rank"
    BUDGET = "budget"
    CHECKBOX = "checkbox"
    EXTRACT = "extract"
    FUNCTIONAL = "functional"
    LIST = "list"
    NUMERICAL = "numerical"
    TOP_K = "top_k"
    LIKERT_FIVE = "likert_five"
    LINEAR_SCALE = "linear_scale"


# https://huggingface.co/meta-llama/Llama-2-70b-chat-hf


# class LanguageModelType(EnumWithChecks):
#     """Enum for the language model types."""

#     GPT_4 = "gpt-4-1106-preview"
#     GPT_3_5_Turbo = "gpt-3.5-turbo"
#     LLAMA_2_70B_CHAT_HF = "llama-2-70b-chat-hf"
#     LLAMA_2_13B_CHAT_HF = "llama-2-13b-chat-hf"
#     GEMINI_PRO = "gemini_pro"
#     MIXTRAL_8x7B_INSTRUCT = "mixtral-8x7B-instruct-v0.1"
#     TEST = "test"
#     ANTHROPIC_3_OPUS = "claude-3-opus-20240229"
#     ANTHROPIC_3_SONNET = "claude-3-sonnet-20240229"
#     ANTHROPIC_3_HAIKU = "claude-3-haiku-20240307"
#     DBRX_INSTRUCT = "dbrx-instruct"


class InferenceServiceType(EnumWithChecks):
    """Enum for the inference service types."""

    BEDROCK = "bedrock"
    DEEP_INFRA = "deep_infra"
    REPLICATE = "replicate"
    OPENAI = "openai"
    GOOGLE = "google"
    TEST = "test"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    AZURE = "azure"
    OLLAMA = "ollama"
    MISTRAL = "mistral"
    TOGETHER = "together"
    PERPLEXITY = "perplexity"
    DEEPSEEK = "deepseek"
    XAI = "xai"


# unavoidable violation of the DRY principle but it is necessary
# checked w/ a unit test to make sure consistent with services in enums.py
InferenceServiceLiteral = Literal[
    "bedrock",
    "deep_infra",
    "replicate",
    "openai",
    "google",
    "test",
    "anthropic",
    "groq",
    "azure",
    "ollama",
    "mistral",
    "together",
    "perplexity",
    "deepseek",
    "xai",
]

available_models_urls = {
    "anthropic": "https://docs.anthropic.com/en/docs/about-claude/models",
    "openai": "https://platform.openai.com/docs/models/gp",
    "groq": "https://console.groq.com/docs/models",
    "google": "https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models",
}


service_to_api_keyname = {
    InferenceServiceType.DEEP_INFRA.value: "DEEP_INFRA_API_KEY",
    InferenceServiceType.REPLICATE.value: "TBD",
    InferenceServiceType.OPENAI.value: "OPENAI_API_KEY",
    InferenceServiceType.GOOGLE.value: "GOOGLE_API_KEY",
    InferenceServiceType.TEST.value: "TBD",
    InferenceServiceType.ANTHROPIC.value: "ANTHROPIC_API_KEY",
    InferenceServiceType.GROQ.value: "GROQ_API_KEY",
    InferenceServiceType.BEDROCK.value: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    InferenceServiceType.MISTRAL.value: "MISTRAL_API_KEY",
    InferenceServiceType.TOGETHER.value: "TOGETHER_API_KEY",
    InferenceServiceType.PERPLEXITY.value: "PERPLEXITY_API_KEY",
    InferenceServiceType.DEEPSEEK.value: "DEEPSEEK_API_KEY",
    InferenceServiceType.XAI.value: "XAI_API_KEY",
}


class TokenPricing:
    def __init__(
        self,
        *,
        model_name,
        prompt_token_price_per_k: float,
        completion_token_price_per_k: float,
    ):
        self.model_name = model_name
        self.prompt_token_price = prompt_token_price_per_k / 1_000.0
        self.completion_token_price = completion_token_price_per_k / 1_000.0

    def __eq__(self, other):
        if not isinstance(other, TokenPricing):
            return False
        return (
            self.model_name == other.model_name
            and self.prompt_token_price == other.prompt_token_price
            and self.completion_token_price == other.completion_token_price
        )


pricing = {
    "dbrx-instruct": TokenPricing(
        model_name="dbrx-instruct",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "claude-3-opus-20240229": TokenPricing(
        model_name="claude-3-opus-20240229",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "claude-3-haiku-20240307": TokenPricing(
        model_name="claude-3-haiku-20240307",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "claude-3-sonnet-20240229": TokenPricing(
        model_name="claude-3-sonnet-20240229",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "gpt-3.5-turbo": TokenPricing(
        model_name="gpt-3.5-turbo",
        prompt_token_price_per_k=0.0005,
        completion_token_price_per_k=0.0015,
    ),
    "gpt-4-1106-preview": TokenPricing(
        model_name="gpt-4",
        prompt_token_price_per_k=0.01,
        completion_token_price_per_k=0.03,
    ),
    "test": TokenPricing(
        model_name="test",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "gemini_pro": TokenPricing(
        model_name="gemini_pro",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "llama-2-13b-chat-hf": TokenPricing(
        model_name="llama-2-13b-chat-hf",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "llama-2-70b-chat-hf": TokenPricing(
        model_name="llama-2-70b-chat-hf",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
    "mixtral-8x7B-instruct-v0.1": TokenPricing(
        model_name="mixtral-8x7B-instruct-v0.1",
        prompt_token_price_per_k=0.0,
        completion_token_price_per_k=0.0,
    ),
}


def get_token_pricing(model_name):
    if model_name in pricing:
        return pricing[model_name]
    else:
        return TokenPricing(
            model_name=model_name,
            prompt_token_price_per_k=0.0,
            completion_token_price_per_k=0.0,
        )
