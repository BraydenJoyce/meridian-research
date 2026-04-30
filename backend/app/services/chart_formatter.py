"""Formats extracted chart data for injection into the WriterAgent prompt (ADR-005 §8)."""
from __future__ import annotations

from typing import Any


def format_charts_section(chart_results: list[dict[str, Any]]) -> str:
    """
    Format a list of ChartResult dicts into a markdown block for the WriterAgent prompt.

    Args:
        chart_results: List of ChartResult.model_dump() dicts.

    Returns:
        Markdown string with a '## Data from Charts' section, or empty string if
        chart_results is empty.
    """
    if not chart_results:
        return ""

    lines: list[str] = [
        "## Data from Charts\n",
        "The following structured data was extracted from charts and figures "
        "found in the research sources. Incorporate relevant chart data into "
        "your analysis sections. Cite the source_url for each chart used.\n",
    ]
    for i, chart in enumerate(chart_results, 1):
        lines.append(f"### Chart {i}: {chart.get('title') or 'Untitled'}")
        lines.append(f"- **Type:** {chart['chart_type']}")
        lines.append(f"- **Source:** {chart['source_url']}")
        if chart.get("x_axis"):
            lines.append(f"- **X-axis:** {chart['x_axis']}")
        if chart.get("y_axis"):
            lines.append(f"- **Y-axis:** {chart['y_axis']}")
        lines.append(f"- **Key insight:** {chart['key_insight']}")
        lines.append("- **Data:**")
        for series in chart.get("series", []):
            lines.append(f"  - Series: {series['name']}")
            for dp in series.get("data_points", []):
                lines.append(f"    - {dp['label']}: {dp['value']}")
        lines.append("")
    return "\n".join(lines)
