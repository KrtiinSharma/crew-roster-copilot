import time

import pytest
from fakes import ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from crew_roster.api import main
from crew_roster.service import duty_views, evaluate


@pytest.fixture
def client():
    main.app.dependency_overrides[main.get_llm_factory] = lambda: None
    main._hits.clear()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def sick_body():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    return {"ruleset": "dgca_current",
            "disruptions": [{"kind": "sick", "pilot_id": pid, "from_day": 3, "to_day": 4}]}


def test_health_and_rules(client):
    assert client.get("/health").json() == {"status": "ok"}
    rules = client.get("/rules").json()
    assert set(rules) == {"dgca_current", "dgca_dec2025_exemption"}
    assert rules["dgca_current"]["ft_7d"] == 2100
    assert rules["dgca_dec2025_exemption"]["night_max_landings"] == 6


def test_base_roster(client):
    view = client.get("/roster").json()
    assert view["stats"]["uncovered"] == 0 and view["stats"]["violations"] == 0
    assert len(view["duties"]) == 126 and len(view["pilots"]) == 80
    assert len(view["flights"]) == 294 and view["changes"] == []
    assert client.get("/roster", params={"ruleset": "dgca_dec2025_exemption"}).json()[
        "stats"]["duties"] == 113


def test_replan_returns_explained_changes(client):
    view = client.post("/replan", json=sick_body()).json()
    assert view["stats"]["violations"] == 0 and view["changes"]
    assert all(c["explanation"].startswith(c["duty_id"] + ":") for c in view["changes"])


def test_bad_disruption_is_422(client):
    body = {"ruleset": "dgca_current",
            "disruptions": [{"kind": "sick", "pilot_id": "NOPE", "from_day": 1, "to_day": 1}]}
    r = client.post("/replan", json=body)
    assert r.status_code == 422 and "NOPE" in r.json()["detail"]
    assert client.get("/roster", params={"ruleset": "nope"}).status_code == 422


def test_chat_needs_an_llm(client):
    body = {**sick_body(), "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/chat", json=body).status_code == 503


def test_chat_with_scripted_model_and_rate_limit(client, monkeypatch):
    model = ScriptedChatModel(script=[AIMessage(content="The roster is fully crewed.")])
    main.app.dependency_overrides[main.get_llm_factory] = lambda: (lambda tools: model)
    monkeypatch.setattr(main.get_settings(), "rate_limit_per_minute", 1)
    body = {"ruleset": "dgca_current", "disruptions": [],
            "messages": [{"role": "user", "content": "Is everything crewed?"}]}
    r = client.post("/chat", json=body)
    assert r.status_code == 200 and r.json()["verified"] is True
    assert client.post("/chat", json=body).status_code == 429


def test_chat_last_turn_must_be_the_user(client):
    body = {"ruleset": "dgca_current", "disruptions": [],
            "messages": [{"role": "assistant", "content": "hello"}]}
    assert client.post("/chat", json=body).status_code == 422


ORIGIN = {"Origin": "http://localhost:5173"}
CHAT = {"ruleset": "dgca_current", "disruptions": [],
        "messages": [{"role": "user", "content": "Is everything crewed?"}]}


def raising_factory(exc):
    def factory(tools):
        raise exc
    return factory


@pytest.fixture
def lenient_client(client):
    yield TestClient(main.app, raise_server_exceptions=False)


def test_chat_internal_error_is_json_with_cors(lenient_client):
    main.app.dependency_overrides[main.get_llm_factory] = lambda: raising_factory(
        RuntimeError("boom"))
    r = lenient_client.post("/chat", json=CHAT, headers=ORIGIN)
    assert r.status_code == 500 and r.json() == {"detail": "Internal error"}
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_groq_quota_is_429_with_cors(lenient_client):
    import groq
    import httpx

    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.test"))
    exc = groq.RateLimitError("rate limited", response=resp, body=None)
    main.app.dependency_overrides[main.get_llm_factory] = lambda: raising_factory(exc)
    r = lenient_client.post("/chat", json=CHAT, headers=ORIGIN)
    assert r.status_code == 429 and "quota" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_groq_failure_is_502(lenient_client):
    import groq
    import httpx

    exc = groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.test"))
    main.app.dependency_overrides[main.get_llm_factory] = lambda: raising_factory(exc)
    r = lenient_client.post("/chat", json=CHAT, headers=ORIGIN)
    assert r.status_code == 502 and r.headers["access-control-allow-origin"]


def test_replan_internal_error_is_json_with_cors(lenient_client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "_scenario", boom)
    r = lenient_client.post("/replan", json={"disruptions": []}, headers=ORIGIN)
    assert r.status_code == 500 and r.json() == {"detail": "Internal error"}
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = lenient_client.get("/roster", headers=ORIGIN)
    assert r.status_code == 500 and r.headers["access-control-allow-origin"]


def scripted(client):
    model = ScriptedChatModel(script=[AIMessage(content="The roster is fully crewed.")])
    main.app.dependency_overrides[main.get_llm_factory] = lambda: (lambda tools: model)


def test_rate_limit_keys_on_the_right_most_forwarded_ip(client, monkeypatch):
    scripted(client)
    monkeypatch.setattr(main.get_settings(), "rate_limit_per_minute", 1)
    xff = lambda left: {"X-Forwarded-For": f"{left}, 203.0.113.9"}  # noqa: E731
    assert client.post("/chat", json=CHAT, headers=xff("10.0.0.1")).status_code == 200
    assert client.post("/chat", json=CHAT, headers=xff("10.0.0.2")).status_code == 429
    other = {"X-Forwarded-For": "10.0.0.1, 198.51.100.7"}
    assert client.post("/chat", json=CHAT, headers=other).status_code == 200


def test_rate_limit_drops_stale_entries(client):
    scripted(client)
    main._hits["chat:old"].append(time.time() - 120)
    assert client.post("/chat", json=CHAT).status_code == 200
    assert "chat:old" not in main._hits
    assert all(main._hits.values())


def test_replan_has_a_looser_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main.get_settings(), "rate_limit_per_minute", 1)
    codes = [client.post("/replan", json={"disruptions": []}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_request_size_limits(client):
    scripted(client)
    sick = {"kind": "sick", "pilot_id": "DEL-C01", "from_day": 1, "to_day": 1}
    assert client.post("/replan", json={"disruptions": [sick] * 31}).status_code == 422
    turn = {"role": "user", "content": "hi"}
    assert client.post("/chat", json={**CHAT, "messages": [turn] * 21}).status_code == 422
    for content in ("", "x" * 2001):
        body = {**CHAT, "messages": [{"role": "user", "content": content}]}
        assert client.post("/chat", json=body).status_code == 422
    for path in ("/replan", "/chat"):
        assert client.post(path, json={**CHAT, "ruleset": "bogus"}).status_code == 422


def test_validation_errors_have_a_string_detail(client):
    body = {"disruptions": [{"kind": "delay", "flight_id": "SK115-D2", "minutes": 0}]}
    r = client.post("/replan", json=body)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and "minutes" in r.json()["detail"]
