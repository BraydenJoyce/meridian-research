# Model Card: YOLOv8 Document Classifier

**Version:** 1.0.0-pre (pre-production)
**Last updated:** 2026-04-29
**Status:** Architecture complete; awaiting production training data

---

## Model Summary

| Attribute | Value |
|---|---|
| Model family | Ultralytics YOLOv8n-cls |
| Task | Multi-class image classification |
| Input | RGB image (any resolution → resized to 224×224) |
| Output | Document class label + confidence score |
| Classes | 8 (see below) |
| Export format | ONNX (opset 17) for production inference |
| Runtime | ONNX Runtime via Modal GPU (T4) |
| Primary use | Meridian Research CV pipeline — classify chart images found in research sources |

The classifier is the first stage of the CV pipeline (ADR-005). It determines whether
an image from a research source is a structured data visualisation (bar chart, line
chart, pie chart, scatter plot, or table) warranting downstream Claude Vision extraction.

---

## Intended Use

### Primary use case

Given an image URL extracted from a web research source, classify the image into one
of 8 document categories. Images classified as `bar_chart`, `line_chart`, `pie_chart`,
`scatter_plot`, or `table` with confidence ≥ 0.70 are forwarded to the chart data
extractor. All other images are discarded.

### Intended users

- Meridian Research backend infrastructure (CvDocumentAgent)
- ML engineers maintaining the CV pipeline

### Out-of-scope uses

- General-purpose document classification outside of the Meridian Research pipeline
- Real-time video classification
- Classification of non-English charts where labels are critical to the classification
- Handwritten documents or very low-resolution scans (<50px on shortest side)

---

## Document Classes

| Class ID | Label | Description |
|---|---|---|
| 0 | `bar_chart` | Vertical or horizontal bar/column charts showing categorical comparisons |
| 1 | `line_chart` | Time-series or continuous line graphs |
| 2 | `pie_chart` | Circular proportional charts (pie, donut) |
| 3 | `scatter_plot` | XY scatter diagrams, bubble charts |
| 4 | `table` | Grid-layout data tables with rows and columns |
| 5 | `diagram` | Flowcharts, org charts, process diagrams, architecture diagrams |
| 6 | `infographic` | Mixed-media visual summaries combining text and graphic elements |
| 7 | `other` | Images that do not fall into the above categories |

Only classes 0–4 trigger downstream chart data extraction. Classes 5–7 are classified
and discarded.

---

## Model Architecture

### Base model

- **Architecture:** YOLOv8n-cls (nano classification variant)
- **Parameters:** ~1.5M (nano tier)
- **Pretrained weights:** `yolov8n-cls.pt` (ImageNet-1K pretrained backbone)
- **Fine-tuning strategy:** Full fine-tune on document classification dataset

### Why YOLOv8n-cls

The nano variant was chosen for production deployment on Modal GPU (T4) where cold-start
latency and per-inference cost are constraints. The document classification task does not
require the capacity of larger variants — high-frequency features (axes, grid lines, data
series colours) are sufficient discriminators at 224×224 resolution.

### Inference preprocessing

```python
# From ml/inference/classifier.py
import numpy as np
from PIL import Image
import io

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]
INPUT_SIZE    = 224

def _preprocess(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD      # ImageNet normalisation
    arr = arr.transpose(2, 0, 1)                     # HWC → CHW
    return arr[np.newaxis, ...]                      # add batch dim → NCHW
```

Softmax is applied to raw logits from the ONNX model output before returning probabilities.

---

## Training Data

### Data sources (planned)

Production training data has not yet been collected. The following sources are planned
for each class:

| Class | Planned data sources |
|---|---|
| `bar_chart` | SEC EDGAR annual reports (10-K), earnings presentation slides, Bloomberg chart exports |
| `line_chart` | Financial time-series plots from earnings reports, macroeconomic dashboards |
| `pie_chart` | Market share slides, portfolio allocation charts from fund factsheets |
| `scatter_plot` | Academic finance papers, equity research reports |
| `table` | SEC EDGAR financial statements, broker research tables, regulatory filings |
| `diagram` | Consulting slide decks, corporate org chart disclosures |
| `infographic` | Company investor relations materials, industry overview slides |
| `other` | Stock photos, logos, decorative images from web pages |

