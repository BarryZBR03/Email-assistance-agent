import sys
import types

import pytest

from email_summary_agent.email_classification import classify_email, create_classification_chain, create_llm_client
from email_summary_agent.email_fetcher import EmailRecord


class FakeChain:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.inputs = None

    def invoke(self, inputs):
        self.inputs = inputs
        if self.error:
            raise self.error
        return self.content


class FakeModel:
    def __init__(self):
        self.piped = []

    def __ror__(self, previous):
        self.piped.append(previous)
        return self


class FakeParser:
    def __ror__(self, previous):
        return (previous, self)


def record():
    return EmailRecord(
        email_id="123",
        subject="Quarterly update",
        sender="boss@example.com",
        date="Sat, 13 Jun 2026 19:45:22 +0000",
        body="Please review the quarterly update.",
    )


def test_create_classification_chain_builds_langchain_pipeline(monkeypatch):
    fake_parser = FakeParser()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            FakePromptTemplate.messages = messages
            return "prompt"

    monkeypatch.setattr(
        "langchain_core.prompts.ChatPromptTemplate",
        FakePromptTemplate,
    )
    monkeypatch.setattr(
        "langchain_core.output_parsers.StrOutputParser",
        lambda: fake_parser,
    )

    chain = create_classification_chain(FakeModel())

    assert chain[1] is fake_parser
    assert "Allowed categories" in FakePromptTemplate.messages[0][1]


def test_classify_email_valid_json():
    chain = FakeChain('{"category":"work","confidence":0.8,"reason":"business email"}')

    result = classify_email(record(), ("work", "other"), chain)

    assert result.category == "work"
    assert result.confidence == 0.8
    assert result.reason == "business email"
    assert chain.inputs["subject"] == "Quarterly update"
    assert chain.inputs["categories"] == "work, other"


def test_classify_email_invalid_json_falls_back():
    result = classify_email(record(), ("work", "other"), FakeChain("not json"))

    assert result.category == "other"
    assert result.confidence == 0.0
    assert "Classification failed" in result.reason


def test_classify_email_unknown_category_falls_back():
    result = classify_email(
        record(),
        ("work", "other"),
        FakeChain('{"category":"finance","confidence":0.9,"reason":"invoice"}'),
    )

    assert result.category == "other"
    assert "unknown category" in result.reason


def test_classify_email_empty_response_falls_back():
    result = classify_email(record(), ("work", "other"), FakeChain(""))

    assert result.category == "other"
    assert "empty" in result.reason


def test_classify_email_api_error_falls_back():
    result = classify_email(
        record(),
        ("work", "other"),
        FakeChain(error=RuntimeError("nope")),
    )

    assert result.category == "other"
    assert "nope" in result.reason



def test_classify_email_logs_fallback_without_body(caplog):
    email_record = record()

    with caplog.at_level("INFO", logger="email_summary_agent.email_classification"):
        classify_email(email_record, ("work", "other"), FakeChain("not json"))

    messages = [record.getMessage() for record in caplog.records]
    assert any("Classifying email" in message for message in messages)
    assert any("Using fallback classification" in message for message in messages)
    assert not any(email_record.body in message for message in messages)


def install_fake_chat(monkeypatch, module_name, class_name):
    calls = []

    class FakeChat:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    module = types.ModuleType(module_name)
    setattr(module, class_name, FakeChat)
    monkeypatch.setitem(sys.modules, module_name, module)
    return calls


def test_create_llm_client_openai_compatible(monkeypatch):
    calls = install_fake_chat(monkeypatch, "langchain_openai", "ChatOpenAI")

    create_llm_client("openai_compatible", "key", "qwen-plus", "https://models.example.com/v1")

    assert calls == [{"model": "qwen-plus", "api_key": "key", "base_url": "https://models.example.com/v1", "temperature": 0}]


def test_create_llm_client_anthropic(monkeypatch):
    calls = install_fake_chat(monkeypatch, "langchain_anthropic", "ChatAnthropic")

    create_llm_client("anthropic", "key", "claude-sonnet-4-20250514", "")

    assert calls == [{"model": "claude-sonnet-4-20250514", "api_key": "key", "temperature": 0}]


def test_create_llm_client_google(monkeypatch):
    calls = install_fake_chat(monkeypatch, "langchain_google_genai", "ChatGoogleGenerativeAI")

    create_llm_client("google", "key", "gemini-2.5-pro", "")

    assert calls == [{"model": "gemini-2.5-pro", "api_key": "key", "temperature": 0}]


def test_create_llm_client_rejects_unknown_provider():
    with pytest.raises(RuntimeError, match="Unsupported LLM provider"):
        create_llm_client("unknown", "key", "model", "")
