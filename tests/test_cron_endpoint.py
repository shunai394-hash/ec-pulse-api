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
    patrol_workflow = (root / ".github/workflows/patrol.yml").read_text(encoding="utf-8")
    smoke_script = (root / "scripts/production_smoke.py").read_text(encoding="utf-8")

    production_url = "https://ec-pulse-api-one.vercel.app"
    assert production_url in readme
    assert production_url in monitor_workflow
    assert production_url in smoke_workflow
    assert production_url in patrol_workflow
    assert production_url in smoke_script
    stale_urls = (
        "https://ec-pulse-api.vercel.app",
        "https://ec-pulse-api-two.vercel.app",
    )
    for source in (readme, monitor_workflow, smoke_workflow, patrol_workflow, smoke_script):
        assert all(stale not in source for stale in stale_urls)


def test_customer_discovery_workflow_is_safe_and_reproducible():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / "examples/github-actions/daily-discovery.yml").read_text(encoding="utf-8")
    guide = (root / "docs/customer-automation-playbook.md").read_text(encoding="utf-8")
    monitor = (root / ".github/workflows/monitor-cron.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "timeout-minutes: 5" in workflow
    assert "secrets.EC_PULSE_API_KEY" in workflow
    assert "secrets.EC_PULSE_BASE_URL" in workflow
    assert "retention-days: 7" in workflow
    assert "/v1/products/search" in workflow
    assert "/v1/orders" not in workflow
    assert "checkout" not in workflow.lower()
    assert "examples/github-actions/daily-discovery.yml" in guide
    assert "must not trigger a purchase or listing publication" in guide
    assert "CRON_SECRET is not configured" in monitor
    assert "exit 0" in monitor
