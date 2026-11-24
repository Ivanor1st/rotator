"""Regression : une erreur propre a un MODELE ne doit pas mettre la CLE en pause.

Avant : un modele retire (404) ou payant (402) comptait comme une erreur de cle.
Apres 3 modeles morts, la cle passait 1 h en pause pour TOUS les modeles, et
le rotator renvoyait « All providers failed ... Last error: None ».
Aussi : un simple delai depasse (fournisseur lent) etait pris pour une coupure
reseau et faisait sauter tous les autres fournisseurs cloud.

Ces tests n'utilisent PAS la vraie base rotator.db (base factice en memoire).
"""
import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main  # noqa: E402
from key_manager import KeyManager  # noqa: E402
from router import RouteTarget  # noqa: E402


class FakeDB:
    async def increment_project_daily_usage(self, *a, **k): pass
    async def upsert_key_stats(self, *a, **k): pass
    async def add_profile_history(self, *a, **k): pass
    async def increment_daily_quota(self, *a, **k): pass
    async def list_model_performance(self, *a, **k): return []
    async def upsert_model_performance(self, *a, **k): pass


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        self.text = "" if status_code < 400 else '{"error":"x"}'

    def json(self):
        return self._body


class FakeClient:
    """Repond selon le modele demande ; compte les appels par modele."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = {}

    async def post(self, url, headers=None, json=None, **kwargs):
        model = json["model"]
        self.calls[model] = self.calls.get(model, 0) + 1
        outcome = self.behaviour[model]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


CONFIG = {
    "keys": {
        "ollama_cloud": [{"label": f"O{i}", "token": f"tok-{i}"} for i in range(3)],
        "nvidia": [{"label": "N1", "key": "nvapi-test"}],
    },
    "settings": {"retry_delay": 0, "retry_attempts": {"nvidia": 1, "ollama_cloud": 1}},
}


@pytest.fixture
def rig(monkeypatch):
    km = KeyManager(CONFIG, {})
    monkeypatch.setattr(main.state, "key_manager", km)
    monkeypatch.setattr(main.state, "db", FakeDB())
    monkeypatch.setattr(main.state, "last_key_by_profile", {})
    monkeypatch.setattr(main.state, "active_routes", {})
    monkeypatch.setattr(main, "send_notification", lambda *a, **k: None)
    monkeypatch.setattr(main, "dispatch_webhook", lambda *a, **k: None)

    def install(behaviour):
        client = FakeClient(behaviour)
        monkeypatch.setattr(main.state, "client", client)
        return client

    return km, install


def run(candidates):
    return asyncio.run(
        main._proxy_with_fallback(
            profile="coding",
            candidates=candidates,
            payload={"messages": [{"role": "user", "content": "hi"}]},
            stream=False,
            project_token="rotator",
        )
    )


@pytest.mark.parametrize("status", [400, 402, 404, 410, 422])
def test_model_level_error_spares_key_and_skips_other_keys(rig, status):
    km, install = rig
    client = install({"dead": status, "good": 200})

    resp = run([RouteTarget("ollama_cloud", "dead", ""), RouteTarget("ollama_cloud", "good", "")])

    assert resp.status_code == 200
    assert client.calls["dead"] == 1  # une seule cle essayee, pas les 3
    assert not km.exhausted_until
    assert all(v == 0 for v in km.consecutive_errors.values())


def test_three_dead_models_do_not_poison_the_keys(rig):
    km, install = rig
    install({"d1": 404, "d2": 402, "d3": 410, "good": 200})

    resp = run([RouteTarget("ollama_cloud", m, "") for m in ("d1", "d2", "d3", "good")])

    assert resp.status_code == 200
    assert not km.exhausted_until  # aucune cle en pause


def test_key_level_error_still_counts_against_the_key(rig):
    km, install = rig
    install({"m": 401})

    with pytest.raises(main.HTTPException) as err:
        run([RouteTarget("ollama_cloud", "m", "")])

    assert err.value.status_code == 503
    assert sum(km.consecutive_errors.values()) == 3  # chaque cle a ete penalisee


def test_read_timeout_is_not_a_network_outage(rig):
    _, install = rig
    install({"slow": httpx.ReadTimeout("slow"), "good": 200})

    resp = run([RouteTarget("nvidia", "slow", ""), RouteTarget("ollama_cloud", "good", "")])

    assert resp.status_code == 200  # avant : 503 « Network unavailable »


def test_connect_error_is_still_a_network_outage(rig):
    _, install = rig
    install({"down": httpx.ConnectError("no route"), "good": 200})

    with pytest.raises(main.HTTPException) as err:
        run([RouteTarget("nvidia", "down", ""), RouteTarget("ollama_cloud", "good", "")])

    assert "Network unavailable" in err.value.detail


def test_no_eligible_key_gives_a_real_last_error(rig):
    km, install = rig
    install({"m": 200})
    for key in km.keys_by_provider["ollama_cloud"]:
        km.block_key(key.key_id)

    with pytest.raises(main.HTTPException) as err:
        run([RouteTarget("ollama_cloud", "m", "")])

    assert "Last error: None" not in err.value.detail
    assert "no eligible key" in err.value.detail


def test_overloaded_model_skips_to_next_candidate_and_spares_key(rig):
    km, install = rig
    client = install({"busy": 503, "good": 200})

    resp = run([RouteTarget("ollama_cloud", "busy", ""), RouteTarget("ollama_cloud", "good", "")])

    assert resp.status_code == 200
    assert client.calls["busy"] == 1  # pas les 3 cles
    assert not km.exhausted_until
    assert all(v == 0 for v in km.consecutive_errors.values())


def test_overloaded_still_retries_same_key_first(rig, monkeypatch):
    km, install = rig
    km.retry_attempts["ollama_cloud"] = 2
    client = install({"busy": 503, "good": 200})

    run([RouteTarget("ollama_cloud", "busy", ""), RouteTarget("ollama_cloud", "good", "")])

    assert client.calls["busy"] == 2  # 2 tentatives sur la meme cle, puis candidat suivant
