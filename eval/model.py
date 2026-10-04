"""Model client. To evaluate another provider, add a client with the same `ask` method."""

from dataclasses import dataclass

import anthropic


@dataclass
class ModelResponse:
    text: str
    stop_reason: str | None
    refusal_category: str | None
    input_tokens: int
    output_tokens: int
    request_id: str | None


class ClaudeClient:
    def __init__(self, model_config, api_key=None):
        self.config = model_config
        # api_key=None lets the SDK fall back to ANTHROPIC_API_KEY / `ant auth login`.
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=model_config.max_retries)

    def ask(self, system, user):
        response = self.client.messages.create(
            model=self.config.name,
            max_tokens=self.config.max_tokens,
            system=system,
            output_config={"effort": self.config.effort},
            messages=[{"role": "user", "content": user}],
        )
        refused = response.stop_reason == "refusal" and response.stop_details
        return ModelResponse(
            text="".join(b.text for b in response.content if b.type == "text"),
            stop_reason=response.stop_reason,
            refusal_category=response.stop_details.category if refused else None,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            request_id=response._request_id,
        )
