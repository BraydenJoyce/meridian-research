"""YOLOv8 document classifier inference using ONNX runtime."""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import structlog
from PIL import Image
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)

CLASS_NAMES: list[str] = [
    "bar_chart",
    "line_chart",
    "pie_chart",
    "scatter_plot",
    "table",
    "diagram",
    "infographic",
    "other",
]

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ClassificationResult(BaseModel):
    """Result of document classification by the ONNX model."""

    predicted_class: int = Field(..., ge=0, lt=8, description="Class index 0–7")
    class_name: str = Field(..., description="Human-readable class name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Softmax confidence 0–1")
    all_scores: dict[str, float] = Field(
        ..., description="Softmax score for each of the 8 classes"
    )

    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, v: str) -> str:
        if v not in CLASS_NAMES:
            raise ValueError(f"class_name must be one of {CLASS_NAMES}, got {v!r}")
        return v


def _preprocess(image_bytes: bytes) -> np.ndarray:
    """Resize, normalize, and reshape image bytes into (1, 3, 224, 224) NCHW float32."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Cannot decode image bytes: {exc}") from exc
    img = img.resize((224, 224), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    return arr[np.newaxis, ...]   # (1, 3, 224, 224)


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - np.max(logits))
    return e / e.sum()


class DocumentClassifier:
    """
    Classifies document images into 8 categories using a YOLOv8-cls ONNX model.

    Loads the ONNX model once at construction. Thread-safe for concurrent inference
    calls (onnxruntime InferenceSession is thread-safe after creation).
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        if model_path is None:
            default = Path(__file__).parent.parent / "models" / "doc_classifier.onnx"
            model_path = default
        model_path = Path(model_path)

        providers: list[str] = ["CPUExecutionProvider"]
        if os.environ.get("ONNXRUNTIME_PROVIDERS") != "CPUExecutionProvider":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

        self._session: ort.InferenceSession = ort.InferenceSession(
            str(model_path), providers=providers
        )
        self._input_name: str = self._session.get_inputs()[0].name
        logger.info("DocumentClassifier loaded", model_path=str(model_path))

    def classify(self, image_bytes: bytes) -> ClassificationResult:
        """
        Classify a single image from raw bytes.

        Args:
            image_bytes: Raw image bytes (PNG, JPEG, WEBP, etc.)

        Returns:
            ClassificationResult with the predicted class and confidence scores.

        Raises:
            ValueError: If image_bytes cannot be decoded as an image.
        """
        arr = _preprocess(image_bytes)  # raises ValueError on bad bytes
        outputs: list[Any] = self._session.run(None, {self._input_name: arr})
        logits: np.ndarray = outputs[0][0]  # shape: (8,)
        probs = _softmax(logits)
        class_idx = int(np.argmax(probs))
        return ClassificationResult(
            predicted_class=class_idx,
            class_name=CLASS_NAMES[class_idx],
            confidence=float(probs[class_idx]),
            all_scores={name: float(probs[i]) for i, name in enumerate(CLASS_NAMES)},
        )
