#!/usr/bin/env python3
"""Golden-query regression evaluation for search quality.

Usage:
    scripts/eval-golden.py --set dev [--check-baseline] [--top-k 5]
    scripts/eval-golden.py --set holdout [--check-baseline]
    scripts/eval-golden.py --set all [--check-baseline]
    scripts/eval-golden.py --update-baseline --set {dev|holdout|all}
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docq import golden_eval, indexer, store, tokens
from docq.golden_eval import BASELINE_EPSILON

class _ValidationError(Exception):
    pass


EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
CORPUS_DIR = EVAL_DIR / "corpus"
BASELINES_PATH = EVAL_DIR / "baselines.json"


def _build_index(pdf_dir: Path):
    pdf_dir = pdf_dir.resolve()
    db_path = pdf_dir / "index.sqlite"
    conn = store.open_store(db_path)
    try:
        for pdf in sorted(pdf_dir.glob("*.pdf")):
            indexer.index_one_file(conn, pdf_dir, pdf)
    except Exception:
        conn.close()
        raise
    return conn


def _run_set(conn, set_name: str, top_k: int, show_details: bool) -> golden_eval.EvalResult:
    golden_path = EVAL_DIR / f"golden-{set_name}.json"
    queries = golden_eval.load_golden_set(golden_path)

    corpus_texts = golden_eval.corpus_text_map(CORPUS_DIR)
    errors = golden_eval.validate_golden_set(queries, corpus_texts)
    if errors:
        lines = [f"ゴールデン集の検証に失敗 ({set_name}):"]
        for e in errors:
            lines.append(f"  {e}")
        raise _ValidationError("\n".join(lines))

    result = golden_eval.evaluate(conn, queries, top_k=top_k)

    print(f"\n=== {set_name} ({result.total_queries} queries) ===")
    if show_details:
        for d in result.details:
            rank = d["rank"]
            if rank is not None:
                status = f"HIT  (top-1: {'✓' if rank == 1 else '-'}, top-{top_k}: ✓, rank={rank})"
            else:
                status = f"MISS (top-1: -, top-{top_k}: -)"
            print(f"  {d['anchor']:30s}: {status}")

    print(f"  top-1: {result.top1:.4f}  top-k: {result.topk:.4f}  MRR@{top_k}: {result.mrr_at_k:.4f}")
    return result


def _check_baselines(results: dict[str, golden_eval.EvalResult]) -> bool:
    try:
        with open(BASELINES_PATH, encoding="utf-8") as f:
            baselines = json.load(f)
    except FileNotFoundError:
        print("ERROR: baselines.json が無い", file=sys.stderr)
        return False

    bl_counter = baselines.get("token_counter")
    current_counter = tokens.counter_name()
    if bl_counter != current_counter:
        print(
            f"ERROR: トークンカウンタが不一致: baseline={bl_counter!r}, current={current_counter!r}",
            file=sys.stderr,
        )
        return False

    ok = True
    for set_name, result in results.items():
        bl = baselines.get(set_name)
        if bl is None:
            print(f"ERROR: baselines.json に {set_name!r} のエントリが無い", file=sys.stderr)
            ok = False
            continue
        failures = golden_eval.check_baseline(result, bl)
        failed_metrics = {msg.split(":")[0] for msg in failures}
        print(f"\n=== baseline check ({set_name}) ===")
        for metric in ("top1", "topk", "mrr_at_k"):
            actual = getattr(result, metric)
            expected = bl[metric]
            passed = metric not in failed_metrics
            print(f"  {metric:10s}: {actual:.4f} >= {expected:.4f}  {'OK' if passed else 'FAIL'}")
        if failures:
            ok = False
            for msg in failures:
                print(f"  FAIL: {msg}", file=sys.stderr)
    return ok


def _update_baselines(results: dict[str, golden_eval.EvalResult]) -> None:
    try:
        with open(BASELINES_PATH, encoding="utf-8") as f:
            baselines = json.load(f)
    except FileNotFoundError:
        baselines = {"format_version": 1}

    baselines["token_counter"] = tokens.counter_name()
    now = datetime.now(timezone.utc).isoformat()

    for set_name, result in results.items():
        old = baselines.get(set_name, {})
        warn_parts = []
        for metric in ("top1", "topk", "mrr_at_k"):
            new_val = getattr(result, metric)
            old_val = old.get(metric)
            if old_val is not None and new_val < old_val - BASELINE_EPSILON:
                warn_parts.append(f"{metric}: {old_val:.4f} -> {new_val:.4f}")
        if warn_parts:
            print(f"WARNING ({set_name}): ベースラインが下がります: {', '.join(warn_parts)}")

        baselines[set_name] = {
            "top1": result.top1,
            "topk": result.topk,
            "mrr_at_k": result.mrr_at_k,
            "recorded_at": now,
        }

    with open(BASELINES_PATH, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nbaselines.json を更新しました")


def main() -> int:
    parser = argparse.ArgumentParser(description="ゴールデンクエリ回帰計測")
    parser.add_argument("--set", required=True, choices=["dev", "holdout", "all"])
    bl_group = parser.add_mutually_exclusive_group()
    bl_group.add_argument("--check-baseline", action="store_true")
    bl_group.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    sets = ["dev", "holdout"] if args.set == "all" else [args.set]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        golden_eval.generate_corpus(CORPUS_DIR, tmp_path)
        conn = _build_index(tmp_path)
        try:
            results: dict[str, golden_eval.EvalResult] = {}
            for s in sets:
                show_details = s == "dev"
                results[s] = _run_set(conn, s, args.top_k, show_details)
        except _ValidationError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        finally:
            conn.close()

    if args.update_baseline:
        _update_baselines(results)
        return 0

    if args.check_baseline:
        return 0 if _check_baselines(results) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
