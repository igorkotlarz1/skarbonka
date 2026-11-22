"""Classifier plumbing: labels from the database, CLI output, model loading."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from skarbonka.api import deps
from skarbonka.categorization.classifier import MODEL_FILE
from skarbonka.categorization.evaluate import expected_calibration_error
from skarbonka.categorization.features import text_of
from skarbonka.categorization.seed import load_seed, seed
from skarbonka.categorization.synthetic_labels import synthetic_examples
from skarbonka.cli import main
from skarbonka.config import Settings
from skarbonka.domain.imports import import_ing_file
from skarbonka.domain.training import labelled_examples
from tests.milestones.test_m05_merchants_rules import HALF_YEAR, fixture


def test_text_drops_digits_and_card_noise() -> None:
    view = synthetic_examples(seed=1)[0].view
    text = text_of(view)
    assert not any(ch.isdigit() for ch in text)
    assert "karty" not in text
    assert "pol" not in text.split()


def test_calibration_error_is_zero_when_confidence_matches_accuracy() -> None:
    assert expected_calibration_error([0.75] * 4, [True, True, True, False]) == pytest.approx(0)
    assert expected_calibration_error([1.0, 1.0], [False, False]) == pytest.approx(1.0)


def test_labels_come_from_rules_merchants_and_manual_never_transfers(db: Session) -> None:
    seed(db, load_seed())
    import_ing_file(db, "half-year.csv", HALF_YEAR)
    import_ing_file(db, "two_accounts.csv", fixture("two_accounts"))
    examples, sources = labelled_examples(db)
    assert examples
    assert set(sources) <= {"manual", "rule", "merchant"}
    assert "Przelewy własne" not in {e.label for e in examples}


def test_train_command_writes_model_and_prints_only_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["train", "--synthetic", "--models-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / MODEL_FILE).is_file()
    assert "Macro-F1" in out
    assert "Płatność" not in out  # no transaction text


def test_model_dependency_loads_the_saved_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(database_url="postgresql+psycopg://x@localhost/x", models_dir=tmp_path)
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    assert deps.get_category_model() is None
    assert main(["train", "--synthetic", "--models-dir", str(tmp_path)]) == 0
    model = deps.get_category_model()
    assert model is not None
    assert model.predict([synthetic_examples(seed=2)[0].view])[0].probability > 0
