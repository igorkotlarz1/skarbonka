"""Features for the category classifier: cleaned text plus amount, weekday, type and account.

The text is the merchant name and the title without digits (card numbers, dates and store
numbers carry no category signal). Two text encoders: TF-IDF on character n-grams (default,
no extra install) and multilingual-e5 sentence embeddings (`uv sync --extra embeddings`).
"""

import math
import re
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from skarbonka.categorization.merchants import parse_counterparty
from skarbonka.categorization.rules import TransactionView

Backend = Literal["tfidf", "e5"]
E5_MODEL = "intfloat/multilingual-e5-small"

_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")
_CARD_NOISE = re.compile(r"\b(płatność kartą|nr karty|xx)\b", re.IGNORECASE)


def text_of(view: TransactionView) -> str:
    name = parse_counterparty(view.counterparty).name
    title = _CARD_NOISE.sub(" ", view.title)
    return _SPACES.sub(" ", _DIGITS.sub(" ", f"{name} {title}")).strip().lower()


def feature_matrix(views: Sequence[TransactionView]) -> np.ndarray[Any, np.dtype[np.object_]]:
    """One row per transaction: text, log amount, income flag, weekday, kind, account.

    The amount becomes a float here only as a model feature (its order of magnitude);
    money itself stays Decimal everywhere else.
    """
    rows = [
        [
            text_of(v),
            math.log1p(float(abs(v.amount))),
            1.0 if v.amount > 0 else 0.0,
            str(v.transaction_date.weekday()),
            v.operation_kind,
            v.account,
        ]
        for v in views
    ]
    return np.array(rows, dtype=object).reshape(len(rows), 6)


class E5Encoder(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """Sentence embeddings from a local multilingual-e5 model (downloaded once, cached)."""

    def __init__(self, model_name: str = E5_MODEL) -> None:
        self.model_name = model_name

    def fit(self, texts: Sequence[str], y: object = None) -> "E5Encoder":
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        embedded = _e5(self.model_name).encode(
            [f"query: {t}" for t in texts], normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(embedded, dtype=np.float32)


_E5_CACHE: dict[str, Any] = {}


def _e5(model_name: str) -> Any:
    if model_name not in _E5_CACHE:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise RuntimeError(
                "the e5 backend needs the embeddings extra: uv sync --extra embeddings"
            ) from exc
        _E5_CACHE[model_name] = SentenceTransformer(model_name, device="cpu")
    return _E5_CACHE[model_name]


def text_encoder(backend: Backend) -> Any:
    if backend == "e5":
        return E5Encoder()
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1)


def preprocessor(backend: Backend) -> ColumnTransformer:
    return ColumnTransformer([
        ("text", text_encoder(backend), 0),
        ("amount", StandardScaler(), [1, 2]),
        ("context", OneHotEncoder(handle_unknown="ignore"), [3, 4, 5]),
    ])  # fmt: skip