### Data collection requirements

- Minimum 500 images per class for initial training
- Target 2,000+ images per class for production accuracy
- Train/val split: 80%/20% (managed by `ml/train/dataset.py`)
- Images must be de-duplicated by perceptual hash before training
- Images sourced from live web scraping require manual verification of class labels

### Data not yet collected

**This model has not been trained on production data.** The training pipeline
(`ml/train/train.py`), inference pipeline (`ml/inference/classifier.py`), and Modal
deployment (`ml/inference/modal_app.py`) are complete and tested, but the model weights
currently reflect only the ImageNet-pretrained backbone without domain fine-tuning.

---

## Training Configuration

Training is managed by `ml/train/train.py` using the Ultralytics API.

### Default hyperparameters

| Parameter | Default value | CLI flag |
|---|---|---|
| Base model | `yolov8n-cls.pt` | `--model` |
| Epochs | 50 | `--epochs` |
| Image size | 224 | `--imgsz` |
| Batch size | 32 | `--batch` |
| Project dir | `ml/runs/classify` | `--project` |
| Run name | `doc_classifier` | `--name` |
| Output dir | `ml/models` | `--output-dir` |

Ultralytics applies its default optimizer (AdamW), learning-rate schedule (cosine
annealing), and data augmentation (random flip, HSV jitter, mosaic) unless overridden
via a config file. No additional overrides are applied in `train.py`.

### ONNX export configuration

After training, `export_onnx()` exports with:

```
format=onnx, opset=17, imgsz=224
```

The ONNX model is stored as `ml/models/doc_classifier.onnx` and tracked via Git LFS
(`.gitattributes`).

### Training command example

```bash
python ml/train/train.py \
    --data ml/data/dataset.yaml \
    --epochs 50 \
    --imgsz 224 \
    --batch 32 \
    --model yolov8n-cls.pt \
    --output-dir ml/models
```

---

## Evaluation Metrics

### Target accuracy

| Metric | Target |
|---|---|
| Top-1 accuracy (validation set) | > 85% |
| Per-class recall (all classes) | > 80% |

Evaluation is run via `ml/train/validate.py` using `sklearn.metrics.classification_report`.
The script prints PASS/FAIL against the 85% target.

### Per-class accuracy (placeholder — awaiting production training)

The table below shows the expected format after training on production data.
All values are **placeholder** until the model is trained.

| Class | Precision | Recall | F1-score | Support |
|---|---|---|---|---|
| `bar_chart` | — | — | — | — |
| `line_chart` | — | — | — | — |
| `pie_chart` | — | — | — | — |
| `scatter_plot` | — | — | — | — |
| `table` | — | — | — | — |
| `diagram` | — | — | — | — |
| `infographic` | — | — | — | — |
| `other` | — | — | — | — |
| **macro avg** | — | — | — | — |
| **accuracy** | | | — | — |

This table must be populated and committed before the model is used in production.

### Confidence threshold

CvDocumentAgent applies a confidence threshold of **0.70** before forwarding an image
to chart data extraction. Images classified with confidence < 0.70 are discarded even
if the predicted class is extractable. This threshold reduces false extractions at the
cost of some recall on borderline images.

### Confusion matrix

A confusion matrix plot is generated by `validate.py` as `ml/runs/validate/confusion_matrix.png`.
The matrix is not committed to the repository; it must be generated locally after training.

---

## Inference

### Using DocumentClassifier directly

```python
from pathlib import Path
from ml.inference.classifier import DocumentClassifier

# Load the ONNX model
classifier = DocumentClassifier(model_path=Path("ml/models/doc_classifier.onnx"))

# Classify an image from bytes
with open("my_chart.png", "rb") as f:
    image_bytes = f.read()

result = classifier.classify(image_bytes)

print(result.class_name)   # e.g. "bar_chart"
print(result.confidence)   # e.g. 0.94
print(result.all_scores)   # dict[str, float] for all 8 classes
```

### Via Modal API

The classifier is deployed as a Modal web endpoint. The CvDocumentAgent calls it
over HTTPS:

