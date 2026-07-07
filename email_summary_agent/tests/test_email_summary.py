import json

import pytest

from email_summary_agent.email_summary import (
    create_summary_chain,
    summarize_selected_email_dump,
    summary_markdown_filename,
)


class FakeChain:
    def __init__(self, content="# Summary"):
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


def write_dump(path, email_count=1):
    path.write_text(
        json.dumps(
            {
                "task_id": "task12345",
                "source_run_dir": str(path.parent),
                "categories": ["important", "personal"],
                "email_count": email_count,
                "emails": [
                    {
                        "basic_information": {"subject": "A", "category": "important"},
                        "email": {"subject": "A", "body": "Body"},
                    }
                ][:email_count],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_summary_markdown_filename_uses_task_id():
    assert summary_markdown_filename("ABC-123") == "email_summary_abc_123.md"


def test_create_summary_chain_builds_langchain_pipeline(monkeypatch):
    fake_parser = FakeParser()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            FakePromptTemplate.messages = messages
            return "prompt"

    monkeypatch.setattr("langchain_core.prompts.ChatPromptTemplate", FakePromptTemplate)
    monkeypatch.setattr("langchain_core.output_parsers.StrOutputParser", lambda: fake_parser)

    chain = create_summary_chain(FakeModel())

    assert chain[1] is fake_parser
    assert "important, work, personal, and other" in FakePromptTemplate.messages[0][1]
    assert "Return Markdown only" in FakePromptTemplate.messages[0][1]


def test_summarize_selected_email_dump_writes_markdown(tmp_path):
    dump_path = tmp_path / "selected_email_dump_task12345.json"
    write_dump(dump_path)
    chain = FakeChain("# Summary\n\n- Action")

    summary_path = summarize_selected_email_dump(dump_path, tmp_path, "task12345", chain)

    assert summary_path == tmp_path / "email_summary_task12345.md"
    assert summary_path.read_text(encoding="utf-8") == "# Summary\n\n- Action\n"
    assert chain.inputs["task_id"] == "task12345"
    assert "important" in chain.inputs["dump_json"]


def test_summarize_selected_email_dump_skips_empty_dump(tmp_path):
    dump_path = tmp_path / "selected_email_dump_task12345.json"
    write_dump(dump_path, email_count=0)
    chain = FakeChain()

    assert summarize_selected_email_dump(dump_path, tmp_path, "task12345", chain) is None
    assert chain.inputs is None


def test_summarize_selected_email_dump_rejects_empty_model_output(tmp_path):
    dump_path = tmp_path / "selected_email_dump_task12345.json"
    write_dump(dump_path)

    with pytest.raises(RuntimeError, match="empty"):
        summarize_selected_email_dump(dump_path, tmp_path, "task12345", FakeChain(""))


def test_create_summary_chain_uses_custom_system_prompt(monkeypatch):
    fake_parser = FakeParser()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            FakePromptTemplate.messages = messages
            return "prompt"

    monkeypatch.setattr("langchain_core.prompts.ChatPromptTemplate", FakePromptTemplate)
    monkeypatch.setattr("langchain_core.output_parsers.StrOutputParser", lambda: fake_parser)

    create_summary_chain(FakeModel(), "Custom summary rules")

    assert FakePromptTemplate.messages[0][1] == "Custom summary rules"
