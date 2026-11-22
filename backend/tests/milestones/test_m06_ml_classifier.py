"""M6 gate: classifier training and evaluation, calibration, pipeline order and review queue."""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.api.deps import get_category_model, get_ml_threshold, get_session
from skarbonka.api.main import create_app
from skarbonka.categorization.classifier import MODEL_FILE, CategoryModel, Prediction, train_model
from skarbonka.categorization.evaluate import grouped_split, train_and_evaluate
from skarbonka.categorization.rules import TransactionView
from skarbonka.categorization.seed import load_seed, seed
from skarbonka.categorization.synthetic_labels import synthetic_examples
from skarbonka.db.models import Allocation, Category, Transaction
from skarbonka.domain.categorize import categorize
from skarbonka.domain.imports import import_ing_file
from skarbonka.importers.synthetic_ing import (
    MAIN_ACCOUNT,
    SyntheticTransaction,
    generate_export,
    render_csv,
)

EXAMPLES = synthetic_examples(seed=6)
FURNITURE = "Dom/Meble i wyposażenie"


class FixedPredictor:
    """Stands in for a trained model: always the same category and probability."""

    def __init__(self, category: str, probability: float) -> None:
        self.category, self.probability = category, probability

    def predict(self, views: Sequence[TransactionView]) -> list[Prediction]:
        return [
            Prediction(self.category, self.probability, {self.category: self.probability})
            for _ in views
        ]


def card(counterparty: str, amount: str) -> SyntheticTransaction:
    return SyntheticTransaction(
        "card", date(2026, 5, 6), date(2026, 5, 7), counterparty,
        " Płatność kartą 06.05.2026 Nr karty 4246xx1234", "", "", "",
        Decimal(amount), MAIN_ACCOUNT,
    )  # fmt: skip


CRAFTED = {
    "manual": card(" KWIACIARNIA BEZ NAZWY  GLIWICE  POL ", "-31.00"),
    "rule": card(" CITY GYM  GLIWICE  POL ", "-99.00"),
    "merchant": card(" LIDL SKLEP  KATOWICE  POL ", "-54.20"),
    "ml": card(" PIEKARNIA U ZOSI  GLIWICE  POL ", "-12.40"),
}


def crafted_export() -> bytes:
    base = generate_export(seed=707, start=date(2026, 5, 1), end=date(2026, 5, 2))
    return render_csv(replace(base, transactions=tuple(CRAFTED.values())))


def path_of(session: Session, category_id: int | None) -> str | None:
    if category_id is None:
        return None
    category = session.get_one(Category, category_id)
    parent = session.get(Category, category.parent_id) if category.parent_id else None
    return f"{parent.name}/{category.name}" if parent else category.name


def allocation_for(session: Session, key: str) -> Allocation:
    marker = CRAFTED[key].counterparty.split()[1 if key == "rule" else 0]
    t = session.scalars(select(Transaction).where(Transaction.counterparty.contains(marker))).one()
    return t.allocations[0]


@pytest.fixture
def seeded(db: Session) -> Session:
    seed(db, load_seed())
    return db


