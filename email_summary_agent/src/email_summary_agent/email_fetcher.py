import email
import imaplib
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from html import unescape
from html.parser import HTMLParser
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailRecord:
    email_id: str
    subject: str
    sender: str
    date: str
    body: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""

    chunks = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            chunks.append(text.decode(charset or "utf-8", errors="ignore"))
        else:
            chunks.append(text)
    return "".join(chunks)


def imap_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def send_imap_id(mail) -> None:
    imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")
    client_id = {
        "name": "program-learning-labs",
        "version": "1.0",
        "vendor": "local-python-imaplib",
    }
    id_payload = "(" + " ".join(
        f"{imap_string(key)} {imap_string(value)}" for key, value in client_id.items()
    ) + ")"

    status, data = mail._simple_command("ID", id_payload)
    if status != "OK":
        raise RuntimeError(f"Could not send IMAP ID command: {status} {data}")
    logger.debug("IMAP ID command sent")


def build_search_args(
    email_status: str,
    recent_days: int,
    allowed_senders: Iterable[str] = (),
    today: date | None = None,
) -> list[str]:
    current_date = today or date.today()
    since_date = current_date - timedelta(days=recent_days - 1)
    search_args = ["SINCE", since_date.strftime("%d-%b-%Y")]

    if email_status == "seen":
        search_args.insert(0, "SEEN")
    elif email_status == "unseen":
        search_args.insert(0, "UNSEEN")

    senders = tuple(allowed_senders)
    if len(senders) == 1:
        search_args.extend(["FROM", senders[0]])

    return search_args


class HtmlTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head", "title"}:
            self._skip_depth += 1
        elif tag in {"br", "p", "div", "tr", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head", "title"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "tr", "li"}:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        text = unescape(" ".join(self._parts))
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(value: str) -> str:
    parser = HtmlTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")


def extract_plain_text_body(msg: Message) -> str:
    if msg.is_multipart():
        plain_parts = []
        html_parts = []
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(decode_payload(part))
            elif content_type == "text/html":
                html_parts.append(html_to_text(decode_payload(part)))
        return "".join(plain_parts).strip() or "\n".join(html_parts).strip()

    body = decode_payload(msg)
    if msg.get_content_type() == "text/html":
        return html_to_text(body)
    return body.strip()


def email_record_from_bytes(raw_email: bytes, email_id: str = "") -> EmailRecord:
    msg = email.message_from_bytes(raw_email)
    return EmailRecord(
        email_id=email_id,
        subject=decode_mime_header(msg["Subject"]),
        sender=msg["From"] or "",
        date=msg["Date"] or "",
        body=extract_plain_text_body(msg)[:1000],
    )


def fetch_emails(config, imap_factory=imaplib.IMAP4_SSL) -> list[EmailRecord]:
    logger.info("Connecting to IMAP server %s:%s", config.imap_host, config.imap_port)
    try:
        mail = imap_factory(config.imap_host, config.imap_port)
        logger.info("Logging in to IMAP server as %s", config.imap_user)
        mail.login(config.imap_user, config.imap_auth_code)
        logger.info("IMAP login succeeded")
        send_imap_id(mail)
    except OSError as exc:
        logger.exception("Could not connect to IMAP server %s:%s", config.imap_host, config.imap_port)
        raise RuntimeError(
            f"Could not connect to {config.imap_host}:{config.imap_port}: {exc}"
        ) from exc
    except imaplib.IMAP4.error as exc:
        logger.exception("Could not log in to IMAP server")
        raise RuntimeError(
            "Could not log in. Check that IMAP/SMTP is enabled and that "
            "IMAP_AUTH_CODE is the mailbox authorization/app password."
        ) from exc

    try:
        logger.info("Selecting INBOX")
        status, data = mail.select("INBOX")
        if status != "OK":
            server_message = b" ".join(data).decode("utf-8", errors="ignore")
            if "Unsafe Login" in server_message:
                logger.error("IMAP server rejected session as unsafe login")
                raise RuntimeError(
                    "The mail provider rejected this IMAP session as an unsafe login. "
                    "Log in to the mailbox web UI, make sure IMAP/SMTP service is enabled, "
                    "regenerate the authorization/app password if needed, then update "
                    "IMAP_AUTH_CODE."
                )
            logger.error("Could not select INBOX: status=%s data=%s", status, data)
            raise RuntimeError(f"Could not select INBOX: {status} {data}")
        logger.info("INBOX selected")

        search_args = build_search_args(
            config.email_status,
            config.recent_days,
            config.allowed_senders,
        )
        logger.info("Searching mailbox with criteria: %s", search_args)
        status, data = mail.uid("SEARCH", None, *search_args)
        if status != "OK":
            logger.error("Could not search mailbox: status=%s data=%s", status, data)
            raise RuntimeError(f"Could not search mailbox: {status} {data}")

        mail_ids = data[0].split()
        logger.info("Mailbox search returned %s message uids", len(mail_ids))
        records = []
        for index, mail_id in enumerate(mail_ids, start=1):
            logger.info("Fetching message %s/%s uid=%r", index, len(mail_ids), mail_id)
            status, msg_data = mail.uid("FETCH", mail_id, "(BODY.PEEK[])")
            if status != "OK":
                logger.warning("Could not fetch message uid=%r status=%s", mail_id, status)
                continue

            raw_email = next(
                (item[1] for item in msg_data if isinstance(item, tuple) and len(item) > 1),
                None,
            )
            if not raw_email:
                logger.warning("Fetched message uid=%r did not include raw email bytes", mail_id)
                continue

            email_id = mail_id.decode("ascii", errors="ignore")
            record = email_record_from_bytes(raw_email, email_id=email_id)
            sender_email = parseaddr(record.sender)[1].lower()
            if config.allowed_senders and sender_email not in config.allowed_senders:
                logger.info(
                    "Skipping message uid=%r from sender=%s due to allowed sender filter",
                    mail_id,
                    sender_email,
                )
                continue

            logger.info(
                "Fetched email uid=%r subject=%r sender=%r date=%r body_chars=%s",
                email_id,
                record.subject,
                record.sender,
                record.date,
                len(record.body),
            )
            records.append(record)
        logger.info("Finished fetching emails: usable_records=%s", len(records))
        return records
    finally:
        try:
            logger.info("Logging out from IMAP server")
            mail.logout()
            logger.info("IMAP logout completed")
        except Exception:
            logger.exception("IMAP logout failed")
