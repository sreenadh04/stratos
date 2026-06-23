# stratos/llm/providers.py
"""
Provider-agnostic LLM abstraction layer.
Supports multiple providers with a unified interface.
"""
from abc import ABC, abstractmethod
from typing import Optional
import json
import re
from groq import Groq
import google.generativeai as genai
from stratos.config import settings
from stratos.retry import with_retry
from stratos.logging_config import get_logger

logger = get_logger("llm")


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response from the LLM."""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name."""
        pass


class GroqProvider(LLMProvider):
    """Groq provider using Llama 3.3 70B."""
    
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"
        self._provider_name = "groq"
    
    @with_retry(max_attempts=3, min_wait=1.0, max_wait=15.0, operation_name="Groq LLM")
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate response using Groq with retry logic."""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Prepare request params
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # Add JSON response format if requested
        if response_format == "json":
            params["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**params)
        content = response.choices[0].message.content
        
        # If JSON format requested, try to extract JSON
        if response_format == "json":
            content = self._extract_json(content)
        
        return content
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that may contain markdown."""
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text.replace("```json", "", 1)
        if text.startswith("```"):
            text = text.replace("```", "", 1)
        if text.endswith("```"):
            text = text[:-3]
        
        # Try to find JSON object using regex
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        
        return text.strip()
    
    def get_provider_name(self) -> str:
        return self._provider_name


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""
    
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = "gemini-2.0-flash-exp"
        self._provider_name = "gemini"
    
    @with_retry(max_attempts=3, min_wait=1.0, max_wait=15.0, operation_name="Gemini LLM")
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate response using Gemini with retry logic."""
        # Build the full prompt with system instruction if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        model = genai.GenerativeModel(
            self.model,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
        )
        
        response = model.generate_content(full_prompt)
        content = response.text
        
        # If JSON format requested, try to extract JSON
        if response_format == "json":
            content = self._extract_json(content)
        
        return content
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that may contain markdown."""
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text.replace("```json", "", 1)
        if text.startswith("```"):
            text = text.replace("```", "", 1)
        if text.endswith("```"):
            text = text[:-3]
        
        # Try to find JSON object using regex
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        
        return text.strip()
    
    def get_provider_name(self) -> str:
        return self._provider_name