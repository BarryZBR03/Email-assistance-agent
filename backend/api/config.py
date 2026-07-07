from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.config_store import ConfigPayload, config_status, save_config, test_imap, test_smtp


router = APIRouter(prefix="/config")


def _friendly_config_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "config_error", "message": str(exc)},
    )


@router.get("/status")
def get_config_status() -> dict[str, object]:
    return config_status()


@router.post("/save")
def save_configuration(payload: ConfigPayload) -> dict[str, object]:
    return save_config(payload)


@router.post("/test-imap")
def test_imap_configuration(payload: ConfigPayload | None = None) -> dict[str, object]:
    try:
        return test_imap(payload)
    except RuntimeError as exc:
        raise _friendly_config_error(exc) from exc


@router.post("/test-smtp")
def test_smtp_configuration(payload: ConfigPayload | None = None) -> dict[str, object]:
    try:
        return test_smtp(payload)
    except RuntimeError as exc:
        raise _friendly_config_error(exc) from exc
