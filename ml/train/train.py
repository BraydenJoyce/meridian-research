"""YOLOv8 document classifier training script.

Usage:
    python ml/train/train.py --epochs 50 --imgsz 224 --batch 32 --data path/to/dataset.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLOv8 document classifier")
    parser.add_argument("--data", type=Path, required=True, help="Path to dataset YAML")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=224, help="Input image size")
    parser.add_argument("--batch", type=int, default=32, help="Batch size")
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n-cls.pt",
        help="Base model checkpoint (default: yolov8n-cls.pt)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/models"),
        help="Directory to save trained model artifacts",
    )
    parser.add_argument(
        "--project",
        type=str,
        default="ml/runs/classify",
        help="Project directory for ultralytics run artifacts",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="doc_classifier",
        help="Run name within the project directory",
    )
    return parser.parse_args()


def train(
    data: Path,
    epochs: int = 50,
    imgsz: int = 224,
    batch: int = 32,
    model: str = "yolov8n-cls.pt",
    output_dir: Path = Path("ml/models"),
    project: str = "ml/runs/classify",
    name: str = "doc_classifier",
) -> Path:
    """
    Fine-tune a YOLOv8 classification model on the document dataset.

    Args:
        data: Path to the ultralytics dataset YAML.
        epochs: Number of training epochs.
        imgsz: Input image resolution (square).
        batch: Training batch size.
        model: Base model name or checkpoint path.
        output_dir: Directory to copy the final .pt and exported .onnx files.
        project: ultralytics project directory for run artifacts.
        name: Run name within the project directory.

    Returns:
        Path to the exported ONNX model file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    yolo = YOLO(model)
    yolo.train(
        data=str(data),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        exist_ok=True,
    )

    best_pt: Path = Path(project) / name / "weights" / "best.pt"
    dest_pt = output_dir / "doc_classifier.pt"
    if best_pt.exists():
        import shutil
        shutil.copy2(best_pt, dest_pt)

    onnx_path = export_onnx(dest_pt, imgsz=imgsz)
    return onnx_path


def export_onnx(checkpoint: Path, imgsz: int = 224) -> Path:
    """
    Export a trained YOLOv8 classification checkpoint to ONNX format.

    Args:
        checkpoint: Path to the .pt checkpoint file.
        imgsz: Image size used during training.

    Returns:
        Path to the exported .onnx file (same directory as checkpoint).
    """
    yolo = YOLO(str(checkpoint))
    yolo.export(format="onnx", opset=17, imgsz=imgsz)
    onnx_path = checkpoint.with_suffix(".onnx")
    return onnx_path


def main() -> None:
    args = parse_args()
    onnx_path = train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        model=args.model,
        output_dir=args.output_dir,
        project=args.project,
        name=args.name,
    )
    print(f"Training complete. ONNX model exported to: {onnx_path}")


if __name__ == "__main__":
    main()
