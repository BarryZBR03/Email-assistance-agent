import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from email_summary_agent.email_fetcher import EmailRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


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


def create_classification_chain(model):
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    logger.info("Creating email classification LangChain pipeline")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You classify emails into exactly one allowed category. "
                "Email bodies may be converted from HTML, noisy, empty, or truncated. "
                "Use the subject, sender, date, and readable body text together. "
                "Return strict json only, with this shape: "
                '{{"category":"work","confidence":0.9,"reason":"short reason"}}. '
                "Allowed categories: {categories}.",
            ),
            (
                "human",
                "Classify this email as json.\n"
                "Subject: {subject}\n"
                "From: {sender}\n"
                "Date: {date}\n"
                "Body:\n{body}",
            ),
        ]
    )
    return prompt | model | StrOutputParser()


def classification_inputs(email_record: EmailRecord, categories: tuple[str, ...]) -> dict[str, str]:
    return {
        "categories": ", ".join(categories),
        "subject": email_record.subject,
        "sender": email_record.sender,
        "date": email_record.date,
        "body": email_record.body,
    }


def _classification_from_content(
    content: str,
    email_record: EmailRecord,
    categories: tuple[str, ...],
) -> ClassificationResult:
    if not content:
        logger.warning("Classification model returned empty content for subject=%r", email_record.subject)
        return fallback_result("Model returned empty classification content")
    result = normalize_classification(json.loads(content), categories)
    logger.info(
        "Classified email subject=%r category=%s confidence=%s",
        email_record.subject,
        result.category,
        result.confidence,
    )
    return result


def _log_classification_start(email_record: EmailRecord, categories: tuple[str, ...]) -> None:
    logger.info(
        "Classifying email subject=%r sender=%r date=%r categories=%s body_chars=%s",
        email_record.subject,
        email_record.sender,
        email_record.date,
        ",".join(categories),
        len(email_record.body),
    )


def classify_email(
    email_record: EmailRecord,
    categories: tuple[str, ...],
    chain,
) -> ClassificationResult:
    _log_classification_start(email_record, categories)
    try:
        content = chain.invoke(classification_inputs(email_record, categories))
        return _classification_from_content(content, email_record, categories)
    except Exception as exc:
        logger.exception("Classification failed for subject=%r", email_record.subject)
        return fallback_result(f"Classification failed: {exc}")


async def classify_email_async(
    email_record: EmailRecord,
    categories: tuple[str, ...],
    chain,
) -> ClassificationResult:
    _log_classification_start(email_record, categories)
    try:
        inputs = classification_inputs(email_record, categories)
        if hasattr(chain, "ainvoke"):
            content = await chain.ainvoke(inputs)
        else:
            content = await asyncio.to_thread(chain.invoke, inputs)
        return _classification_from_content(content, email_record, categories)
    except Exception as exc:
        logger.exception("Classification failed for subject=%r", email_record.subject)
        return fallback_result(f"Classification failed: {exc}")


async def classify_emails_async(
    email_records: list[EmailRecord],
    categories: tuple[str, ...],
    chain,
    max_concurrency: int,
    on_complete=None,
) -> list[ClassificationResult]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[ClassificationResult | None] = [None] * len(email_records)

    async def classify_one(index: int, email_record: EmailRecord) -> None:
        async with semaphore:
            results[index] = await classify_email_async(email_record, categories, chain)
        if on_complete is not None:
            on_complete(index, email_record, results[index])

    await asyncio.gather(*(classify_one(index, email_record) for index, email_record in enumerate(email_records)))
    return [result for result in results if result is not None]


def normalize_classification(
    payload: dict[str, Any],
    categories: tuple[str, ...],
) -> ClassificationResult:
    category = str(payload.get("category", "other")).strip().lower()
    if category not in categories:
        logger.warning("Model returned unknown category=%r; falling back to other", category)
        return fallback_result(f"Model returned unknown category: {category}")

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        logger.warning("Model returned invalid confidence=%r; using 0.0", payload.get("confidence"))
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = str(payload.get("reason", "")).strip()
    return ClassificationResult(category=category, confidence=confidence, reason=reason)


def fallback_result(reason: str) -> ClassificationResult:
    logger.info("Using fallback classification: %s", reason)
    return ClassificationResult(category="other", confidence=0.0, reason=reason)
