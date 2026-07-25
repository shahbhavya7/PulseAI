"""Guards for the accuracy harness (no model calls).

The eval itself needs a live key and is run manually (`scripts/eval_accuracy.py`
→ `docs/accuracy.md`). These tests keep the *harness* honest in CI: the dataset
is well-formed, uses only valid categories, and stays disjoint from the few-shot
examples — so the reported accuracy always reflects blind inputs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_harness() -> object:
    spec = importlib.util.spec_from_file_location(
        "eval_accuracy", ROOT / "scripts" / "eval_accuracy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dataset_valid_and_blind() -> None:
    harness = _load_harness()
    items = harness.load_set()  # type: ignore[attr-defined]
    assert len(items) >= 10, "need at least 10 blind inputs (rubric)"
    # Every gold label is a real category (load_set raises otherwise, but be explicit).
    valid = set(harness.CATEGORIES)  # type: ignore[attr-defined]
    assert all(it["category"] in valid for it in items)
    # The core guarantee: no eval item reuses a few-shot example.
    harness.assert_disjoint_from_few_shot(items)  # type: ignore[attr-defined]


def test_dataset_covers_every_category() -> None:
    harness = _load_harness()
    items = harness.load_set()  # type: ignore[attr-defined]
    seen = {it["category"] for it in items}
    assert seen == set(harness.CATEGORIES), f"missing categories: {set(harness.CATEGORIES) - seen}"
