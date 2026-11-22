"""Honest evaluation: a split grouped by merchant, macro-F1 and per-class numbers.

Grouping by merchant means every test merchant is new to the model, which is exactly where
ML matters (repeat purchases are already handled by merchant memory). Accuracy alone would
flatter the dominant classes, so macro-F1 leads.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit

from skarbonka.categorization.classifier import MODEL_FILE, Prediction, train_model
from skarbonka.categorization.features import Backend
from skarbonka.categorization.synthetic_labels import LabelledExample

METRICS_FILE = "metrics.json"
SPLIT_ATTEMPTS = 50


def grouped_split(
    examples: Sequence[LabelledExample], test_size: float = 0.25, seed: int = 0
) -> tuple[list[LabelledExample], list[LabelledExample]]:
    """Train/test split with no merchant on both sides and every test label seen in training."""
    groups = [e.merchant for e in examples]
    splitter = GroupShuffleSplit(n_splits=SPLIT_ATTEMPTS, test_size=test_size, random_state=seed)
    for train_idx, test_idx in splitter.split(examples, groups=groups):
        train = [examples[i] for i in train_idx]
        test = [examples[i] for i in test_idx]
        if {e.label for e in test} <= {e.label for e in train}:
            return train, test
    raise ValueError("cannot split: some category has too few merchants")


def expected_calibration_error(
    confidence: Sequence[float], correct: Sequence[bool], bins: int = 10
) -> float:
    """Weighted gap between confidence and accuracy over equal-width confidence bins."""
    if not confidence:
        return 0.0
    total = 0.0
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidence) if low < c <= high or (b == 0 and c == 0)]
        if idx:
            accuracy = sum(correct[i] for i in idx) / len(idx)
            mean_conf = sum(confidence[i] for i in idx) / len(idx)
            total += len(idx) / len(confidence) * abs(accuracy - mean_conf)
    return total


def score(
    truth: Sequence[str], predictions: Sequence[Prediction], threshold: float
) -> dict[str, Any]:
    predicted = [p.category for p in predictions]
    labels = sorted(set(truth))
    precision, recall, f1, support = precision_recall_fscore_support(
        truth, predicted, labels=labels, zero_division=0
    )
    confident = [
        (t, p) for t, p in zip(truth, predictions, strict=True) if p.probability >= threshold
    ]
    macro_f1 = f1_score(truth, predicted, labels=labels, average="macro", zero_division=0)
    per_class = {
        label: {
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(float(f), 4),
            "support": int(s),
        }
        for label, p, r, f, s in zip(labels, precision, recall, f1, support, strict=True)
    }
    hits = sum(t == p.category for t, p in confident)
    hit = [t == p.category for t, p in zip(truth, predictions, strict=True)]
    conf = [p.probability for p in predictions]
    return {
        "n": len(truth),
        "macro_f1": round(float(macro_f1), 4),
        "accuracy": round(float(accuracy_score(truth, predicted)), 4),
        "threshold": threshold,
        "coverage_at_threshold": round(len(confident) / len(truth), 4) if truth else 0.0,
        "accuracy_at_threshold": round(hits / len(confident), 4) if confident else None,
        "expected_calibration_error": round(expected_calibration_error(conf, hit), 4),
        "per_class": per_class,
    }


def evaluate_backend(
    examples: Sequence[LabelledExample], backend: Backend, threshold: float, seed: int
) -> dict[str, Any]:
    train, test = grouped_split(examples, seed=seed)
    model = train_model(train, backend=backend)
    predictions = model.predict([e.view for e in test])
    return {
        "backend": backend,
        "calibrated": model.calibrated,
        "split": {
            "train": len(train),
            "test": len(test),
            "train_merchants": len({e.merchant for e in train}),
            "test_merchants": len({e.merchant for e in test}),
            "shared_merchants": len({e.merchant for e in train} & {e.merchant for e in test}),
        },
        "test": score([e.label for e in test], predictions, threshold),
    }


def train_and_evaluate(
    examples: Sequence[LabelledExample],
    models_dir: Path,
    backend: Backend = "tfidf",
    threshold: float = 0.8,
    seed: int = 0,
) -> dict[str, Any]:
    """Evaluate on a merchant-grouped split, then refit on everything and save model + metrics."""
    report = evaluate_backend(examples, backend, threshold, seed)
    model = train_model(examples, backend=backend)
    report |= {"trained_at": model.trained_at, "n_final": model.n_train, "labels": model.labels}
    models_dir.mkdir(parents=True, exist_ok=True)
    model.save(models_dir / MODEL_FILE)
    (models_dir / METRICS_FILE).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
