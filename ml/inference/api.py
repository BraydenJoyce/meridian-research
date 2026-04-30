"""FastAPI application for the Meridian CV inference server.

This module is importable independently of Modal — used in tests and local dev.
The Modal deployment in modal_app.py wraps this app.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────


class ClassifyRequest(BaseModel):
    image_url: str = Field(..., max_length=2048)
    session_id: str = Field(..., description="UUID v4 string for structured logging")


class ClassifyResponse(BaseModel):
    image_url: str
    doc_class: str
    confidence: float
    latency_ms: float


class ExtractChartRequest(BaseModel):
    image_url: str = Field(..., max_length=2048)
    session_id: str
    source_url: str = Field(..., max_length=2048)
    doc_class: str


_EXTRACTABLE_CLASSES = frozenset(
    {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}
)

# ─────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────


def create_app(
    classifier: Any | None = None,
    chart_extractor: Any | None = None,
) -> FastAPI:
    """
    Create the FastAPI inference app.

    Args:
        classifier: Optional pre-built DocumentClassifier (injected in tests).
        chart_extractor: Optional pre-built ChartExtractor (injected in tests).

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(title="Meridian CV Inference Server", version="1.0.0")

    # Store dependencies on app state so endpoints can access them
    app.state.classifier = classifier
    app.state.chart_extractor = chart_extractor

    _modal_api_secret: str = os.environ.get("MODAL_API_SECRET", "")

    def _verify_auth(request: Request) -> None:
        if not _modal_api_secret:
            return  # Auth disabled when secret not configured (local dev / tests)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {_modal_api_secret}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "unauthorized"},
            )

    async def _fetch_image(image_url: str) -> bytes:
        """Download image bytes from a URL. Raises HTTPException on failure."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                if len(resp.content) > 10 * 1024 * 1024:
                    raise HTTPException(
                        status_code=422,
                        detail={"error": "image_too_large"},
                    )
                return resp.content
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "image_fetch_failed", "detail": str(exc)},
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "image_fetch_failed", "detail": str(exc)},
            ) from exc

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "model": "yolov8n-cls-onnx"}

    @app.post("/classify", response_model=ClassifyResponse)
    async def classify(body: ClassifyRequest, request: Request) -> ClassifyResponse:
        _verify_auth(request)
        clf = request.app.state.classifier
        if clf is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "inference_error", "detail": "Classifier not loaded"},
            )
        image_bytes = await _fetch_image(body.image_url)
        t0 = time.perf_counter()
        try:
            result = clf.classify(image_bytes)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_image_url", "detail": str(exc)},
            ) from exc
        except Exception as exc:
            logger.error("classifier_inference_error", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail={"error": "inference_error", "detail": str(exc)},
            ) from exc
        latency_ms = (time.perf_counter() - t0) * 1000
        return ClassifyResponse(
            image_url=body.image_url,
            doc_class=result.class_name,
            confidence=result.confidence,
            latency_ms=latency_ms,
        )

    @app.post("/extract-chart")
    async def extract_chart(
        body: ExtractChartRequest, request: Request
    ) -> JSONResponse:
        _verify_auth(request)
        if body.doc_class not in _EXTRACTABLE_CLASSES:
            raise HTTPException(
                status_code=422,
                detail={"error": "unsupported_doc_class"},
            )
        extractor = request.app.state.chart_extractor
        if extractor is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "claude_api_error", "detail": "Extractor not loaded"},
            )
        image_bytes = await _fetch_image(body.image_url)
        chart_result = await extractor.extract(
            image_bytes=image_bytes,
            doc_class=body.doc_class,
            source_url=body.source_url,
            image_url=body.image_url,
        )
        if chart_result is None:
            return JSONResponse(content=None)
        return JSONResponse(content=chart_result.model_dump())

    return app
