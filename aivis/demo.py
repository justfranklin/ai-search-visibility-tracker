"""Synthetic demo: fictional brands and generated answers, so the report can be
explored without API keys. Nothing here reflects any real product or real AI output."""

from __future__ import annotations

import random
from datetime import date, timedelta

from .config import Brand, Config, EngineConfig, Prompt
from .engines import Answer

DEMO_BRANDS = [
    Brand("Lumora", "lumora.example", is_you=True),
    Brand("Pipewell", "pipewell.example"),
    Brand("Quillr", "quillr.example"),
    Brand("Stackfold", "stackfold.example"),
    Brand("Orbitra", "orbitra.example"),
]

DEMO_PROMPTS = [
    Prompt("best-b2b", "Shortlist", "What are the best marketing automation platforms for a mid-size B2B company?"),
    Prompt("best-smb", "Shortlist", "Which marketing automation tool should a small business start with?"),
    Prompt("alt-pipewell", "Alternatives", "What are good alternatives to Pipewell?"),
    Prompt("lead-scoring", "Capabilities", "Which platforms have the best lead scoring?"),
    Prompt("crm", "Capabilities", "What marketing automation software has the best built-in CRM?"),
    Prompt("abm", "Capabilities", "What tools do B2B teams use for account-based marketing?"),
    Prompt("pricing", "Pricing", "What is the most affordable marketing automation platform?"),
    Prompt("migrate", "Switching", "Which marketing automation platforms are easiest to migrate to?"),
]

DEMO_ENGINES = [EngineConfig("assistant-a", "demo", "demo-model"),
                EngineConfig("assistant-b", "demo", "demo-model")]

# How likely each fictional brand is to appear, by topic. The story: Lumora published
# comparison and capability content, so those topics improve week over week, while
# pricing and switching questions stay gaps.
BASE = {"Pipewell": 0.85, "Quillr": 0.6, "Stackfold": 0.45, "Orbitra": 0.3}
LUMORA = {"Shortlist": 0.25, "Alternatives": 0.35, "Capabilities": 0.15, "Pricing": 0.03, "Switching": 0.03}
IMPROVING = {"Shortlist", "Alternatives", "Capabilities"}
FILLER = ["is a common pick for growing teams", "is often mentioned for its reporting",
          "is known for an approachable editor", "suits teams with complex workflows",
          "is frequently shortlisted by B2B marketers"]


def demo_config() -> Config:
    return Config(DEMO_BRANDS[0], DEMO_BRANDS[1:], DEMO_PROMPTS, DEMO_ENGINES, samples=2)


def make_asker(week: int, seed: int = 11):
    rng = random.Random(seed + week * 101)

    def ask(engine: EngineConfig, question: str) -> Answer:
        topic = next(p.topic for p in DEMO_PROMPTS if p.text == question)
        lift = (0.09 * week if topic in IMPROVING else 0) + (0.04 if engine.id == "assistant-b" else 0)
        odds = dict(BASE, Lumora=min(LUMORA[topic] + lift, 0.9))
        picked = [b for b in odds if rng.random() < odds[b]] or ["Pipewell"]
        rng.shuffle(picked)
        picked.sort(key=lambda b: -odds[b] * rng.uniform(0.6, 1.4))
        lines = [f"{i}. **{b}** {rng.choice(FILLER)}." for i, b in enumerate(picked, 1)]
        cites = [f"https://{b.lower()}.example/guide" for b in picked if rng.random() < 0.35]
        return Answer("Here are some options to consider:\n" + "\n".join(lines), cites)

    return ask


def demo_dates(weeks: int = 6, end: date | None = None) -> list[str]:
    end = end or date.today()
    return [(end - timedelta(weeks=weeks - 1 - i)).isoformat() for i in range(weeks)]
