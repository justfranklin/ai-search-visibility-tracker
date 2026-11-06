"""Tracker configuration: your brand, competitors, buyer questions and AI engines."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "tracker.yaml"


@dataclass
class Brand:
    name: str
    domain: str = ""
    aliases: list[str] = field(default_factory=list)
    is_you: bool = False

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases]


@dataclass
class Prompt:
    id: str
    topic: str
    text: str


@dataclass
class EngineConfig:
    id: str
    provider: str
    model: str = ""
    key_env: str = ""

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.key_env) if self.key_env else None

    @property
    def ready(self) -> bool:
        return bool(self.model and self.api_key)


@dataclass
class Config:
    brand: Brand
    competitors: list[Brand]
    prompts: list[Prompt]
    engines: list[EngineConfig]
    samples: int = 1

    @property
    def brands(self) -> list[Brand]:
        return [self.brand, *self.competitors]


def load_config(path: str | Path = DEFAULT_CONFIG) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    ids = [p["id"] for p in raw.get("prompts", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("Prompt ids must be unique.")
    return Config(
        brand=Brand(**raw["brand"], is_you=True),
        competitors=[Brand(**c) for c in raw.get("competitors", [])],
        prompts=[Prompt(**p) for p in raw.get("prompts", [])],
        engines=[EngineConfig(**e) for e in raw.get("engines", [])],
        samples=int(raw.get("samples", 1)),
    )
