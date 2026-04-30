"""Modal serverless deployment for the Meridian CV inference server (ADR-005).

Deployment:
    modal deploy ml/inference/modal_app.py

Dry-run validation:
    modal deploy ml/inference/modal_app.py --dry-run
"""
from __future__ import annotations

import modal

# ─────────────────────────────────────────────
# Modal app definition
# ─────────────────────────────────────────────

app = modal.App("meridian-cv-prod")

_cv_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libglib2.0-0", "libsm6", "libxext6", "libgl1")
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "httpx>=0.27.0",
        "onnxruntime>=1.17.0",
        "pillow>=11.0.0",
        "numpy>=1.26.0",
        "anthropic==0.40.0",
        "pydantic>=2.0.0",
        "structlog>=24.0.0",
    )
)

_anthropic_secret = modal.Secret.from_name("meridian-anthropic-secret")
_backend_secret = modal.Secret.from_name("meridian-backend-secret")

# ─────────────────────────────────────────────
# Classifier endpoint (GPU T4)
# ─────────────────────────────────────────────

_ONNX_MODEL_PATH = "/models/doc_classifier.onnx"


@app.cls(
    gpu="T4",
    image=_cv_image,
    secrets=[_backend_secret],
)
class ClassifierService:
    @modal.enter()
    def load(self) -> None:
        import sys

        sys.path.insert(0, "/app")
        from ml.inference.classifier import DocumentClassifier  # type: ignore[import]

        self._clf = DocumentClassifier(model_path=_ONNX_MODEL_PATH)

    @modal.web_endpoint(method="GET", label="health")
    def health(self) -> dict[str, str]:
        return {"status": "ok", "model": "yolov8n-cls-onnx"}

    @modal.web_endpoint(method="POST", label="classify")
    async def classify(self, request: dict[str, str]) -> dict[str, object]:
        import time

        import httpx

        # Auth is validated at the Modal gateway level via the backend secret.
        image_url = request.get("image_url", "")
        if not image_url.startswith(("http://", "https://")):
            return {"error": "invalid_image_url"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
            except Exception as exc:
                return {"error": "image_fetch_failed", "detail": str(exc)}

        t0 = time.perf_counter()
        try:
            result = self._clf.classify(image_bytes)
        except Exception as exc:
            return {"error": "inference_error", "detail": str(exc)}
        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "image_url": image_url,
            "doc_class": result.class_name,
            "confidence": result.confidence,
            "latency_ms": latency_ms,
        }


# ─────────────────────────────────────────────
# Chart extractor endpoint (no GPU)
# ─────────────────────────────────────────────


@app.cls(
    image=_cv_image,
    secrets=[_anthropic_secret, _backend_secret],
)
class ChartExtractorService:
    @modal.enter()
    def load(self) -> None:
        import sys

        sys.path.insert(0, "/app")
        from ml.inference.chart_extractor import ChartExtractor  # type: ignore[import]

        self._extractor = ChartExtractor()

    @modal.web_endpoint(method="POST", label="extract-chart")
    async def extract_chart(self, request: dict[str, str]) -> dict[str, object] | None:
        import httpx

        image_url = request.get("image_url", "")
        source_url = request.get("source_url", "")
        doc_class = request.get("doc_class", "")
        _extractable = {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}

        if doc_class not in _extractable:
            return {"error": "unsupported_doc_class"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
            except Exception as exc:
                return {"error": "image_fetch_failed", "detail": str(exc)}

        chart_result = await self._extractor.extract(
            image_bytes=image_bytes,
            doc_class=doc_class,
            source_url=source_url,
            image_url=image_url,
        )
        if chart_result is None:
            return None
        return chart_result.model_dump()
