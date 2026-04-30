"""Chart data extractor using Claude Vision API (ADR-005 Section 7)."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import structlog

# Make backend/ importable when running from project root or ml/ subdirectory
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import anthropic
from app.schemas.cv import ChartResult  # noqa: E402  # type: ignore[import]

logger = structlog.get_logger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2048

_SYSTEM_PROMPT = (
    "You are a data extraction assistant. You will be given an image of a chart or figure. "
    "Extract all data visible in the chart into structured JSON.\n\n"
    "Respond with ONLY a JSON object matching this exact schema — no markdown, no "
    "explanation, no code fences:\n\n"
    '{\n'
    '  "title": "<chart title or null>",\n'
    '  "x_axis": "<x-axis label or null>",\n'
    '  "y_axis": "<y-axis label or null>",\n'
    '  "series": [\n'
    '    {\n'
    '      "name": "<series name>",\n'
    '      "data_points": [\n'
    '        {"label": "<x value or category>", "value": <numeric value or "string">}\n'
    '      ]\n'
    '    }\n'
    '  ],\n'
    '  "key_insight": "<1-2 sentence summary of the most important finding in this chart>"\n'
    '}\n\n'
    "Rules:\n"
    "- For pie charts: x_axis and y_axis must be null. Each slice is one DataPoint where "
    "label is the slice name and value is the percentage (as a float, e.g. 34.5).\n"
    "- For tables: x_axis and y_axis must be null. Each column is one series. series[].name "
    "is the column header. data_points[].label is the row header. data_points[].value "
    "is the cell value.\n"
    "- If a numeric value is not readable, use the string \"unreadable\" as the value.\n"
    "- key_insight must always be populated. Never leave it empty or null.\n"
    "- Output ONLY the JSON object. No other text."
)

_RETRY_SUFFIX = (
    "\n\nYour previous response was not valid JSON. Respond with ONLY the JSON object."
)


def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image media type from magic bytes."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"  # safe default


def _parse_chart_result(
    raw_json: str, image_url: str, source_url: str, chart_type: str
) -> ChartResult | None:
    """Parse Claude's JSON response into a ChartResult. Returns None on any failure."""
    try:
        data: dict[str, Any] = json.loads(raw_json.strip())
    except json.JSONDecodeError:
        return None
    data["image_url"] = image_url
    data["source_url"] = source_url
    data["chart_type"] = chart_type
    try:
        return ChartResult.model_validate(data)
    except Exception:
        return None


class ChartExtractor:
    """
    Extracts structured chart data from images using Claude Vision (claude-sonnet-4-6).

    Returns None gracefully for non-chart images, schema validation failures,
    and API errors — never raises to the caller.
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client: anthropic.AsyncAnthropic = client or anthropic.AsyncAnthropic()

    async def extract(
        self,
        image_bytes: bytes,
        doc_class: str,
        source_url: str,
        image_url: str = "",
    ) -> ChartResult | None:
        """
        Extract structured data from a chart image.

        Args:
            image_bytes: Raw image bytes of the chart.
            doc_class: One of bar_chart, line_chart, pie_chart, scatter_plot, table.
            source_url: URL of the web page that contained this image.
            image_url: URL of the image itself (used for citation; empty string if unknown).

        Returns:
            ChartResult if extraction succeeded, None otherwise.
        """
        try:
            return await self._extract_with_retry(
                image_bytes=image_bytes,
                doc_class=doc_class,
                source_url=source_url,
                image_url=image_url,
            )
        except Exception as exc:
            logger.warning(
                "chart_extraction_failed",
                source_url=source_url,
                doc_class=doc_class,
                error=str(exc),
            )
            return None

    async def _extract_with_retry(
        self,
        image_bytes: bytes,
        doc_class: str,
        source_url: str,
        image_url: str,
    ) -> ChartResult | None:
        media_type = _detect_media_type(image_bytes)
        image_b64 = base64.standard_b64encode(image_bytes).decode()
        prompt = f"You will be given an image of a {doc_class}.\n{_SYSTEM_PROMPT}"

        for attempt in range(2):
            user_text = prompt if attempt == 0 else prompt + _RETRY_SUFFIX
            response = await self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": user_text,
                            },
                        ],
                    }
                ],
            )
            raw_text = response.content[0].text if response.content else ""
            result = _parse_chart_result(
                raw_json=raw_text,
                image_url=image_url,
                source_url=source_url,
                chart_type=doc_class,
            )
            if result is not None:
                return result
            logger.debug(
                "chart_extraction_parse_failed",
                attempt=attempt + 1,
                source_url=source_url,
            )

        return None
