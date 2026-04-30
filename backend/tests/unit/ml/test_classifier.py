"""Tests for the YOLOv8 document classifier inference module."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

# Make ml/ importable from this test file
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from ml.inference.classifier import CLASS_NAMES, ClassificationResult, DocumentClassifier


def _make_png_bytes(width: int = 64, height: int = 64) -> bytes:
    """Create a minimal valid PNG image as bytes."""
    img = Image.new("RGB", (width, height), color=(128, 64, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_mock_session(logits: list[float] | None = None) -> MagicMock:
    """Return a mock ort.InferenceSession that returns fixed logits."""
    if logits is None:
        logits = [2.0, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]  # bar_chart wins
    session = MagicMock()
    session.get_inputs.return_value = [MagicMock(name="images")]
    outputs = np.array([logits], dtype=np.float32)
    session.run.return_value = [outputs]
    return session


@pytest.fixture()
def classifier(monkeypatch: pytest.MonkeyPatch) -> DocumentClassifier:
    """DocumentClassifier with a monkeypatched ort.InferenceSession."""
    mock_session = _build_mock_session()
    monkeypatch.setattr(
        "ml.inference.classifier.ort.InferenceSession",
        lambda *args, **kwargs: mock_session,
        raising=True,
    )
    # Use a dummy path — session is mocked so the file need not exist
    return DocumentClassifier(model_path="dummy.onnx")


def test_classify_returns_classification_result(classifier: DocumentClassifier) -> None:
    result = classifier.classify(_make_png_bytes())

    assert isinstance(result, ClassificationResult)
    assert 0.0 <= result.confidence <= 1.0
    assert result.class_name in CLASS_NAMES


def test_all_scores_sum_to_one(classifier: DocumentClassifier) -> None:
    result = classifier.classify(_make_png_bytes())

    total = sum(result.all_scores.values())
    assert abs(total - 1.0) < 1e-5


def test_class_name_matches_predicted_class(classifier: DocumentClassifier) -> None:
    result = classifier.classify(_make_png_bytes())

    assert result.class_name == CLASS_NAMES[result.predicted_class]


def test_invalid_bytes_raises_value_error(classifier: DocumentClassifier) -> None:
    with pytest.raises(ValueError):
        classifier.classify(b"this is not an image")
