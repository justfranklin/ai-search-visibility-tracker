"""Ask every question of every ready engine and record what each answer says."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .analyze import analyze
from .config import Config, EngineConfig
from .engines import Answer, EngineError, ask
from .store import Row


def run(cfg: Config, engines: list[EngineConfig], samples: int | None = None,
        run_date: str | None = None, ask_fn: Callable[[EngineConfig, str], Answer] = ask,
        log: Callable[[str], None] = print) -> tuple[list[Row], list[dict]]:
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    samples = samples or cfg.samples
    rows: list[Row] = []
    answers: list[dict] = []
    for eng in engines:
        log(f"Asking {eng.id} ({eng.model}) {len(cfg.prompts)} questions × {samples}…")
        failures = 0
        for prompt in cfg.prompts:
            for s in range(1, samples + 1):
                try:
                    ans = ask_fn(eng, prompt.text)
                except EngineError as exc:
                    failures += 1
                    log(f"  ! {eng.id} / {prompt.id}: {exc}")
                    continue
                for r in analyze(ans.text, ans.citations, cfg.brands):
                    rows.append(Row(run_date, eng.id, eng.model, prompt.id, prompt.topic, s,
                                    r.brand, r.is_you, r.mentioned, r.rank, r.cited))
                answers.append({"run_date": run_date, "engine": eng.id, "model": eng.model,
                                "prompt_id": prompt.id, "sample": s, "question": prompt.text,
                                "answer": ans.text, "citations": ans.citations})
        if failures:
            log(f"  {failures} questions failed on {eng.id}")
    return rows, answers
