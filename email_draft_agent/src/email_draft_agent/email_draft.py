import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_llm_client(provider: str, api_key: str, model: str, base_url: str = ""):
    logger.info("Creating LLM provider=%s model=%s base_url=%s", provider, model, base_url or "provider-default")
    if provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=0,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=0,
        )
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            api_key=api_key,
            temperature=0,
        )
    raise RuntimeError("Unsupported LLM provider: " + provider)


def create_deepseek_client(api_key: str, base_url: str, model: str):
    return create_llm_client("openai_compatible", api_key, model, base_url)


DEFAULT_DRAFT_SYSTEM_PROMPT = (
    "You draft a sendable reply email from exactly one classified email JSON object. "
    "Use only the provided JSON data. Return Markdown only. "
    "Do not copy or summarize the original email as the body. "
    "Write the reply from the recipient/user back to the original sender. "
    "Use this exact format: To: <original sender>\nSubject: Re: <original subject>\nBody:\n<draft reply body>. "
    "Keep the body concise, professional, and directly responsive to the email. "
    "Do not invent facts that are not present in the JSON; if action details are unavailable, keep the response generic."
)


def create_draft_chain(model, system_prompt: str = "", personality: str = ""):
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    logger.info("Creating email draft LangChain pipeline")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "\n\n".join(
                    part
                    for part in (
                        system_prompt.strip() or DEFAULT_DRAFT_SYSTEM_PROMPT,
                        f"Draft personality and tone: {personality.strip()}" if personality.strip() else "",
                    )
                    if part
                ),
            ),
            (
                "human",
                "Draft a sending email using only this email JSON.\n"
                "JSON:\n{email_json}",
            ),
        ]
    )
    return prompt | model | StrOutputParser()


def draft_inputs(payload: dict[str, Any]) -> dict[str, str]:
    return {"email_json": json.dumps(payload, ensure_ascii=False, indent=2)}


def _draft_from_content(content: Any) -> str:
    if not content:
        raise RuntimeError("Draft model returned empty content")
    return str(content).strip()


def draft_email(payload: dict[str, Any], chain) -> str:
    content = chain.invoke(draft_inputs(payload))
    return _draft_from_content(content)


async def draft_email_async(payload: dict[str, Any], chain) -> str:
    inputs = draft_inputs(payload)
    if hasattr(chain, "ainvoke"):
        content = await chain.ainvoke(inputs)
    else:
        content = await asyncio.to_thread(chain.invoke, inputs)
    return _draft_from_content(content)


async def draft_emails_async(
    payloads: list[dict[str, Any]],
    chain,
    max_concurrency: int,
    on_complete=None,
) -> list[str]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[str | None] = [None] * len(payloads)

    async def draft_one(index: int, payload: dict[str, Any]) -> None:
        async with semaphore:
            results[index] = await draft_email_async(payload, chain)
        if on_complete is not None:
            on_complete(index, payload, results[index])

    await asyncio.gather(*(draft_one(index, payload) for index, payload in enumerate(payloads)))
    return [result for result in results if result is not None]