def test_training_writes_model_and_metrics(tmp_path: Path) -> None:
    """Training on a synthetic labelled set writes a model and a metrics JSON to models/."""
    models_dir = tmp_path / "models"
    report = train_and_evaluate(EXAMPLES, models_dir, backend="tfidf", seed=1)

    assert (models_dir / MODEL_FILE).is_file()
    metrics = json.loads((models_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics == report
    assert metrics["backend"] == "tfidf"
    assert 0.5 < metrics["test"]["macro_f1"] <= 1.0
    assert set(metrics["test"]["per_class"]) == {e.label for e in EXAMPLES}
    assert CategoryModel.load(models_dir / MODEL_FILE).labels == sorted({e.label for e in EXAMPLES})


def test_evaluation_split_is_grouped_by_merchant() -> None:
    """No merchant appears in both the training and the test part."""
    train, test = grouped_split(EXAMPLES, test_size=0.25, seed=3)
    assert train
    assert test
    assert len(train) + len(test) == len(EXAMPLES)
    assert not {e.merchant for e in train} & {e.merchant for e in test}
    assert {e.label for e in test} <= {e.label for e in train}


def test_probabilities_are_calibrated() -> None:
    """Every class gets a probability and the probabilities sum to 1."""
    model = train_model(EXAMPLES, backend="tfidf")
    assert model.calibrated
    predictions = model.predict([e.view for e in EXAMPLES[:25]])
    for p in predictions:
        assert set(p.probabilities) == set(model.labels)
        assert all(0.0 <= v <= 1.0 for v in p.probabilities.values())
        assert sum(p.probabilities.values()) == pytest.approx(1.0)
        assert p.probability == max(p.probabilities.values())
        assert p.category == max(p.probabilities, key=lambda k: p.probabilities[k])


def test_manual_label_beats_ml(seeded: Session) -> None:
    """Layer 1: a manual allocation is never changed by the model."""
    import_ing_file(seeded, "crafted.csv", crafted_export())
    manual = allocation_for(seeded, "manual")
    manual.category_id, manual.source = None, "manual"

    categorize(seeded, model=FixedPredictor(FURNITURE, 0.99))

    assert (manual.category_id, manual.source) == (None, "manual")


def test_rule_beats_ml(seeded: Session) -> None:
    """Layer 2: a matching rule decides the category, not the model."""
    import_ing_file(seeded, "crafted.csv", crafted_export(), model=FixedPredictor(FURNITURE, 0.99))
    gym = allocation_for(seeded, "rule")
    assert (path_of(seeded, gym.category_id), gym.source) == ("Sport/Siłownia", "rule")


def test_merchant_memory_beats_ml(seeded: Session) -> None:
    """Layer 3: a known merchant's default category wins over the model."""
    import_ing_file(seeded, "crafted.csv", crafted_export(), model=FixedPredictor(FURNITURE, 0.99))
    lidl = allocation_for(seeded, "merchant")
    assert (path_of(seeded, lidl.category_id), lidl.source) == (
        "Jedzenie/Zakupy spożywcze",
        "merchant",
    )


def test_ml_labels_an_unknown_merchant_above_threshold(seeded: Session) -> None:
    """Layer 4: with nothing else matching, a confident model sets the category."""
    import_ing_file(seeded, "crafted.csv", crafted_export(), model=FixedPredictor(FURNITURE, 0.93))
    bakery = allocation_for(seeded, "ml")
    assert (path_of(seeded, bakery.category_id), bakery.source) == (FURNITURE, "ml")
    assert bakery.confidence == Decimal("0.930")
    assert bakery.personal is False


def test_below_threshold_goes_to_review_queue(seeded: Session) -> None:
    """Layer 5: an unsure prediction leaves the category empty and waits in the review queue."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: seeded
    app.dependency_overrides[get_category_model] = lambda: FixedPredictor(FURNITURE, 0.41)
    app.dependency_overrides[get_ml_threshold] = lambda: 0.8
    with TestClient(app) as client:
        files = [("files", ("crafted.csv", crafted_export(), "text/csv"))]
        assert client.post("/imports", files=files).status_code == 200
        bakery = allocation_for(seeded, "ml")
        assert bakery.category_id is None
        assert path_of(seeded, bakery.suggested_category_id) == FURNITURE
        assert bakery.confidence == Decimal("0.410")

        queue = client.get("/review-queue").json()
    row = next(r for r in queue if r["transaction_id"] == bakery.transaction_id)
    assert row["suggested_category"] == FURNITURE
    assert Decimal(row["confidence"]) == Decimal("0.410")
    assert all(r["transaction_id"] != allocation_for(seeded, "merchant").transaction_id
               for r in queue)  # fmt: skip
