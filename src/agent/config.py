"""Shared LLM configuration for DBVoyager agents."""

import os
from functools import cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()


@cache
def create_deepseek_llm() -> ChatOpenAI:
    """Create the shared DeepSeek Flash chat model from environment settings."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required")
    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0,
        max_tokens=160,
        extra_body={"thinking": {"type": "disabled"}},
    )
