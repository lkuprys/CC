# -*- coding: utf-8 -*-
"""Naršyklės plėtinio API: tik šis kompiuteris, tik http(s) nuorodos."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("flask")

from api_server import FlaskServerThread  # noqa: E402


@pytest.fixture
def api():
    server = FlaskServerThread(port=0, host="127.0.0.1")
    received = []
    server.designs_received.connect(received.append)
    return server.app.test_client(), received


def post(client, body, host="127.0.0.1:5000"):
    return client.post("/api/add_designs", json=body, headers={"Host": host})


def test_foreign_host_rejected(api):
    client, received = api
    assert client.get("/api/health", headers={"Host": "evil.com:5000"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "localhost:5000"}).status_code == 200
    assert post(client, {"designs": []}, host="evil.com").status_code == 403
    assert received == []


def test_only_http_urls_pass(api):
    client, received = api
    r = post(client, {"designs": [
        {"name": "A", "url": r"\\evil\share\x.png"},
        {"name": "B", "url": "C:/Users/x.png"},
        {"name": "C", "url": "https://cdn.example.com/c.png"},
        "ne dict",
    ], "jobName": "BID-1"})
    assert r.status_code == 200 and r.json["count"] == 3
    urls = [d["url"] for d in received[0]["designs"]]
    assert urls == ["", "", "https://cdn.example.com/c.png"]
    assert received[0]["jobName"] == "BID-1"


def test_bad_json_rejected(api):
    client, received = api
    assert post(client, [1, 2]).status_code == 400
    assert received == []
