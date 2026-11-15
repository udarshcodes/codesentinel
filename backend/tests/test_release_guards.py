from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from agents.pr_author import stale_lockfiles
from api.routes import _validate_admin_origin


def test_nested_dependency_updates_require_their_lock(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web/package-lock.json").write_text("{}")
    assert stale_lockfiles(str(tmp_path), {"web/package.json"}) == ["web/package-lock.json"]
    assert stale_lockfiles(str(tmp_path), {"web/package.json", "web/package-lock.json"}) == []
    assert stale_lockfiles(str(tmp_path), {"web/app.js"}) == []


def test_admin_cross_site_mutation_requires_trusted_origin():
    def request(origin):
        return Request({"type": "http", "scheme": "https", "server": ("api.example", 443),
                        "path": "/", "headers": [(b"origin", origin.encode())]})
    with patch.dict("os.environ", {"CORS_ORIGINS": "https://app.example"}):
        _validate_admin_origin(request("https://app.example"))
        with pytest.raises(HTTPException) as error:
            _validate_admin_origin(request("https://attacker.example"))
        assert error.value.status_code == 403
