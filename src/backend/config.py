"""
Configuration module for Terra Qualifier Agent.

This module handles:
- Environment variables loading
- LLM provider configuration
- Business rules constants
"""

import os
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class LLMProvider(str, Enum):
    """Available LLM providers."""
    GROQ = "groq"
    GEMINI = "gemini"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.GROQ
    groq_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-70b-versatile"
    gemini_model: str = "gemini-1.5-flash"
    temperature: float = 0.3
    max_tokens: int = 2000
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # MLflow Configuration
    mlflow_tracking_uri: str = "./mlflow"
    mlflow_experiment_name: str = "terra-qualifier"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


# Business Rules Constants
ALLOWED_BAIRROS = [
    "Centro",
    "Itacorubi",
    "Campeche",
    "Jurerê Internacional"
]

BAIRRO_FOCUS = {
    "Centro": "Studios e Comercial",
    "Itacorubi": "Público universitário e tech",
    "Campeche": "Rentabilidade de curto prazo/Airbnb",
    "Jurerê Internacional": "Luxo e alto padrão"
}

CIDADE_ALVO = "Florianópolis"

FALLBACK_MAP_URL = "https://www.google.com/maps/place/Florianópolis,+SC"

# Validation Ranges
MIN_LAND_SIZE_M2 = 50
MAX_LAND_SIZE_M2 = 10000
MIN_PRICE_BRL = 50000
MAX_PRICE_BRL = 50000000


def get_llm():
    """
    Factory function to get the appropriate LLM instance based on configuration.
    
    Returns:
        BaseChatModel: Configured LLM instance (Groq or Gemini)
    
    Raises:
        ValueError: If LLM provider is not configured properly
    """
    provider = settings.llm_provider
    
    if provider == LLMProvider.GROQ:
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY not found in environment variables. "
                "Get your free key at: https://console.groq.com/"
            )
        
        from langchain_groq import ChatGroq
        
        return ChatGroq(
            model=settings.groq_model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            groq_api_key=settings.groq_api_key
        )
    
    elif provider == LLMProvider.GEMINI:
        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY not found in environment variables. "
                "Get your free key at: https://aistudio.google.com/app/apikey"
            )
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            google_api_key=settings.google_api_key
        )
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")