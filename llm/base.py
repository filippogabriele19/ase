# llm/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, AsyncIterator


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    Defines the interface that all LLM providers must implement.
    """

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize the LLM provider with configuration.
        
        Args:
            config: Configuration dictionary containing provider-specific settings
                   (e.g., api_key, model, temperature, max_tokens)
        """
        pass

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        **kwargs
    ) -> str:
        """
        Generate a response from the LLM provider.
        
        Args:
            prompt: The user prompt/query
            system_prompt: Optional system prompt to guide the model behavior
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            The generated response text
        """
        pass

    @abstractmethod
    def stream_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream a response from the LLM provider.
        
        Args:
            prompt: The user prompt/query
            system_prompt: Optional system prompt to guide the model behavior
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Chunks of the generated response text
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current model configuration.
        
        Returns:
            Dictionary containing model information such as:
            - model_name: Name of the model
            - provider: Name of the provider
            - max_tokens: Maximum tokens supported
            - capabilities: List of supported features
        """
        pass