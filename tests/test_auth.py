"""Token authentication of `mapcan serve` on a network address."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mapcan.web.app import create_app

TOKEN = "s3cret-token"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(None, cwd=tmp_path, auth_token=TOKEN))


def test_without_the_token_nothing_is_served(client):
    r = client.get("/api/meta")
    assert r.status_code == 401 and r.json()["code"] == "auth"
    assert client.get("/").status_code == 401
    assert client.get("/api/meta", headers={"Authorization": "Bearer wrong"}).status_code == 401
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws") as ws:
        ws.receive_json()


def test_the_token_in_the_address_sets_a_cookie(client):
    r = client.get(f"/?token={TOKEN}&x=1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?x=1"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/meta").status_code == 200        # the client keeps the cookie
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_bearer_header(client):
    assert client.get("/api/meta", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_local_server_needs_no_token(tmp_path):
    assert TestClient(create_app(None, cwd=tmp_path)).get("/api/meta").status_code == 200
