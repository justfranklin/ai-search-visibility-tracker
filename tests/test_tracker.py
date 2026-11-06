from pathlib import Path
from types import SimpleNamespace

import pytest

from aivis import engines
from aivis.analyze import analyze, domain_cited
from aivis.cli import main
from aivis.config import Brand, Config, EngineConfig, Prompt, load_config
from aivis.engines import Answer, EngineError
from aivis.report import build_report, render_html
from aivis.run import run
from aivis.store import append_rows, read_rows

YOU = Brand("Acme", "acme.com", ["Acme Cloud"], is_you=True)
RIVALS = [Brand("Globex", "globex.com"), Brand("Initech", "initech.io", ["Initrode"])]


def cfg(prompts=None):
    prompts = prompts or [Prompt("q1", "Shortlist", "best tools?"), Prompt("q2", "Pricing", "cheapest?")]
    return Config(YOU, RIVALS, prompts, [EngineConfig("e1", "demo", "m")], samples=1)


# --- analysis ---------------------------------------------------------------

def test_mentions_ranks_and_aliases():
    text = "Top picks: **Globex**, then Acme Cloud, and Initrode for enterprises."
    res = {r.brand: r for r in analyze(text, [], [YOU, *RIVALS])}
    assert res["Globex"].rank == 1 and res["Acme"].rank == 2 and res["Initech"].rank == 3
    assert res["Acme"].is_you and res["Acme"].mentioned


def test_word_boundaries_and_possessives():
    res = {r.brand: r for r in analyze("Acmetric is unrelated. Acme's editor is good.", [], [YOU])}
    assert res["Acme"].mentioned and res["Acme"].rank == 1
    assert not analyze("Acmetric only", [], [YOU])[0].mentioned
    assert not analyze("acme-corp is different", [], [YOU])[0].mentioned


def test_citations_from_list_and_inline_links():
    assert domain_cited("acme.com", ["https://www.acme.com/pricing"])
    assert domain_cited("acme.com", ["https://docs.acme.com/x"])
    assert not domain_cited("acme.com", ["https://notacme.com"])
    res = analyze("See https://globex.com/compare for details.", ["https://acme.com/a"], [YOU, *RIVALS])
    cited = {r.brand: r.cited for r in res}
    assert cited == {"Acme": True, "Globex": True, "Initech": False}


# --- engines ----------------------------------------------------------------

class FakeResp:
    def __init__(self, body, status=200, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = str(body)

    def json(self):
        return self._body


def fake_post(responses, calls):
    def post(url, json=None, headers=None, timeout=None):
        calls.append(SimpleNamespace(url=url, json=json, headers=headers))
        return responses.pop(0)
    return post


@pytest.mark.parametrize("provider,body,expected_text,expected_cites", [
    ("anthropic", {"content": [{"type": "text", "text": "Use Acme."}]}, "Use Acme.", []),
    ("openai", {"choices": [{"message": {"content": "Try Globex"}}]}, "Try Globex", []),
    ("perplexity", {"choices": [{"message": {"content": "Acme [1]"}}], "citations": ["https://acme.com"]},
     "Acme [1]", ["https://acme.com"]),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "Initech"}]},
                                "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://initech.io"}}]}}]},
     "Initech", ["https://initech.io"]),
])
def test_provider_parsing(monkeypatch, provider, body, expected_text, expected_cites):
    calls = []
    monkeypatch.setattr(engines.requests, "post", fake_post([FakeResp(body)], calls))
    ans = engines.ask(EngineConfig("x", provider, "model-x", "K"), "q?")
    assert ans.text == expected_text and ans.citations == expected_cites
    assert calls[0].json  # a request body was sent


def test_retries_then_raises(monkeypatch):
    monkeypatch.setattr(engines.time, "sleep", lambda s: None)
    calls = []
    ok = FakeResp({"choices": [{"message": {"content": "hi"}}]})
    monkeypatch.setattr(engines.requests, "post", fake_post([FakeResp({}, 429), ok], calls))
    assert engines.ask(EngineConfig("x", "openai", "m", "K"), "q").text == "hi"
    monkeypatch.setattr(engines.requests, "post", fake_post([FakeResp({"error": "bad"}, 401)], []))
    with pytest.raises(EngineError):
        engines.ask(EngineConfig("x", "openai", "m", "K"), "q")


