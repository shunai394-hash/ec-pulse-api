from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_browser_gets_customer_landing_page():
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Turn product pages into decisions." in response.text
    assert 'href="/docs"' in response.text


def test_root_api_client_keeps_json_contract():
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "EC Pulse API"
    assert payload["docs"] == "/docs"
    assert payload["health"] == "/health"
