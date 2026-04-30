"""Validation script for the YOLOv8 document classifier.

Loads a trained checkpoint and reports per-class accuracy on a validation set.

Usage:
    python ml/train/validate.py --checkpoint ml/models/doc_classifier.onnx --val-dir dataset/val/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report

from ml.inference.classifier import CLASS_NAMES, DocumentClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate document classifier")
    parser.add_argument(
        "--checkpoint", type=Path, required=True, help="Path to ONNX model file"
    )
    parser.add_argument(
        "--val-dir",
        type=Path,
        required=True,
        help="Validation directory with one subdirectory per class",
    )
    return parser.parse_args()


def evaluate(checkpoint: Path, val_dir: Path) -> dict[str, object]:
    """
    Run inference on all images in val_dir and report per-class accuracy.

    Args:
        checkpoint: Path to the ONNX classifier model.
        val_dir: Validation directory structured as val_dir/{class_name}/*.png

    Returns:
        Dict with keys: accuracy (float), report (str), per_class_accuracy (dict).
    """
    classifier = DocumentClassifier(model_path=checkpoint)
    y_true: list[int] = []
    y_pred: list[int] = []

    for class_dir in sorted(val_dir.iterdir()):
        if not class_dir.is_dir() or class_dir.name not in CLASS_NAMES:
            continue
        true_idx = CLASS_NAMES.index(class_dir.name)
        for img_path in sorted(class_dir.iterdir()):
            if img_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            image_bytes = img_path.read_bytes()
            try:
                result = classifier.classify(image_bytes)
                y_true.append(true_idx)
                y_pred.append(result.predicted_class)
            except ValueError:
                continue  # skip unreadable images

    if not y_true:
        return {"accuracy": 0.0, "report": "No images evaluated.", "per_class_accuracy": {}}

    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    accuracy = float(np.mean(y_true_arr == y_pred_arr))

    report_str: str = classification_report(
        y_true_arr,
        y_pred_arr,
        target_names=CLASS_NAMES,
        zero_division=0,
    )

    per_class: dict[str, float] = {}
    for idx, name in enumerate(CLASS_NAMES):
        mask = y_true_arr == idx
        if mask.sum() == 0:
            per_class[name] = 0.0
        else:
            per_class[name] = float(np.mean(y_pred_arr[mask] == idx))

    return {
        "accuracy": accuracy,
        "report": report_str,
        "per_class_accuracy": per_class,
    }


def main() -> None:
    args = parse_args()
    results = evaluate(checkpoint=args.checkpoint, val_dir=args.val_dir)
    accuracy = results["accuracy"]
    assert isinstance(accuracy, float)
    print(f"Overall accuracy: {accuracy:.4f} ({accuracy * 100:.2f}%)")
    print("\nPer-class report:")
    print(results["report"])
    target = 0.85
    status = "PASS" if accuracy >= target else "FAIL"
    print(f"\nTarget accuracy >= {target:.0%}: {status}")


if __name__ == "__main__":
    main()
