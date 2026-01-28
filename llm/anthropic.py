# llm/anthropic.py
import os
from anthropic import Anthropic
from llm.base import BaseLLMProvider


# Centralized configuration
DEFAULT_MODEL = "claude-haiku-4-5"
API_KEY = os.getenv("ANTHROPIC_API_KEY")


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic provider implementation inheriting from BaseLLMProvider.
    It integrates Claude models via the official Anthropic API.
    """

    def __init__(self) -> None:
        self.client = None
        self.model = None
        self.api_key = None

    def initialize(self, config: dict) -> None:
        """
        Initialize the provider.

        Expected config keys:
        - api_key (optional): overrides ANTHROPIC_API_KEY env var
        - model (optional): overrides DEFAULT_MODEL
        """
        self.api_key = config.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("❌ ANTHROPIC_API_KEY missing")

        self.model = config.get("model", DEFAULT_MODEL)
        self.client = Anthropic(api_key=self.api_key)

    def generate_response(self, prompt: str, **kwargs) -> str:
        """
        Generate a single completion from Claude.

        kwargs:
        - system_prompt (optional): system prompt string
        - temperature (optional): float, default 0.0
        - max_tokens (optional): int, default 16000
        """
        if not self.client:
            raise RuntimeError("Provider not initialized. Call initialize() first.")

        system_prompt = kwargs.get("system_prompt", "")
        temperature = kwargs.get("temperature", 0.0)
        max_tokens = kwargs.get("max_tokens", 16000)

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else None,
                messages=messages,
            )
            return response.content[0].text
        except Exception as e:
            return f"❌ Error calling LLM: {str(e)}"

    def stream_response(self, prompt: str, **kwargs):
        """
        Stream a completion from Claude.

        kwargs:
        - system_prompt (optional): system prompt string
        - temperature (optional): float, default 0.0
        - max_tokens (optional): int, default 16000
        """
        if not self.client:
            raise RuntimeError("Provider not initialized. Call initialize() first.")

        system_prompt = kwargs.get("system_prompt", "")
        temperature = kwargs.get("temperature", 0.0)
        max_tokens = kwargs.get("max_tokens", 16000)

        messages = [{"role": "user", "content": prompt}]

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else None,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"❌ Error calling LLM: {str(e)}"

    def get_model_info(self) -> dict:
        """Return provider/model metadata useful for debugging and UI."""
        return {
            "provider": "anthropic",
            "model": self.model,
            "api_key_configured": bool(self.api_key),
        }


def call_claude(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
    """
    Backward-compatible convenience wrapper around AnthropicProvider.

    Note: kept for legacy codepaths; prefer using AnthropicProvider directly in new code.
    """
    provider = AnthropicProvider()
    provider.initialize({})
    return provider.generate_response(
        user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
    )