```python
import httpx

response = httpx.post(
    "https://<modal-app>.modal.run/classify",
    json={
        "image_url": "https://example.com/chart.png",
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
    },
    headers={"Authorization": "Bearer <MODAL_API_SECRET>"},
)

data = response.json()
# {
#   "image_url": "https://example.com/chart.png",
#   "doc_class": "bar_chart",
#   "confidence": 0.94,
#   "latency_ms": 38.2
# }
```

### Local / CI mode

Set `MODAL_BASE_URL=local` to disable all Modal HTTP calls. CvDocumentAgent returns
`chart_count=0` and `chart_results=[]` without making any network requests. Used in
CI pipelines and local development without Modal credentials.

---

## Limitations

### Not yet trained on production data

The most significant limitation: **no domain fine-tuning has been performed**. The
current ONNX weights are the ImageNet-pretrained backbone only. Classification accuracy
on real financial document images is unknown. The model **must not be used in production**
until trained on at least 500 labelled images per class.

### Known failure modes

| Failure mode | Expected behaviour | Mitigation |
|---|---|---|
| Scanned PDFs (rasterised at low DPI) | Low confidence on blurry images | Confidence threshold ≥ 0.70 discards uncertain predictions |
| Non-English documents | Class label text (axis labels, titles) may confuse visual features | Not mitigated — model is visual, not text-based; impact expected to be low |
| Dark-background images | ImageNet normalisation tuned for light backgrounds | Monitor per-class accuracy on dark-background examples after training |
| Very small images (<50px) | Upsampling artefacts after resize to 224×224 | CvDocumentAgent does not filter by image size — add a minimum-dimension check if needed |
| Composite images | An image containing multiple chart types may be misclassified | Manual inspection of low-confidence predictions |
| Animated GIFs | Only the first frame is decoded | Expected: rarely encountered in research sources |

### Confidence threshold trade-off

Setting the threshold at 0.70 means images with true class confidence between 0.50
and 0.70 are silently discarded. For sessions with many borderline images this reduces
chart coverage. The threshold was chosen to minimise spurious extractions; it can be
lowered to 0.60 if recall is found to be insufficient in production.

---

## Ethical Considerations

### Data sourcing

Training images sourced from public financial documents (SEC EDGAR, public earnings
slides) are generally in the public domain. Images from paywalled sources must not
be used for training without appropriate licensing.

### False positives (spurious chart extraction)

A false positive — classifying a non-chart image as a chart — causes the Claude Vision
chart extractor to run unnecessarily. This incurs cost (Anthropic API token usage) but
does not produce incorrect data in the report; the extractor returns `null` for images
that do not contain extractable chart data.

### False negatives (missed charts)

A false negative means a real chart is not extracted and its data does not appear in
the research report. This is the more material failure mode from a product quality
perspective. Recall must be monitored per-class after production training.

### Bias in training data

If training data skews toward a particular industry (e.g., technology sector), the
model may perform better on technology company charts than healthcare or energy sector
charts. Balanced collection across industries is recommended.

---

## Versioning and Artefact Storage

| Artefact | Location | Storage |
|---|---|---|
| Trained weights | `ml/models/doc_classifier.pt` | Git LFS |
| ONNX model | `ml/models/doc_classifier.onnx` | Git LFS |
| Training runs | `ml/runs/classify/doc_classifier/` | Not committed (gitignored) |
| Validation runs | `ml/runs/validate/` | Not committed (gitignored) |

When the model is retrained, increment the version in this model card, commit the new
ONNX file via Git LFS, and record accuracy metrics in the per-class accuracy table above.

---

## References

- Ultralytics YOLOv8 documentation: https://docs.ultralytics.com/
- ONNX opset 17 specification: https://onnx.ai/onnx/operators/
- ADR-005: CV pipeline architecture — `docs/adr/ADR-005-cv-pipeline-architecture.md`
- CvDocumentAgent implementation — `backend/app/agents/cv_document.py`
- DocumentClassifier implementation — `ml/inference/classifier.py`
- Modal inference server — `ml/inference/api.py`, `ml/inference/modal_app.py`
