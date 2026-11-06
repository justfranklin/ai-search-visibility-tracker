"""Results history: one CSV row per (run, engine, question, sample, brand), plus the
raw answers as JSON Lines so every number can be traced back to what the AI said."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ["run_date", "engine", "model", "prompt_id", "topic", "sample",
           "brand", "is_you", "mentioned", "rank", "cited"]


@dataclass
class Row:
    run_date: str
    engine: str
    model: str
    prompt_id: str
    topic: str
    sample: int
    brand: str
    is_you: bool
    mentioned: bool
    rank: int | None
    cited: bool

    def to_csv(self) -> list:
        return [self.run_date, self.engine, self.model, self.prompt_id, self.topic, self.sample,
                self.brand, int(self.is_you), int(self.mentioned),
                "" if self.rank is None else self.rank, int(self.cited)]


def append_rows(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLUMNS)
        w.writerows(r.to_csv() for r in rows)


def read_rows(path: Path) -> list[Row]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [Row(r["run_date"], r["engine"], r["model"], r["prompt_id"], r["topic"],
                    int(r["sample"]), r["brand"], r["is_you"] == "1", r["mentioned"] == "1",
                    int(r["rank"]) if r["rank"] else None, r["cited"] == "1")
                for r in csv.DictReader(f)]


def append_answers(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_answers(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
