import asyncio

import pandas as pd

from src.application.captcha_queue import NEEDS_CAPTCHA, captcha_held_job_ids, park_for_captcha, requeue_after_captcha
from src.agent.tools import _worker_application_status, get_jobs, update_job_status


def test_captcha_job_is_held_then_requeued_at_the_tail(tmp_path, monkeypatch):
    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([
        {"id": "1", "title": "First", "application_status": "Not Applied", "fetched_at": "2026-08-01T00:00:00Z"},
        {"id": "2", "title": "CAPTCHA", "application_status": "Not Applied", "fetched_at": "2026-08-02T00:00:00Z"},
        {"id": "3", "title": "Third", "application_status": "Not Applied", "fetched_at": "2026-08-03T00:00:00Z"},
    ]).to_excel(workbook, index=False)
    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", workbook)

    park_for_captcha("2", url="https://jobs.example.com/apply/2", workbook_path=workbook)
    held = pd.read_excel(workbook, dtype=str)
    assert held.loc[held.id == "2", "application_status"].iloc[0] == NEEDS_CAPTCHA
    assert [job["id"] for job in get_jobs.invoke({"filters": ["Not Applied"]})] == ["1", "3"]

    assert requeue_after_captcha("2", workbook_path=workbook)
    assert [job["id"] for job in get_jobs.invoke({"filters": ["Not Applied"]})] == ["1", "3", "2"]


def test_worker_captcha_result_is_distinct_from_a_failure():
    assert _worker_application_status("status: needs_captcha\nreason: captcha_required") == "needs_captcha"
    assert _worker_application_status("status: failed\nreason: blocked") == "failed"


def test_captcha_held_job_cannot_be_overwritten_as_failed(tmp_path, monkeypatch):
    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([{"id": "7", "application_status": NEEDS_CAPTCHA}]).to_excel(workbook, index=False)
    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", workbook)

    result = update_job_status.invoke({"job_id": "7", "status": "Failed"})

    assert "cannot be marked Failed" in result
    assert pd.read_excel(workbook, dtype=str).loc[0, "application_status"] == NEEDS_CAPTCHA


def test_telegram_captcha_done_requeues_the_held_job(tmp_path, monkeypatch):
    from src.application import captcha_queue
    from src.notifications.telegram_service import TelegramConfig, TelegramService
    from src.runtime.services import AgentRuntime

    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([{"id": "42", "application_status": NEEDS_CAPTCHA}]).to_excel(workbook, index=False)
    monkeypatch.setattr(captcha_queue, "JOBS_FILE", workbook)

    class FakeTelegram(TelegramService):
        def __init__(self, config, runtime):
            super().__init__(config, runtime)
            self.messages = []

        async def _send_direct(self, text, keyboard=None):
            self.messages.append(text)

        async def _safe_answer_callback(self, callback_id):
            return None

    async def scenario():
        runtime = AgentRuntime()
        service = FakeTelegram(TelegramConfig("test-token", 42, True), runtime)
        await service._handle_callback({"id": "callback", "data": "captcha:42"})
        assert "moved to the end" in service.messages[0]
        assert "CAPTCHA-held application was requeued" in await runtime.inputs.messages.get()

    asyncio.run(scenario())
    assert pd.read_excel(workbook, dtype=str).loc[0, "application_status"] == "Not Applied"


def test_telegram_text_captcha_done_is_a_fallback_for_a_missing_inline_button(tmp_path, monkeypatch):
    """A plain text confirmation must not be sent to the manager model."""
    from src.application import captcha_queue
    from src.notifications.telegram_service import TelegramConfig, TelegramService
    from src.runtime.services import AgentRuntime

    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([{"id": "42", "application_status": NEEDS_CAPTCHA}]).to_excel(workbook, index=False)
    monkeypatch.setattr(captcha_queue, "JOBS_FILE", workbook)

    class FakeTelegram(TelegramService):
        def __init__(self, config, runtime):
            super().__init__(config, runtime)
            self.messages = []

        async def _send_direct(self, text, keyboard=None):
            self.messages.append(text)

    async def scenario():
        runtime = AgentRuntime()
        service = FakeTelegram(TelegramConfig("test-token", 42, True), runtime)
        await service._handle_message("Captcha done")
        assert "moved to the end" in service.messages[0]
        assert "CAPTCHA-held application was requeued" in await runtime.inputs.messages.get()

    asyncio.run(scenario())
    assert pd.read_excel(workbook, dtype=str).loc[0, "application_status"] == "Not Applied"


def test_text_captcha_done_requires_a_job_id_when_multiple_jobs_are_held(tmp_path):
    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([
        {"id": "42", "application_status": NEEDS_CAPTCHA},
        {"id": "43", "application_status": NEEDS_CAPTCHA},
    ]).to_excel(workbook, index=False)

    assert captcha_held_job_ids(workbook_path=workbook) == ["42", "43"]


def test_requeued_captcha_job_sorts_with_legacy_naive_timestamps(tmp_path, monkeypatch):
    """A new UTC requeue timestamp must remain sortable with older Excel rows."""
    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame([
        {"id": "1", "application_status": "Not Applied", "fetched_at": "2026-08-01 00:00:00"},
        {"id": "2", "application_status": NEEDS_CAPTCHA, "fetched_at": "2026-08-02 00:00:00"},
    ]).to_excel(workbook, index=False)
    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", workbook)

    assert requeue_after_captcha("2", workbook_path=workbook)
    assert [job["id"] for job in get_jobs.invoke({"filters": ["Not Applied"]})] == ["1", "2"]
