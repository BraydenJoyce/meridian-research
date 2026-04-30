"""Pydantic schemas for the CV document pipeline (ADR-005)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_VALID_CHART_TYPES: frozenset[str] = frozenset(
    {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}
)


class DataPoint(BaseModel):
    """A single x→y data point within a chart series."""

    label: str = Field(..., description="Category label or x-axis tick value")
    value: float | str = Field(
        ...,
        description="Numeric value if parseable; raw string from chart otherwise",
    )


class SeriesItem(BaseModel):
    """One data series within a chart (one line, one bar group, one pie slice set)."""

    name: str = Field(..., description="Series name. 'value' for single-series charts.")
    data_points: list[DataPoint] = Field(
        ...,
        min_length=1,
        description="Ordered list of data points for this series.",
    )


class ChartResult(BaseModel):
    """
    Structured data extracted from a single chart image.

    Produced by CvDocumentAgent; consumed by WriterAgent.
    Stored in chart_extractions table (one row per ChartResult).
    """

    image_url: str = Field(..., description="URL of the source image")
    source_url: str = Field(..., description="URL of the web page containing the image")
    chart_type: str = Field(
        ...,
        description="One of: bar_chart, line_chart, pie_chart, scatter_plot, table",
    )
    title: str | None = Field(
        None,
        description="Chart title as it appears in the image; None if not present",
    )
    x_axis: str | None = Field(
        None,
        description="X-axis label; None for pie charts and tables",
    )
    y_axis: str | None = Field(
        None,
        description="Y-axis label; None for pie charts and tables",
    )
    series: list[SeriesItem] = Field(
        ...,
        min_length=1,
        description="All data series extracted from the chart",
    )
    key_insight: str = Field(
        ...,
        description=(
            "1-2 sentence plain-English summary of the chart's key finding. "
            "Always populated — never empty string."
        ),
    )

    @field_validator("chart_type")
    @classmethod
    def validate_chart_type(cls, v: str) -> str:
        if v not in _VALID_CHART_TYPES:
            raise ValueError(
                f"chart_type must be one of {sorted(_VALID_CHART_TYPES)}, got {v!r}"
            )
        return v

    @field_validator("key_insight")
    @classmethod
    def validate_key_insight(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("key_insight must not be empty")
        return v.strip()
