"""
Factory for creating LangChain chat models based on configuration.
"""

import logging
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

try:
    from langchain_anthropic import ChatAnthropic
except Exception:  # pragma: no cover - optional dependency
    ChatAnthropic = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - optional dependency
    ChatGoogleGenerativeAI = None

def get_model(model_name: str | None = None) -> Any:
    """
    Get a configured ChatModel instance.
    """
    if not model_name:
        model_name = settings.claude_model
        
    normalized = model_name.lower()
    
    if "claude" in normalized or "anthropic" in normalized:
        if ChatAnthropic is None:
            logger.warning("langchain_anthropic is not installed, trying Google...")
        elif not settings.claude_api_key:
            logger.warning("Claude API key not found, trying Google...")
        else:
            return ChatAnthropic(
                model=model_name,
                api_key=settings.claude_api_key,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens
            )

    if "gemini" in normalized or "google" in normalized:
        if ChatGoogleGenerativeAI is None:
            logger.warning("langchain_google_genai is not installed.")
        elif not settings.gemini_api_key:
            logger.warning("Gemini API key not found.")
        else:
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.gemini_api_key,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_tokens
            )

    # Fallback logic
    if settings.claude_api_key and ChatAnthropic is not None:
        return ChatAnthropic(
            model=settings.claude_model,
            api_key=settings.claude_api_key,
            temperature=settings.llm_temperature
        )
    elif settings.gemini_api_key and ChatGoogleGenerativeAI is not None:
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature
        )

    raise ValueError(
        "No usable LLM client is configured. Install langchain_anthropic or "
        "langchain_google_genai and provide matching API keys."
    )
