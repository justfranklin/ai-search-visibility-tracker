"""Command line.

  python -m aivis engines            # which engines are ready (model + API key set)
  python -m aivis run                # ask every question, save results, build the report
  python -m aivis report             # rebuild the report from saved results
  python -m aivis demo               # fictional brands + synthetic answers, no keys needed
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_CONFIG, load_config
from .demo import demo_config, demo_dates, make_asker
from .report import build_report, render_html
from .run import run
from .store import append_answers, append_rows, read_rows


def write_report(cfg, data_dir: Path, site_dir: Path) -> Path:
    rows = read_rows(data_dir / "results.csv")
    page = render_html(cfg, build_report(cfg, rows))
    site_dir.mkdir(parents=True, exist_ok=True)
    out = site_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def main(argv=None, ask_fn=None) -> int:
    p = argparse.ArgumentParser(prog="aivis", description="Track how AI assistants talk about your brand.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--data", default="data", help="Folder for results.csv and raw answers.")
    p.add_argument("--site", default="site", help="Folder for the HTML report.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("engines", help="List engines and whether each is ready.")
    r = sub.add_parser("run", help="Ask the questions and record results.")
    r.add_argument("--engines", help="Comma-separated engine ids (default: every ready engine).")
    r.add_argument("--samples", type=int, help="Times to ask each question (overrides config).")
    r.add_argument("--date", help="Record the run under this date (YYYY-MM-DD).")
    sub.add_parser("report", help="Rebuild the HTML report from saved results.")
    d = sub.add_parser("demo", help="Generate a synthetic demo with fictional brands.")
    d.add_argument("--weeks", type=int, default=6)
    d.add_argument("--out", default="demo")
    args = p.parse_args(argv)

    if args.cmd == "demo":
        cfg = demo_config()
        out = Path(args.out)
        (out / "results.csv").unlink(missing_ok=True)
        for week, day in enumerate(demo_dates(args.weeks)):
            rows, answers = run(cfg, cfg.engines, run_date=day, ask_fn=make_asker(week), log=lambda m: None)
            append_rows(rows, out / "results.csv")
        print(f"Demo: {args.weeks} weekly runs of synthetic answers for fictional brands")
        print(f"  wrote {write_report(cfg, out, out)}")
        return 0

    cfg = load_config(args.config)
    data, site = Path(args.data), Path(args.site)

    if args.cmd == "engines":
        for e in cfg.engines:
            missing = [x for x, ok in (("model", e.model), (e.key_env, e.api_key)) if not ok]
            state = "ready" if not missing else "not ready (set " + " and ".join(missing) + ")"
            print(f"  {e.id:12} {e.provider:11} {e.model or '-':22} {state}")
        return 0

    if args.cmd == "run":
        engines = [e for e in cfg.engines if e.ready]
        if args.engines:
            wanted = {x.strip() for x in args.engines.split(",")}
            engines = [e for e in engines if e.id in wanted]
        if not engines:
            print("No engines are ready. Set a model and API key (see `python -m aivis engines`).")
            return 2
        kwargs = {"ask_fn": ask_fn} if ask_fn else {}
        rows, answers = run(cfg, engines, args.samples, args.date, **kwargs)
        if not rows:
            print("No answers collected.")
            return 1
        append_rows(rows, data / "results.csv")
        append_answers(answers, data / "answers" / f"{rows[0].run_date}.jsonl")
        print(f"  saved {len(answers)} answers to {data}")

    print(f"  wrote {write_report(cfg, data, site)}")
    return 0
