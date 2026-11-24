"""Regression : la detection d'Ollama local ne doit pas couter ~5 s a chaque requete.

Avant : choose_targets() appelait _get_ollama_local_models() (HTTP synchrone,
dans un handler async) a CHAQUE requete, meme pour une chaine sans modele
local. Ollama eteint = ~4,8 s perdues par requete et boucle d'evenements
bloquee pour toutes les autres requetes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main  # noqa: E402
from router import ROUTING_CHAINS, RouteTarget  # noqa: E402


def _count_probes(monkeypatch, result):
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return result

    monkeypatch.setattr(main, "_get_ollama_local_models", fake)
    monkeypatch.setattr(main, "_local_models_cache", None)
    monkeypatch.setattr(main, "_local_models_checked_at", 0.0)
    monkeypatch.setattr(main.state, "active_preset_id", None)
    monkeypatch.setattr(main.state, "model_locks", {})
    return calls


def test_no_probe_when_chain_has_no_local_model(monkeypatch):
    calls = _count_probes(monkeypatch, [])
    monkeypatch.setitem(ROUTING_CHAINS, "t-cloud", [RouteTarget("nvidia", "m", "")])

    for _ in range(5):
        targets = main.choose_targets("t-cloud")

    assert [t.model for t in targets] == ["m"]
    assert calls["n"] == 0


def test_probe_is_cached_between_requests(monkeypatch):
    calls = _count_probes(monkeypatch, ["qwen3:8b"])
    monkeypatch.setitem(ROUTING_CHAINS, "t-local", [RouteTarget("local", "x", "")])

    for _ in range(5):
        targets = main.choose_targets("t-local")

    assert targets[0].model == "qwen3:8b"  # le modele local reel est toujours resolu
    assert calls["n"] == 1


def test_probe_is_refreshed_after_ttl(monkeypatch):
    calls = _count_probes(monkeypatch, [])
    monkeypatch.setitem(ROUTING_CHAINS, "t-local", [RouteTarget("local", "x", "")])

    main.choose_targets("t-local")
    monkeypatch.setattr(main, "_local_models_checked_at", main.time.monotonic() - main.LOCAL_MODELS_TTL_SECONDS - 1)
    main.choose_targets("t-local")

    assert calls["n"] == 2
