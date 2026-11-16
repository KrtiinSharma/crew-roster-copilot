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
