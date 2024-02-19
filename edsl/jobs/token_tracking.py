
class TokenPricing:
    def __init__(self, model_name, prompt_token_price, completion_token_price):
        self.model_name = model_name
        self.prompt_token_price = prompt_token_price
        self.completion_token_price = completion_token_price

    def __eq__(self, other):
        if not isinstance(other, TokenPricing):
            return False
        return self.model_name == other.model_name and self.prompt_token_price == other.prompt_token_price and self.completion_token_price == other.completion_token_price

class TokenUsage:

    def __init__(self, from_cache: bool, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.from_cache = from_cache
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def add_tokens(self, prompt_tokens, completion_tokens):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
 
    def __add__(self, other):
        if not isinstance(other, TokenUsage):
            raise ValueError(f"Can't add {type(other)} to InterviewTokenUsage")
        if self.from_cache != other.from_cache:
            raise ValueError(f"Can't add token usages from different sources")
        return TokenUsage(
            use_cache = self.from_cache,
            prompt_tokens = self.prompt_tokens + other.prompt_tokens,
            completion_tokens = self.completion_tokens + other.completion_tokens
        )
    
    def cost(self, prices: TokenPricing):
        return self.prompt_tokens * prices.prompt_token_price + self.completion_tokens * prices.completion_token_price
    

class InterviewTokenUsage:
    def __init__(self, new_token_usage, cached_token_usage):
        self.new_token_usage = new_token_usage
        self.cached_token_usage = cached_token_usage

    def __add__(self, other):
        if not isinstance(other, InterviewTokenUsage):
            raise ValueError(f"Can't add {type(other)} to InterviewTokenSummary")
        return InterviewTokenUsage(
            new_token_usage = self.new_token_usage + other.new_token_usage,
            cached_token_usage = self.cached_token_usage + other.cached_token_usage
        )