def test_engine_ready_needs_model_and_key(monkeypatch):
    monkeypatch.delenv("SOME_KEY", raising=False)
    e = EngineConfig("x", "openai", "", "SOME_KEY")
    assert not e.ready
    monkeypatch.setenv("SOME_KEY", "k")
    assert not e.ready and EngineConfig("x", "openai", "m", "SOME_KEY").ready


# --- run, store, report ---------------------------------------------------------

def scripted(answers):
    def ask(engine, question):
        a = answers[question]
        if isinstance(a, Exception):
            raise a
        return a
    return ask


def test_run_records_rows_and_survives_failures():
    c = cfg()
    rows, answers = run(c, c.engines, run_date="2026-11-01", log=lambda m: None, ask_fn=scripted({
        "best tools?": Answer("Globex and Acme"), "cheapest?": EngineError("boom")}))
    assert len(answers) == 1 and len(rows) == 3  # one answer x three brands
    assert {(r.brand, r.rank) for r in rows} == {("Acme", 2), ("Globex", 1), ("Initech", None)}


def test_store_round_trip(tmp_path: Path):
    c = cfg()
    rows, _ = run(c, c.engines, run_date="2026-11-01", log=lambda m: None,
                  ask_fn=scripted({"best tools?": Answer("Acme"), "cheapest?": Answer("Globex")}))
    append_rows(rows, tmp_path / "r.csv")
    append_rows(rows, tmp_path / "r.csv")
    back = read_rows(tmp_path / "r.csv")
    assert len(back) == 2 * len(rows) and back[0] == rows[0]


def test_report_metrics_trend_and_gaps():
    c = cfg()
    all_rows = []
    for day, best in (("2026-10-25", "Globex only"), ("2026-11-01", "Acme then Globex")):
        rows, _ = run(c, c.engines, run_date=day, log=lambda m: None,
                      ask_fn=scripted({"best tools?": Answer(best), "cheapest?": Answer("Initech is cheapest")}))
        all_rows += rows
    rep = build_report(c, all_rows)
    assert rep.latest == "2026-11-01" and rep.previous == "2026-10-25"
    assert rep.you_now.mention_rate == 0.5 and rep.you_prev.mention_rate == 0.0
    assert rep.you_now.first_rate == 0.5
    assert [g.prompt_id for g in rep.gaps] == ["q2"]
    assert rep.gaps[0].competitors == [("Initech", 1)]
    assert [v for _, v in rep.trend["Acme"]] == [0.0, 0.5]
    html = render_html(c, rep)
    assert "Content gaps" in html and "cheapest?" in html and "<svg" in html


def test_report_requires_data():
    with pytest.raises(ValueError):
        build_report(cfg(), [])


def test_default_config_loads():
    c = load_config()
    assert c.brand.is_you and c.competitors and len(c.prompts) >= 5
    assert {e.provider for e in c.engines} <= set(engines.PROVIDERS)


def test_cli_demo_and_run(tmp_path, monkeypatch):
    assert main(["demo", "--weeks", "3", "--out", str(tmp_path / "demo")]) == 0
    assert (tmp_path / "demo" / "index.html").exists()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for k in ("OPENAI_API_KEY", "PERPLEXITY_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    rc = main(["--data", str(tmp_path / "data"), "--site", str(tmp_path / "site"), "run", "--date", "2026-11-01"],
              ask_fn=lambda e, q: Answer("HubSpot and Marketo are popular. https://hubspot.com"))
    assert rc == 0
    assert (tmp_path / "data" / "answers" / "2026-11-01.jsonl").exists()
    assert "HubSpot" in (tmp_path / "site" / "index.html").read_text()


def test_cli_run_without_engines(monkeypatch, tmp_path):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert main(["--data", str(tmp_path), "run"]) == 2
