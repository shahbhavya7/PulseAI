# Classifier accuracy (held-out set)

Run on **18** labelled tickets from `tests/data/accuracy_set.jsonl` — a blind set authored to be diverse and **verified disjoint from the few-shot examples** in the prompt (so this measures generalisation, not recall of the examples).

- **Generated:** 2026-07-24 10:52 UTC
- **Overall accuracy:** 18/18 = **100%**
- **Taxonomy:** bug, feature_request, question, incident, other

## Per-category precision / recall

| Category | Precision | Recall | Support |
| --- | --- | --- | --- |
| bug | 100% | 100% | 4 |
| feature_request | 100% | 100% | 4 |
| question | 100% | 100% | 4 |
| incident | 100% | 100% | 5 |
| other | 100% | 100% | 1 |

## Confusion matrix (rows = gold, columns = predicted)

| gold \ pred | bug | feature_request | question | incident | other |
| --- | --- | --- | --- | --- | --- |
| **bug** | 4 | 0 | 0 | 0 | 0 |
| **feature_request** | 0 | 4 | 0 | 0 | 0 |
| **question** | 0 | 0 | 4 | 0 | 0 |
| **incident** | 0 | 0 | 0 | 5 | 0 |
| **other** | 0 | 0 | 0 | 0 | 1 |

## Misclassifications

None — every item was classified correctly.

## How to reproduce

```bash
export PULSE_OPENAI_API_KEY=sk-...   # needs a live key
python scripts/eval_accuracy.py
```

The harness (`scripts/eval_accuracy.py`) asserts the set is disjoint from the few-shot examples before scoring; if you edit either, re-run to refresh this file.

