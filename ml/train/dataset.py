"""Dataset utilities for the YOLOv8 document classifier."""
from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

import yaml

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


def build_dataset_yaml(dataset_root: Path, output_path: Path) -> None:
    """
    Generate a dataset YAML file for ultralytics YOLOv8 classification training.

    Expects dataset_root to have train/ and val/ subdirectories, each containing
    one subdirectory per class named with the class name.

    Args:
        dataset_root: Path to the root of the image dataset.
        output_path: Path where the YAML file will be written.
    """
    config = {
        "path": str(dataset_root.resolve()),
        "train": "train",
        "val": "val",
        "nc": len(CLASS_NAMES),
        "names": CLASS_NAMES,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def compute_class_distribution(dataset_dir: Path) -> dict[str, int]:
    """
    Count the number of images per class in a dataset directory.

    Args:
        dataset_dir: Path to a split directory (e.g., dataset/train/).
            Expected structure: dataset_dir/{class_name}/*.{png,jpg,jpeg,webp}

    Returns:
        Dict mapping class name to image count.
    """
    counts: Counter[str] = Counter()
    for class_dir in sorted(dataset_dir.iterdir()):
        if not class_dir.is_dir():
            continue
        images = [
            f
            for f in class_dir.iterdir()
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        ]
        counts[class_dir.name] = len(images)
    return dict(counts)


def organize_images(
    source_dir: Path, dataset_root: Path, val_fraction: float = 0.2
) -> None:
    """
    Organize flat image files into train/val splits under dataset_root.

    Image files must be named {class_name}_{index}.{ext} (e.g. bar_chart_001.png).

    Args:
        source_dir: Directory of flat image files.
        dataset_root: Destination root (train/ and val/ will be created here).
        val_fraction: Fraction of images to reserve for validation (default 0.2).
    """
    import random

    by_class: dict[str, list[Path]] = {c: [] for c in CLASS_NAMES}
    for img in sorted(source_dir.iterdir()):
        if img.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        for cls in CLASS_NAMES:
            if img.stem.startswith(cls):
                by_class[cls].append(img)
                break

    for cls, images in by_class.items():
        random.shuffle(images)
        n_val = max(1, int(len(images) * val_fraction))
        splits = {"val": images[:n_val], "train": images[n_val:]}
        for split, split_images in splits.items():
            dest = dataset_root / split / cls
            dest.mkdir(parents=True, exist_ok=True)
            for img in split_images:
                shutil.copy2(img, dest / img.name)
