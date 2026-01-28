# llm/__init__.py
import os
from .base import BaseLLMProvider
from .anthropic import AnthropicProvider, call_claude
from .ollama import OLLAMAProvider
from .factory import LLMFactory

__all__ = [
    "BaseLLMProvider",
    "AnthropicProvider",
    "OLLAMAProvider",
    "LLMFactory",
    "call_model",
    "call_claude",
]

def call_model(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
    """
    Unified entry point for LLM interaction.
    Dispatches the request to the configured provider via LLMFactory.
    """
    provider_type = os.getenv("LLM_PROVIDER", "anthropic").lower()
    
    try:
        if provider_type == "anthropic":
            return call_claude(system_prompt, user_prompt, temperature)
        elif provider_type == "ollama":
            # Integrating the OLLAMAProvider you imported
            provider = OLLAMAProvider()
            return provider.call(system_prompt, user_prompt, temperature)
        elif provider_type == "local":
            raise NotImplementedError("Local LLM configuration pending migration to OLLAMAProvider.")
        else:
            raise ValueError(f"Unknown LLM provider: {provider_type}")
            
    except Exception as e:
        # Fallback or re-raise with clear context
        raise RuntimeError(f"LLM Call Failed ({provider_type}): {str(e)}") from e
