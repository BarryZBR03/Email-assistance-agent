"""Import-safe modules for fetching, classifying, and storing email data."""

from email_summary_agent.email_classification import ClassificationResult
from email_summary_agent.email_fetcher import EmailRecord

__all__ = ["ClassificationResult", "EmailRecord"]
