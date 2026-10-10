import logging

import psycopg
from fastapi.testclient import TestClient


def test_health_database_failure_is_correlated_but_does_not_leak_details(monkeypatch, caplog):
    from app import main
    from app.services import monitor_store

    monkeypatch.setattr(monitor_store, "_db_url", lambda: "postgresql://test/test")

    def fail_connect(*args, **kwargs):
        raise psycopg.ProgrammingError("simulated database protocol failure")

    monkeypatch.setattr(main.psycopg, "connect", fail_connect)
    caplog.set_level(logging.ERROR, logger="app.main")

    response = TestClient(main.app).get(
        "/health",
        headers={"X-Request-ID": "health-regression-test"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "degraded",
        "database": "unavailable",
    }
    assert "health-regression-test" in caplog.text
    assert "ProgrammingError" in caplog.text
    assert "simulated database protocol failure" not in response.text


def test_database_url_strips_whitespace_and_rejects_placeholder(monkeypatch):
    from app.services import monitor_store

    monkeypatch.setenv("DATABASE_URL", "  postgresql://user:pass@example.test/db  \n")
    assert monitor_store._db_url() == "postgresql://user:pass@example.test/db"

    monkeypatch.setenv("DATABASE_URL", "*********************")
    try:
        monitor_store._db_url()
    except RuntimeError as exc:
        assert "must be a PostgreSQL URI" in str(exc)
    else:
        raise AssertionError("Invalid DATABASE_URL must fail with a clear configuration error")
