import pytest
from fastapi.testclient import TestClient

from app import main


def test_cron_monitor_endpoint_requires_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    client = TestClient(main.app)

    response = client.get("/api/cron/check-monitors")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_cron_monitor_endpoint_runs_due_monitors(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")

    async def fake_run_due_monitors():
        return {
            "checked": 2,
            "changed": 1,
            "failed": 0,
            "webhooks_delivered": 1,
        }

    monkeypatch.setattr(main, "run_due_monitors", fake_run_due_monitors)
    client = TestClient(main.app)

    response = client.get(
        "/api/cron/check-monitors",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checked"] == 2
    assert body["changed"] == 1
    assert body["failed"] == 0
    assert body["webhooks_delivered"] == 1
    assert body["checked_at"]


def test_cron_monitor_endpoint_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    client = TestClient(main.app)

    response = client.get(
        "/api/cron/check-monitors",
        headers={"Authorization": "Bearer wrong-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"

def test_automation_workflows_target_documented_production_domain():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    monitor_workflow = (root / ".github/workflows/monitor-cron.yml").read_text(encoding="utf-8")
    smoke_workflow = (root / ".github/workflows/production-smoke.yml").read_text(encoding="utf-8")

    production_url = "https://ec-pulse-api-two.vercel.app"
    assert production_url in readme
    assert production_url in monitor_workflow
    assert production_url in smoke_workflow
    assert "https://ec-pulse-api.vercel.app" not in monitor_workflow
    assert "https://ec-pulse-api.vercel.app" not in smoke_workflow

