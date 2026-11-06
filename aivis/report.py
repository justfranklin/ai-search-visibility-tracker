"""Turn the results history into visibility metrics and an HTML report."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import Config
from .store import Row

TEMPLATES = Path(__file__).resolve().parent / "templates"
SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]  # fixed categorical order


@dataclass
class BrandStats:
    brand: str
    is_you: bool
    answers: int = 0
    mentions: int = 0
    firsts: int = 0
    cited: int = 0
    rank_sum: int = 0

    @property
    def mention_rate(self) -> float:
        return self.mentions / self.answers if self.answers else 0.0

    @property
    def first_rate(self) -> float:
        return self.firsts / self.answers if self.answers else 0.0

    @property
    def cite_rate(self) -> float:
        return self.cited / self.answers if self.answers else 0.0

    @property
    def avg_rank(self) -> float | None:
        return self.rank_sum / self.mentions if self.mentions else None


def brand_stats(rows: list[Row]) -> dict[str, BrandStats]:
    stats: dict[str, BrandStats] = {}
    for r in rows:
        s = stats.setdefault(r.brand, BrandStats(r.brand, r.is_you))
        s.answers += 1
        if r.mentioned:
            s.mentions += 1
            s.rank_sum += r.rank or 0
            s.firsts += r.rank == 1
        s.cited += r.cited
    return stats


@dataclass
class Gap:
    prompt_id: str
    topic: str
    question: str
    competitors: list[tuple[str, int]]   # (brand, answers mentioning them)
    answers: int


@dataclass
class Report:
    you: str
    run_dates: list[str]
    latest: str
    previous: str | None
    you_now: BrandStats
    you_prev: BrandStats | None
    ranking: list[BrandStats]
    trend: dict[str, list[tuple[str, float]]]
    by_engine: list[tuple[str, float, float | None]]
    by_topic: list[tuple[str, float, str, float]]
    grid: list[dict]
    engines: list[str]
    gaps: list[Gap] = field(default_factory=list)


def build_report(cfg: Config, rows: list[Row]) -> Report:
    if not rows:
        raise ValueError("No results yet. Run `python -m aivis run` (or `demo`) first.")
    you = cfg.brand.name
    dates = sorted({r.run_date for r in rows})
    latest, previous = dates[-1], (dates[-2] if len(dates) > 1 else None)
    now = [r for r in rows if r.run_date == latest]
    stats = brand_stats(now)
    prev_stats = brand_stats([r for r in rows if r.run_date == previous]) if previous else {}
    ranking = sorted(stats.values(), key=lambda s: (-s.mention_rate, s.brand))

    # Trend: you plus the three most-mentioned competitors right now.
    tracked = [you] + [s.brand for s in ranking if s.brand != you][:3]
    trend = {}
    for b in tracked:
        pts = []
        for d in dates:
            st = brand_stats([r for r in rows if r.run_date == d and r.brand == b]).get(b)
            if st:
                pts.append((d, st.mention_rate))
        trend[b] = pts

    engines = sorted({r.engine for r in now})
    by_engine = []
    for e in engines:
        st = brand_stats([r for r in now if r.engine == e and r.brand == you]).get(you)
        if st:
            by_engine.append((e, st.mention_rate, st.avg_rank))

    by_topic = []
    for topic in dict.fromkeys(p.topic for p in cfg.prompts):
        tstats = brand_stats([r for r in now if r.topic == topic])
        if not tstats:
            continue
        mine = tstats.get(you)
        rivals = [s for s in tstats.values() if s.brand != you]
        top = max(rivals, key=lambda s: s.mention_rate) if rivals else None
        by_topic.append((topic, mine.mention_rate if mine else 0.0,
                         top.brand if top else "", top.mention_rate if top else 0.0))

    # Question-by-engine grid and the gaps (competitors show up, you don't).
    cell: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in now:
        cell[(r.prompt_id, r.engine)].append(r)
    grid, gaps = [], []
    for p in cfg.prompts:
        prow = {"question": p.text, "topic": p.topic, "cells": []}
        mentioned_anywhere = False
        rival_counts: dict[str, int] = defaultdict(int)
        answers = 0
        for e in engines:
            rs = cell.get((p.id, e), [])
            mine = [r for r in rs if r.brand == you]
            answers += len(mine)
            hits = [r for r in mine if r.mentioned]
            mentioned_anywhere |= bool(hits)
            for r in rs:
                if r.brand != you and r.mentioned:
                    rival_counts[r.brand] += 1
            best = min((r.rank for r in hits if r.rank), default=None)
            prow["cells"].append({"engine": e, "n": len(mine), "hits": len(hits), "best": best})
        if any(c["n"] for c in prow["cells"]):
            grid.append(prow)
        if not mentioned_anywhere and rival_counts:
            gaps.append(Gap(p.id, p.topic, p.text,
                            sorted(rival_counts.items(), key=lambda kv: -kv[1]), answers))

    return Report(you, dates, latest, previous, stats[you], prev_stats.get(you), ranking, trend,
                  by_engine, by_topic, grid, engines, gaps)


# --- SVG ----------------------------------------------------------------------

def ranking_svg(rep: Report, width: int = 940) -> Markup:
    row, label_w, right = 34, 170, 70
    h = row * len(rep.ranking) + 8
    plot = width - label_w - right
    out = [f'<svg viewBox="0 0 {width} {h}" role="img" aria-label="Share of AI answers mentioning each brand">']
    for i, s in enumerate(rep.ranking):
        y = i * row + 6
        w = max(plot * s.mention_rate, 0)
        r = min(4, w / 2)
        fill = "var(--s1)" if s.is_you else "var(--neutral)"
        weight = ' font-weight="650"' if s.is_you else ""
        name = escape(s.brand) + (" (you)" if s.is_you else "")
        avg = f", average position {s.avg_rank:.1f}" if s.avg_rank else ""
        out.append(f'<g class="mark"><title>{name}: mentioned in {s.mention_rate:.0%} of answers{avg}</title>'
                   f'<rect class="hit" x="0" y="{y - 6}" width="{width}" height="{row}"/>'
                   f'<text class="label" x="{label_w - 12}" y="{y + 15}" text-anchor="end"{weight}>{name}</text>')
        if w > 0:
            out.append(f'<path fill="{fill}" d="M{label_w},{y} H{label_w + w - r:.1f} Q{label_w + w:.1f},{y} '
                       f'{label_w + w:.1f},{y + r:.1f} V{y + 20 - r:.1f} Q{label_w + w:.1f},{y + 20} '
                       f'{label_w + w - r:.1f},{y + 20} H{label_w} Z"/>')
        out.append(f'<text class="value" x="{label_w + w + 8:.1f}" y="{y + 15}">{s.mention_rate:.0%}</text></g>')
    out.append(f'<line class="axis" x1="{label_w}" x2="{label_w}" y1="0" y2="{h - 2}"/></svg>')
    return Markup("".join(out))


def trend_svg(rep: Report, width: int = 940, height: int = 280) -> Markup:
    if len(rep.run_dates) < 2:
        return Markup('<p class="note">The trend appears after the second run.</p>')
    left, right, top, bottom = 44, 130, 14, 30
    pw, ph = width - left - right, height - top - bottom
    xs = {d: left + pw * i / (len(rep.run_dates) - 1) for i, d in enumerate(rep.run_dates)}
    peak = max(0.5, max((v for pts in rep.trend.values() for _, v in pts), default=0.5))
    peak = min(1.0, (int(peak * 10) + 1) / 10)

    def y(v): return top + ph * (1 - v / peak)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Mention rate over time">']
    for frac in (0, 0.5, 1):
        v = peak * frac
        out.append(f'<line class="{"axis" if frac == 0 else "grid"}" x1="{left}" x2="{left + pw}" '
                   f'y1="{y(v):.1f}" y2="{y(v):.1f}"/><text class="tick" x="{left - 8}" y="{y(v) + 4:.1f}" '
                   f'text-anchor="end">{v:.0%}</text>')
    for i, d in enumerate(rep.run_dates):
        if len(rep.run_dates) <= 8 or i % 2 == 0 or i == len(rep.run_dates) - 1:
            out.append(f'<text class="tick" x="{xs[d]:.1f}" y="{height - 8}" text-anchor="middle">{d[5:]}</text>')
    ends = []
    for k, (brand, pts) in enumerate(rep.trend.items()):
        color = SERIES[k % len(SERIES)]
        path = " ".join(f'{"M" if j == 0 else "L"}{xs[d]:.1f},{y(v):.1f}' for j, (d, v) in enumerate(pts))
        out.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for d, v in pts:
            out.append(f'<g class="mark"><title>{escape(brand)}, {d}: {v:.0%}</title>'
                       f'<circle cx="{xs[d]:.1f}" cy="{y(v):.1f}" r="12" class="hit"/>'
                       f'<circle cx="{xs[d]:.1f}" cy="{y(v):.1f}" r="4" fill="{color}" stroke="var(--surface-1)" stroke-width="2"/></g>')
        if pts:
            ends.append([y(pts[-1][1]), brand, pts[-1][1], k])
    # Direct end labels, nudged apart so they don't collide.
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 15)
    for ly, brand, v, k in ends:
        you = ' font-weight="650"' if brand == rep.you else ""
        out.append(f'<text class="label" x="{left + pw + 10}" y="{ly + 4:.1f}"{you}>{escape(brand)} {v:.0%}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def render_html(cfg: Config, rep: Report) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    legend = [(b, SERIES[i % len(SERIES)]) for i, b in enumerate(rep.trend)]
    return env.get_template("report.html.j2").render(
        cfg=cfg, rep=rep, ranking=ranking_svg(rep), trend=trend_svg(rep), legend=legend)
