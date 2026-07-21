from unittest.mock import patch

from src.agent.config import create_deepseek_llm


def test_create_deepseek_llm_reuses_the_process_client(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    create_deepseek_llm.cache_clear()

    with patch("src.agent.config.ChatOpenAI") as chat_openai:
        assert create_deepseek_llm() is create_deepseek_llm()

    assert chat_openai.call_count == 1
    create_deepseek_llm.cache_clear()
