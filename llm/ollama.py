# llm/ollama.py
import os
from typing import Optional, Dict, Any, Generator

from fastapi import requests
from llm.base import BaseLLMProvider


class OLLAMAProvider(BaseLLMProvider):
    """
    Ollama LLM provider implementation for local model inference.
    Supports HTTP communication with local Ollama instance.
    """

    def __init__(self):
        self.base_url: str = "http://localhost:11434"
        self.model_name: str = "llama2"
        self.temperature: float = 0.0
        self.top_p: float = 0.9
        self.top_k: int = 40
        self.timeout: int = 300

    def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize Ollama provider with configuration.
        
        Args:
            config: Configuration dictionary with keys:
                - base_url: Ollama server URL (default: http://localhost:11434)
                - model_name: Model name to use (default: llama2)
                - temperature: Sampling temperature (default: 0.0)
                - top_p: Nucleus sampling parameter (default: 0.9)
                - top_k: Top-k sampling parameter (default: 40)
                - timeout: Request timeout in seconds (default: 300)
        """
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model_name = config.get("model_name", "llama2")
        self.temperature = config.get("temperature", 0.0)
        self.top_p = config.get("top_p", 0.9)
        self.top_k = config.get("top_k", 40)
        self.timeout = config.get("timeout", 300)

    def _check_connection(self) -> bool:
        """
        Check if Ollama server is available.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _check_model_availability(self) -> bool:
        """
        Check if the specified model is available on Ollama server.
        
        Returns:
            True if model is available, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "").split(":")[0] for m in models]
                return self.model_name in model_names
            return False
        except requests.exceptions.RequestException:
            return False

    def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate a response from Ollama model.
        
        Args:
            prompt: User prompt/query
            system_prompt: Optional system prompt for context
            **kwargs: Additional parameters (temperature, top_p, top_k)
        
        Returns:
            Generated response text
        """
        if not self._check_connection():
            raise ConnectionError(
                f"❌ Cannot connect to Ollama server at {self.base_url}"
            )

        if not self._check_model_availability():
            raise ValueError(
                f"❌ Model '{self.model_name}' not available on Ollama server"
            )

        temperature = kwargs.get("temperature", self.temperature)
        top_p = kwargs.get("top_p", self.top_p)
        top_k = kwargs.get("top_k", self.top_k)

        # Construct full prompt with system message if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()

        except requests.exceptions.Timeout:
            return f"❌ Request timeout after {self.timeout} seconds"
        except requests.exceptions.ConnectionError:
            return f"❌ Connection error: Cannot reach Ollama at {self.base_url}"
        except requests.exceptions.HTTPError as e:
            return f"❌ HTTP error: {str(e)}"
        except Exception as e:
            return f"❌ Error calling Ollama: {str(e)}"

    def stream_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Generator[str, None, None]:
        """
        Stream a response from Ollama model.
        
        Args:
            prompt: User prompt/query
            system_prompt: Optional system prompt for context
            **kwargs: Additional parameters (temperature, top_p, top_k)
        
        Yields:
            Response text chunks as they are generated
        """
        if not self._check_connection():
            raise ConnectionError(
                f"❌ Cannot connect to Ollama server at {self.base_url}"
            )

        if not self._check_model_availability():
            raise ValueError(
                f"❌ Model '{self.model_name}' not available on Ollama server"
            )

        temperature = kwargs.get("temperature", self.temperature)
        top_p = kwargs.get("top_p", self.top_p)
        top_k = kwargs.get("top_k", self.top_k)

        # Construct full prompt with system message if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "stream": True
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = response.json() if isinstance(line, bytes) else line
                        if isinstance(chunk, dict):
                            text = chunk.get("response", "")
                            if text:
                                yield text
                    except Exception:
                        continue

        except requests.exceptions.Timeout:
            yield f"❌ Request timeout after {self.timeout} seconds"
        except requests.exceptions.ConnectionError:
            yield f"❌ Connection error: Cannot reach Ollama at {self.base_url}"
        except requests.exceptions.HTTPError as e:
            yield f"❌ HTTP error: {str(e)}"
        except Exception as e:
            yield f"❌ Error streaming from Ollama: {str(e)}"