"""Calibrated category classifier (M6): logistic regression over text and context features.

The model only proposes a category. The pipeline decides what to do with the proposal
(apply it above the threshold, otherwise leave it as a suggestion for the review queue).
The personal flag is never predicted: it changes what the parents pay, so it stays with
rules and the owner.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from skarbonka.categorization.features import Backend, feature_matrix, preprocessor
from skarbonka.categorization.rules import TransactionView
from skarbonka.categorization.synthetic_labels import LabelledExample

MODEL_FILE = "category-model.joblib"
CALIBRATION_FOLDS = 3


@dataclass(frozen=True)
class Prediction:
    category: str
    probability: float
    probabilities: dict[str, float]


class CategoryPredictor(Protocol):
    def predict(self, views: Sequence[TransactionView]) -> list[Prediction]: ...


@dataclass
class CategoryModel:
    pipeline: Any
    backend: Backend
    labels: list[str]
    calibrated: bool
    n_train: int
    trained_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def predict(self, views: Sequence[TransactionView]) -> list[Prediction]:
        if not views:
            return []
        matrix = self.pipeline.predict_proba(feature_matrix(views))
        classes = [str(c) for c in self.pipeline.classes_]
        predictions = []
        for row in matrix:
            probabilities = {c: float(p) for c, p in zip(classes, row, strict=True)}
            best = max(probabilities, key=lambda c: probabilities[c])
            predictions.append(Prediction(best, probabilities[best], probabilities))
        return predictions

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "CategoryModel":
        # joblib unpickles: only ever load a model the owner trained locally into `models/`
        # (`skarbonka train`); never a file downloaded or received from someone else.
        model = joblib.load(path)
        if not isinstance(model, CategoryModel):
            raise TypeError(f"{path.name} is not a Skarbonka category model")
        return model


def train_model(examples: Sequence[LabelledExample], backend: Backend = "tfidf") -> CategoryModel:
    """Fit on all examples, calibrated by temperature scaling when every class has enough
    examples, otherwise plain (already probabilistic) logistic regression.

    Temperature scaling keeps the multiclass softmax intact. Sigmoid (one-vs-rest) calibration
    was tried first and made the model badly underconfident: 98% accurate on new merchants,
    yet only 30% of predictions reached 0.8 (expected calibration error 0.30 vs 0.11).
    """
    labels = [e.label for e in examples]
    smallest = min(Counter(labels).values())
    base = LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced")
    calibrated = smallest >= CALIBRATION_FOLDS
    classifier = (
        CalibratedClassifierCV(base, method="temperature", cv=CALIBRATION_FOLDS)
        if calibrated
        else base
    )
    pipeline = Pipeline([("features", preprocessor(backend)), ("classifier", classifier)])
    pipeline.fit(feature_matrix([e.view for e in examples]), labels)
    return CategoryModel(
        pipeline=pipeline,
        backend=backend,
        labels=sorted(set(labels)),
        calibrated=calibrated,
        n_train=len(examples),
    )
