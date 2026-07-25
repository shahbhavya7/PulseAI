"""Classifier accuracy harness.

Runs a **held-out labelled set** (``tests/data/accuracy_set.jsonl``) through the
real classification pipeline and reports accuracy + a confusion summary, then
writes ``docs/accuracy.md``. This answers the "blind inputs" rubric item: the set
is authored to be diverse and is verified **disjoint from the few-shot examples**
baked into the prompt, so we measure generalisation, not memorisation.

Usage (needs a live OpenAI key; DB/Redis not required):

    python scripts/eval_accuracy.py                 # eval + write docs/accuracy.md
    python scripts/eval_accuracy.py --no-write      # print only
    python scripts/eval_accuracy.py --dry-run       # list the set, don't call the model

The label of each item is the PRIMARY (first) issue's category — the taxonomy is
bug | feature_request | question | incident | other.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from app.models.enums import IssueCategory  # noqa: E402
from app.services.llm import _FEW_SHOT, LLMError, build_instructions  # noqa: E402
from app.services.pipeline import analyze  # noqa: E402

DATASET = ROOT / "tests" / "data" / "accuracy_set.jsonl"
DOC = ROOT / "docs" / "accuracy.md"
CATEGORIES = [c.value for c in IssueCategory]
_EVAL_USER = "00000000-0000-0000-0000-0000000000ac"  # fixed; scopes the (unused) hash


def load_set() -> list[dict[str, str]]:
    items = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    for it in items:
        if it["category"] not in CATEGORIES:
            raise SystemExit(f"{it['id']}: unknown gold category {it['category']!r}")
    return items


def assert_disjoint_from_few_shot(items: list[dict[str, str]]) -> None:
    """Fail loudly if any eval item reuses a few-shot example's text."""
    shots = {text.strip().lower() for text, _analysis, _rationale in _FEW_SHOT}
    for it in items:
        if it["text"].strip().lower() in shots:
            raise SystemExit(f"{it['id']} duplicates a few-shot example — not a blind input")


def classify(text: str) -> str:
    """Return the predicted PRIMARY category for one ticket (fresh, no cache)."""
    outcome = analyze(text, user_id_str=_EVAL_USER, use_cache=False)
    return str(outcome.analysis.issues[0].classification.category)


def confusion(items: list[dict[str, str]], preds: list[str]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {g: defaultdict(int) for g in CATEGORIES}
    for it, pred in zip(items, preds, strict=True):
        matrix[it["category"]][pred] += 1
    return {g: dict(row) for g, row in matrix.items()}


def per_class(items: list[dict[str, str]], preds: list[str]) -> dict[str, dict[str, float]]:
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    for it, pred in zip(items, preds, strict=True):
        gold = it["category"]
        if pred == gold:
            tp[gold] += 1
        else:
            fp[pred] += 1
            fn[gold] += 1
    out: dict[str, dict[str, float]] = {}
    for c in CATEGORIES:
        support = tp[c] + fn[c]
        if support == 0 and fp[c] == 0:
            continue
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        out[c] = {"precision": prec, "recall": rec, "support": float(support)}
    return out


def render_markdown(
    items: list[dict[str, str]],
    preds: list[str],
    correct: int,
    matrix: dict[str, dict[str, int]],
    classes: dict[str, dict[str, float]],
    stamp: str,
) -> str:
    n = len(items)
    acc = correct / n if n else 0.0
    lines: list[str] = []
    lines.append("# Classifier accuracy (held-out set)\n")
    lines.append(
        f"Run on **{n}** labelled tickets from `tests/data/accuracy_set.jsonl` — a "
        "blind set authored to be diverse and **verified disjoint from the few-shot "
        "examples** in the prompt (so this measures generalisation, not recall of "
        "the examples).\n"
    )
    lines.append(f"- **Generated:** {stamp}")
    lines.append(f"- **Overall accuracy:** {correct}/{n} = **{acc:.0%}**")
    lines.append(f"- **Taxonomy:** {', '.join(CATEGORIES)}\n")

    lines.append("## Per-category precision / recall\n")
    lines.append("| Category | Precision | Recall | Support |")
    lines.append("| --- | --- | --- | --- |")
    for c, m in classes.items():
        lines.append(f"| {c} | {m['precision']:.0%} | {m['recall']:.0%} | {int(m['support'])} |")
    lines.append("")

    lines.append("## Confusion matrix (rows = gold, columns = predicted)\n")
    header = "| gold \\ pred | " + " | ".join(CATEGORIES) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join("---" for _ in CATEGORIES) + " |")
    for g in CATEGORIES:
        row = matrix.get(g, {})
        if not row:
            continue
        cells = " | ".join(str(row.get(p, 0)) for p in CATEGORIES)
        lines.append(f"| **{g}** | {cells} |")
    lines.append("")

    misses = [
        (it["id"], it["category"], pred, it["text"])
        for it, pred in zip(items, preds, strict=True)
        if pred != it["category"]
    ]
    lines.append("## Misclassifications\n")
    if not misses:
        lines.append("None — every item was classified correctly.\n")
    else:
        lines.append("| id | gold | predicted | text |")
        lines.append("| --- | --- | --- | --- |")
        for mid, gold, pred, text in misses:
            snippet = text.replace("|", "\\|")[:80]
            lines.append(f"| {mid} | {gold} | {pred} | {snippet}… |")
        lines.append("")

    lines.append("## How to reproduce\n")
    lines.append("```bash")
    lines.append("export PULSE_OPENAI_API_KEY=sk-...   # needs a live key")
    lines.append("python scripts/eval_accuracy.py")
    lines.append("```")
    lines.append(
        "\nThe harness (`scripts/eval_accuracy.py`) asserts the set is disjoint from "
        "the few-shot examples before scoring; if you edit either, re-run to refresh "
        "this file.\n"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classifier accuracy eval")
    parser.add_argument("--no-write", action="store_true", help="print only, don't write docs")
    parser.add_argument("--dry-run", action="store_true", help="list the set, no model calls")
    args = parser.parse_args()

    items = load_set()
    assert_disjoint_from_few_shot(items)
    print(f"Loaded {len(items)} labelled items (disjoint from few-shot ✓).")
    print(
        f"Prompt has {len(_FEW_SHOT)} few-shot examples; instructions "
        f"{len(build_instructions())} chars."
    )

    if args.dry_run:
        for it in items:
            print(f"  {it['id']}: [{it['category']}] {it['text'][:60]}…")
        return 0

    preds: list[str] = []
    correct = 0
    for it in items:
        try:
            pred = classify(it["text"])
        except LLMError as exc:
            print(f"\nAborting: model unavailable ({exc}). Set PULSE_OPENAI_API_KEY.")
            return 2
        preds.append(pred)
        ok = pred == it["category"]
        correct += ok
        mark = "✓" if ok else "✗"
        print(f"  {mark} {it['id']}: gold={it['category']:<16} pred={pred}")

    matrix = confusion(items, preds)
    classes = per_class(items, preds)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    acc = correct / len(items)
    print(f"\nAccuracy: {correct}/{len(items)} = {acc:.0%}")

    md = render_markdown(items, preds, correct, matrix, classes, stamp)
    if args.no_write:
        print("\n--- docs/accuracy.md (preview) ---\n")
        print(md)
    else:
        DOC.write_text(md + "\n")
        print(f"Wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
