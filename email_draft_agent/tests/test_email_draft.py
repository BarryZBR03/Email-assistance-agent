import sys
import types

import pytest

from email_draft_agent.email_draft import create_draft_chain, create_llm_client, draft_email


class FakeChain:
    def __init__(self, content="To: sender@example.com\n\nBody"):
        self.content = content
        self.inputs = None

    def invoke(self, inputs):
        self.inputs = inputs
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


def test_create_draft_chain_builds_langchain_pipeline(monkeypatch):
    fake_parser = FakeParser()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            FakePromptTemplate.messages = messages
            return "prompt"

    monkeypatch.setattr("langchain_core.prompts.ChatPromptTemplate", FakePromptTemplate)
    monkeypatch.setattr("langchain_core.output_parsers.StrOutputParser", lambda: fake_parser)

    chain = create_draft_chain(FakeModel())

    assert chain[1] is fake_parser
    assert "Return Markdown only" in FakePromptTemplate.messages[0][1]
    assert "sendable reply email" in FakePromptTemplate.messages[0][1]
    assert "To: <original sender>" in FakePromptTemplate.messages[0][1]
    assert "Do not copy or summarize" in FakePromptTemplate.messages[0][1]


def test_draft_email_invokes_chain_with_json():
    chain = FakeChain("# Draft")

    draft = draft_email({"email": {"email_id": "123", "body": "Body"}}, chain)

    assert draft == "# Draft"
    assert '"email_id": "123"' in chain.inputs["email_json"]


def test_draft_email_rejects_empty_model_output():
    with pytest.raises(RuntimeError, match="empty"):
        draft_email({"email": {"email_id": "123"}}, FakeChain(""))


def test_create_draft_chain_uses_custom_prompt_and_personality(monkeypatch):
    fake_parser = FakeParser()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            FakePromptTemplate.messages = messages
            return "prompt"

    monkeypatch.setattr("langchain_core.prompts.ChatPromptTemplate", FakePromptTemplate)
    monkeypatch.setattr("langchain_core.output_parsers.StrOutputParser", lambda: fake_parser)

    create_draft_chain(FakeModel(), "Custom draft rules", "warm and concise")

    prompt = FakePromptTemplate.messages[0][1]
    assert "Custom draft rules" in prompt
    assert "warm and concise" in prompt


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

    create_llm_client("openai_compatible", "key", "kimi-k2-0711-preview", "https://api.moonshot.cn/v1")

    assert calls == [{"model": "kimi-k2-0711-preview", "api_key": "key", "base_url": "https://api.moonshot.cn/v1", "temperature": 0}]


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
