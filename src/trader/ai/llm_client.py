"""LLM client for DeepSeek and OpenAI compatible APIs.

Provides a unified interface for interacting with LLM APIs with
automatic retry logic, error handling, and response parsing.
"""
import os
import time
import json
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal
from dataclasses import dataclass
from pydantic import BaseModel, Field
import httpx


class LLMMessage(BaseModel):
    """Message in a conversation with an LLM."""
    role: str = Field(description="Role of the message sender (system, user, assistant)")
    content: str = Field(description="Content of the message")


class LLMFunctionCall(BaseModel):
    """Function call requested by the LLM."""
    name: str = Field(description="Name of the function to call")
    arguments: Dict[str, Any] = Field(description="Arguments for the function")


class LLMResponse(BaseModel):
    """Response from an LLM."""
    content: Optional[str] = Field(default=None, description="Text content of the response")
    function_calls: List[LLMFunctionCall] = Field(default_factory=list, description="Function calls requested")
    model: str = Field(description="Model used for the response")
    usage: Dict[str, int] = Field(default_factory=dict, description="Token usage statistics")
    prompt_tokens: int = Field(default=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(default=0, description="Number of tokens in the completion")
    total_tokens: int = Field(default=0, description="Total tokens used")


class LLMConfig(BaseModel):
    """Configuration for LLM client."""
    api_key: str = Field(description="API key for authentication")
    base_url: str = Field(description="Base URL for the API")
    model: str = Field(default="deepseek-chat", description="Model to use")
    temperature: float = Field(default=0.7, description="Temperature for sampling")
    max_tokens: int = Field(default=2000, description="Maximum tokens in response")
    timeout: int = Field(default=60, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")


class LLMClient:
    """Unified LLM client supporting DeepSeek and OpenAI compatible APIs.

    Provides automatic retry logic, error handling, and function calling support.
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """Initialize LLM client.

        Args:
            config: Complete LLMConfig object
            api_key: API key (alternative to config)
            base_url: Base URL (alternative to config)
            model: Model name (alternative to config)
        """
        if config is None:
            # Try to get from environment variables
            api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            base_url = base_url or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL")
            
            if not api_key:
                raise ValueError("API key must be provided either via config or environment variable")
            
            # Set reasonable defaults
            if base_url is None:
                # Default to DeepSeek
                base_url = "https://api.deepseek.com"
                model = model or "deepseek-chat"
            elif "openai" in base_url.lower():
                model = model or "gpt-4"
            
            config = LLMConfig(
                api_key=api_key,
                base_url=base_url,
                model=model or "deepseek-chat",
            )
        
        self.config = config
        self._client = httpx.Client(timeout=config.timeout)

    def chat(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict]] = None,
    ) -> LLMResponse:
        """Send a chat request to the LLM.

        Args:
            messages: List of conversation messages
            temperature: Temperature for sampling (overrides config)
            max_tokens: Maximum tokens (overrides config)
            functions: Optional list of function definitions for function calling

        Returns:
            LLMResponse with the model's response
        """
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        
        if functions:
            payload["functions"] = functions
            payload["function_call"] = "auto"
        
        # Execute with retries
        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                response = self._client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                
                return self._parse_response(result)
                
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                continue
        
        raise RuntimeError(f"Failed after {self.config.max_retries} attempts") from last_exception

    def _parse_response(self, response: Dict) -> LLMResponse:
        """Parse the raw API response into LLMResponse."""
        choice = response["choices"][0]
        message = choice.get("message", {})
        
        content = message.get("content")
        
        # Parse function calls
        function_calls = []
        if "function_call" in message:
            func_call = message["function_call"]
            try:
                arguments = json.loads(func_call.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            
            function_calls.append(LLMFunctionCall(
                name=func_call.get("name", ""),
                arguments=arguments,
            ))
        
        usage = response.get("usage", {})
        
        return LLMResponse(
            content=content,
            function_calls=function_calls,
            model=response.get("model", self.config.model),
            usage=usage,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    def simple_chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Simple one-off chat with the LLM.

        Args:
            user_message: User's message
            system_prompt: Optional system prompt
            temperature: Optional temperature override

        Returns:
            The LLM's text response
        """
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=user_message))
        
        response = self.chat(messages, temperature=temperature)
        return response.content or ""

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "LLMClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Convenience factory functions
def create_deepseek_client(
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    **kwargs,
) -> LLMClient:
    """Create a DeepSeek LLM client.

    Args:
        api_key: DeepSeek API key (defaults to DEEPSEEK_API_KEY env var)
        model: Model to use (default: deepseek-chat)
        **kwargs: Additional config options

    Returns:
        Configured LLMClient for DeepSeek
    """
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")
    
    config = LLMConfig(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model=model,
        **kwargs,
    )
    return LLMClient(config=config)


def create_openai_client(
    api_key: Optional[str] = None,
    model: str = "gpt-4",
    base_url: Optional[str] = None,
    **kwargs,
) -> LLMClient:
    """Create an OpenAI-compatible LLM client.

    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        model: Model to use (default: gpt-4)
        base_url: Optional base URL for custom endpoints
        **kwargs: Additional config options

    Returns:
        Configured LLMClient for OpenAI
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    config = LLMConfig(
        api_key=api_key,
        base_url=base_url or "https://api.openai.com/v1",
        model=model,
        **kwargs,
    )
    return LLMClient(config=config)
