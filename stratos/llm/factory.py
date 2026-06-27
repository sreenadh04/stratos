# stratos/llm/factory.py
"""
Factory for creating LLM provider instances.
Supports provider switching, batch processing, and A/B testing.
"""
from typing import Optional, List, Dict, Any
import asyncio
import random
from stratos.llm.providers import LLMProvider, GroqProvider, GeminiProvider
from stratos.config import settings
from stratos.logging_config import get_logger
from stratos.retry import with_retry

logger = get_logger("llm.factory")


class LLMFactory:
    """Factory for LLM providers with A/B testing support."""
    
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
            provider_name = getattr(settings, "llm_provider", cls._default_provider)
        
        provider_class = cls._providers.get(provider_name.lower())
        if provider_class is None:
            raise ValueError(f"Unknown LLM provider: {provider_name}")
        
        # Check API key
        if provider_name.lower() == "groq" and not settings.groq_api_key:
            logger.warning("⚠️ Groq API key missing, falling back to Gemini")
            provider_class = cls._providers["gemini"]
        elif provider_name.lower() == "gemini" and not settings.gemini_api_key:
            logger.warning("⚠️ Gemini API key missing, falling back to Groq")
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
    
    # ============================================================
    # #12: BATCH LLM PROCESSING
    # ============================================================
    @classmethod
    async def batch_generate(
        cls,
        prompts: List[str],
        provider_name: Optional[str] = None,
        **kwargs,
    ) -> List[str]:
        """
        Process multiple prompts in parallel.
        
        Args:
            prompts: List of prompts to process
            provider_name: Optional provider name (defaults to configured)
            **kwargs: Additional arguments passed to generate()
        
        Returns:
            List of responses (in the same order as prompts)
        
        Usage:
            responses = await LLMFactory.batch_generate(
                ["Prompt 1", "Prompt 2", "Prompt 3"],
                temperature=0.7
            )
        """
        provider = cls.get_provider(provider_name)
        
        tasks = [
            provider.generate(prompt=prompt, **kwargs)
            for prompt in prompts
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results - handle errors
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch generation failed for prompt {i+1}: {result}")
                responses.append(None)
            else:
                responses.append(result)
        
        return responses
    
    # ============================================================
    # #17: A/B TESTING
    # ============================================================
    @classmethod
    def get_provider_for_experiment(
        cls,
        experiment_name: str,
        variants: Dict[str, float],
    ) -> LLMProvider:
        """
        Get a provider based on A/B testing weights.
        
        Args:
            experiment_name: Name of the experiment
            variants: Dict of {provider_name: weight}
                     e.g., {"groq": 0.5, "gemini": 0.5}
        
        Returns:
            Selected LLMProvider instance
        
        Usage:
            provider = LLMFactory.get_provider_for_experiment(
                "prompt_version_2",
                {"groq": 0.7, "gemini": 0.3}
            )
        """
        # Choose variant based on weights
        provider_names = list(variants.keys())
        weights = list(variants.values())
        selected = random.choices(provider_names, weights=weights, k=1)[0]
        
        logger.info(
            f"Experiment '{experiment_name}' selected provider: {selected}",
            extra={"experiment": experiment_name, "provider": selected}
        )
        
        return cls.get_provider(selected)
    
    @classmethod
    async def generate_with_variant(
        cls,
        prompt: str,
        experiment_name: str,
        variants: Dict[str, float],
        **kwargs,
    ) -> tuple[str, str]:
        """
        Generate a response with A/B testing, returning the provider used.
        
        Args:
            prompt: The prompt to process
            experiment_name: Name of the experiment
            variants: Dict of {provider_name: weight}
            **kwargs: Additional arguments passed to generate()
        
        Returns:
            Tuple of (response, provider_name)
        """
        provider = cls.get_provider_for_experiment(experiment_name, variants)
        response = await provider.generate(prompt=prompt, **kwargs)
        return response, provider.get_provider_name()
    
    # ============================================================
    # #7: MULTI-SOURCE SUPPORT (for future extension)
    # ============================================================
    @classmethod
    def get_provider_for_source(cls, source_type: str) -> LLMProvider:
        """
        Get a provider based on source type (blog, github, linkedin, etc.)
        
        Args:
            source_type: Type of source (blog, github, linkedin, twitter)
        
        Returns:
            LLMProvider instance
        """
        # Map source types to provider preferences
        source_provider_map = {
            "blog": "groq",
            "github": "groq",
            "linkedin": "gemini",
            "twitter": "gemini",
            "rss": "groq",
        }
        
        provider_name = source_provider_map.get(source_type.lower(), "groq")
        return cls.get_provider(provider_name)