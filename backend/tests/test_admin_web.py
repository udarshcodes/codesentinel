from fastapi.testclient import TestClient
import main


def test_admin_html_is_served_on_api_origin_without_altering_api_root(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<html><div id="root"></div></html>')
    monkeypatch.setattr(main, "ADMIN_WEB_DIR", str(tmp_path))
    client = TestClient(main.app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/").json() == {"message": "System Operational"}
    assert client.get("/api/v1/admin/telemetry").status_code == 401
    (tmp_path / "logo.jpg").write_bytes(b"test-logo")
    assert client.get("/logo.jpg").content == b"test-logo"
