from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from pydantic import BaseModel, Field

from services.agent_runner import AgentRunError, prepare_summary_agent, run_draft_agent, run_summary_agent_for_task, send_saved_draft
from storage import task_store


router = APIRouter()


class DraftRequest(BaseModel):
    email_ids: list[str] = Field(min_length=1)


class DraftUpdateRequest(BaseModel):
    markdown: str = Field(min_length=1)


class SendDraftRequest(BaseModel):
    approved: bool = False


def _agent_error(exc: AgentRunError) -> HTTPException:
    detail = {"code": exc.code, "message": str(exc)}
    details = {}
    if exc.stdout:
        details["stdout"] = exc.stdout[-4000:]
    if exc.stderr:
        details["stderr"] = exc.stderr[-4000:]
    if details:
        detail["details"] = details
    status_code = 400 if exc.code in {"missing_config", "llm_api_key_missing", "imap_login_failed", "missing_email_ids", "smtp_send_failed"} else 500
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/trash/tasks")
def list_trash_tasks() -> list[dict[str, object]]:
    return task_store.list_trashed_tasks()


@router.post("/trash/tasks/{task_id}/{trash_id}/restore")
def restore_trash_task(task_id: str, trash_id: str) -> dict[str, object]:
    try:
        result = task_store.restore_trashed_task(task_id, trash_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"code": "task_restore_conflict", "message": str(exc)}) from exc
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail={"code": "trash_task_not_found", "message": f"Trash task not found: {task_id}/{trash_id}"})
    return result


@router.delete("/trash/tasks/{task_id}/{trash_id}")
def permanently_delete_trash_task(task_id: str, trash_id: str) -> dict[str, object]:
    try:
        result = task_store.permanently_delete_trashed_task(task_id, trash_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"code": "trash_delete_conflict", "message": str(exc)}) from exc
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail={"code": "trash_task_not_found", "message": f"Trash task not found: {task_id}/{trash_id}"})
    return result


@router.post("/tasks/summary")
def create_summary_task(background_tasks: BackgroundTasks) -> dict[str, object]:
    try:
        response = prepare_summary_agent()
    except AgentRunError as exc:
        raise _agent_error(exc) from exc
    background_tasks.add_task(run_summary_agent_for_task, str(response["task_id"]))
    return response


@router.get("/tasks")
def list_tasks() -> list[dict[str, object]]:
    return task_store.list_tasks()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, object]:
    try:
        result = task_store.move_task_to_trash(task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"code": "task_delete_conflict", "message": str(exc)}) from exc
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail={"code": "task_not_found", "message": f"Task not found: {task_id}"})
    return result


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    metadata = task_store.task_metadata(task_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found", "message": f"Task not found: {task_id}"})
    return metadata


@router.get("/tasks/{task_id}/progress")
def get_progress(task_id: str) -> dict[str, object]:
    return task_store.read_progress(task_id)


@router.get("/tasks/{task_id}/draft-progress")
def get_draft_progress(task_id: str) -> dict[str, object]:
    return task_store.read_progress(task_id, draft=True)


@router.get("/tasks/{task_id}/summary")
def get_summary(task_id: str) -> Response:
    markdown = task_store.read_summary_markdown(task_id)
    if markdown is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "summary_not_found", "message": f"Summary not found for task: {task_id}"},
        )
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get("/tasks/{task_id}/emails")
def get_emails(task_id: str) -> dict[str, list[dict[str, str]]]:
    emails = task_store.list_emails_for_task(task_id)
    if not emails:
        raise HTTPException(
            status_code=404,
            detail={"code": "emails_not_found", "message": f"Classified emails not found for task: {task_id}"},
        )
    return emails


@router.get("/tasks/{task_id}/emails/{email_id}")
def get_email(task_id: str, email_id: str) -> dict[str, object]:
    email = task_store.read_email_for_task(task_id, email_id)
    if email is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "email_not_found", "message": f"Email not found for task/email: {task_id}/{email_id}"},
        )
    return email


@router.post("/tasks/{task_id}/drafts")
def create_drafts(task_id: str, request: DraftRequest) -> dict[str, object]:
    try:
        drafts = run_draft_agent(task_id, request.email_ids)
    except AgentRunError as exc:
        raise _agent_error(exc) from exc
    return {"task_id": task_id, "drafts": drafts}


@router.get("/tasks/{task_id}/drafts")
def get_drafts(task_id: str) -> list[dict[str, str]]:
    return task_store.list_drafts(task_id, include_content=True)

@router.put("/tasks/{task_id}/drafts/{email_id}")
def update_draft(task_id: str, email_id: str, request: DraftUpdateRequest) -> dict[str, str]:
    draft = task_store.update_draft_markdown(task_id, email_id, request.markdown)
    if draft is None:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "message": f"Draft not found for task/email: {task_id}/{email_id}"})
    return draft


@router.post("/tasks/{task_id}/drafts/{email_id}/send")
def send_draft(task_id: str, email_id: str, request: SendDraftRequest) -> dict[str, object]:
    if not request.approved:
        raise HTTPException(status_code=400, detail={"code": "send_not_approved", "message": "User approval is required before sending email."})
    if task_store.read_draft_markdown(task_id, email_id) is None:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "message": f"Draft not found for task/email: {task_id}/{email_id}"})
    try:
        return send_saved_draft(task_id, email_id)
    except AgentRunError as exc:
        raise _agent_error(exc) from exc

