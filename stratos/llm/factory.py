# stratos/llm/factory.py
"""
Factory for creating LLM provider instances.
"""
from typing import Optional
from stratos.llm.providers import LLMProvider, GroqProvider, GeminiProvider
from stratos.config import settings


class LLMFactory:
    """Factory for LLM providers."""
    
    _providers = {
        "groq": GroqProvider,
        "gemini": GeminiProvider,
    }
    
    _default_provider = "groq"
    
    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> LLMProvider:
        """
        Get an LLM provider instance.
        
        Args:
            provider_name: Name of provider (groq, gemini). 
                          Defaults to configured default.
        
        Returns:
            LLMProvider instance
        
        Raises:
            ValueError: If provider not found or API key missing.
        """
        if provider_name is None:
            # Use configured provider or default
            provider_name = getattr(settings, "llm_provider", cls._default_provider)
        
        provider_class = cls._providers.get(provider_name.lower())
        if provider_class is None:
            raise ValueError(f"Unknown LLM provider: {provider_name}")
        
        # Check API key
        if provider_name.lower() == "groq" and not settings.groq_api_key:
            # Fallback to Gemini if Groq key missing
            print(f"⚠️ Groq API key missing, falling back to Gemini")
            provider_class = cls._providers["gemini"]
        elif provider_name.lower() == "gemini" and not settings.gemini_api_key:
            # Fallback to Groq if Gemini key missing
            print(f"⚠️ Gemini API key missing, falling back to Groq")
            provider_class = cls._providers["groq"]
        
        return provider_class()
    
    @classmethod
    def register_provider(cls, name: str, provider_class):
        """Register a new provider."""
        cls._providers[name.lower()] = provider_class
    
    @classmethod
    def list_providers(cls) -> list:
        """List available provider names."""
        return list(cls._providers.keys())