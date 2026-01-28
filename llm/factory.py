# llm/factory.py
import os
from typing import Dict, Type
from llm.base import BaseLLMProvider
from llm.anthropic import AnthropicProvider
from llm.ollama import OLLAMAProvider


class LLMFactory:
    """Factory class for creating and managing LLM provider instances."""
    
    # Provider registry mapping provider names to their implementation classes
    _PROVIDER_REGISTRY: Dict[str, Type[BaseLLMProvider]] = {
        "anthropic": AnthropicProvider,
        "ollama": OLLAMAProvider,
    }
    
    @staticmethod
    def get_provider(provider_type: str = "anthropic", config: dict = None) -> BaseLLMProvider:
        """
        Factory method to get an initialized LLM provider instance.
        
        Args:
            provider_type (str): Type of provider ('anthropic' or 'ollama'). Defaults to 'anthropic'.
            config (dict): Configuration dictionary for the provider. Defaults to None.
            
        Returns:
            BaseLLMProvider: Initialized provider instance.
            
        Raises:
            ValueError: If provider_type is not supported.
        """
        if config is None:
            config = {}
        
        provider_type = provider_type.lower().strip()
        
        if provider_type not in LLMFactory._PROVIDER_REGISTRY:
            supported = ", ".join(LLMFactory._PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported provider: '{provider_type}'. "
                f"Supported providers: {supported}"
            )
        
        provider_class = LLMFactory._PROVIDER_REGISTRY[provider_type]
        provider_instance = provider_class()
        provider_instance.initialize(config)
        
        return provider_instance
    
    @staticmethod
    def register_provider(name: str, provider_class: Type[BaseLLMProvider]) -> None:
        """
        Register a new provider in the factory registry.
        
        Args:
            name (str): Name identifier for the provider.
            provider_class (Type[BaseLLMProvider]): Provider class inheriting from BaseLLMProvider.
        """
        LLMFactory._PROVIDER_REGISTRY[name.lower()] = provider_class
    
    @staticmethod
    def get_supported_providers() -> list:
        """
        Get list of supported provider names.
        
        Returns:
            list: List of supported provider type names.
        """
        return list(LLMFactory._PROVIDER_REGISTRY.keys())