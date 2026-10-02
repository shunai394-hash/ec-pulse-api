import pytest

from app.services import patrol


@pytest.mark.asyncio
async def test_patrol_persists_final_delivery_failure_state(monkeypatch):
    monkeypatch.setattr(patrol.psycopg, "connect", lambda *_args, **_kwargs: _HealthyConn())
    monkeypatch.setattr(
        patrol,
        "search_products",
        lambda *_args, **_kwargs: _search_result(),
    )

    async def monitors():
        return {"checked": 0, "changed": 0, "failed": 0, "webhooks_delivered": 0}

    async def diagnosis(_checks, _repairs):
        return {"actions": []}

    async def send(_report):
        return False

    stored = []

    def capture_store(report):
        stored.append(report.copy())

    monkeypatch.setattr(patrol, "run_due_monitors", monitors)
    monkeypatch.setattr(patrol, "diagnose", diagnosis)
    monkeypatch.setattr(patrol, "_send_report", send)
    monkeypatch.setattr(patrol, "_store_report", capture_store)

    result = await patrol.run_patrol()

    assert result["report_delivery"]["delivered"] is False
    assert result["ok"] is False
    assert stored
    assert stored[0]["report_delivery"]["delivered"] is False
    assert stored[0]["ok"] is False
    assert stored[0]["failures"][-1]["name"] == "report-delivery"


@pytest.mark.asyncio
async def test_patrol_persists_same_final_report_returned(monkeypatch):
    monkeypatch.setattr(patrol.psycopg, "connect", lambda *_args, **_kwargs: _HealthyConn())
    monkeypatch.setattr(
        patrol,
        "search_products",
        lambda *_args, **_kwargs: _search_result(),
    )

    async def monitors():
        return {"checked": 1, "changed": 0, "failed": 0, "webhooks_delivered": 0}

    async def diagnosis(_checks, _repairs):
        return {"actions": []}

    async def send(_report):
        return True

    stored = []

    def capture_store(report):
        stored.append(report.copy())

    monkeypatch.setattr(patrol, "run_due_monitors", monitors)
    monkeypatch.setattr(patrol, "diagnose", diagnosis)
    monkeypatch.setattr(patrol, "_send_report", send)
    monkeypatch.setattr(patrol, "_store_report", capture_store)

    result = await patrol.run_patrol()

    assert stored
    assert stored[0] == result


class _HealthyConn:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return None


def _search_result():
    return {"results": [{"title": "test-product"}]}
