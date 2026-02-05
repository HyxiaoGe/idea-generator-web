"""
Cost estimation utilities for image generation.
"""

from dataclasses import dataclass


@dataclass
class CostEstimate:
    """Cost estimate for image generation."""

    resolution: str
    count: int
    unit_cost: float
    total_cost: float
    currency: str = "USD"


# Pricing based on Google Gemini Image Generation (as of 2024)
# https://ai.google.dev/pricing
PRICING = {
    "1K": 0.04,  # $0.04 per image for standard resolution
    "2K": 0.08,  # $0.08 per image for 2K
    "4K": 0.08,  # $0.08 per image for 4K (same as 2K in current pricing)
}


def estimate_cost(resolution: str = "1K", count: int = 1) -> CostEstimate:
    """
    Estimate the cost for generating images.

    Args:
        resolution: Image resolution (1K, 2K, 4K)
        count: Number of images to generate

    Returns:
        CostEstimate with pricing details
    """
    unit_cost = PRICING.get(resolution, PRICING["1K"])
    total_cost = unit_cost * count

    return CostEstimate(
        resolution=resolution, count=count, unit_cost=unit_cost, total_cost=total_cost
    )


def format_cost(estimate: CostEstimate, lang: str = "en") -> str:
    """
    Format cost estimate for display.

    Args:
        estimate: CostEstimate object
        lang: Language code

    Returns:
        Formatted cost string
    """
    if lang == "zh":
        if estimate.count == 1:
            return f"预估成本: ${estimate.total_cost:.3f}"
        return f"预估成本: {estimate.count} 张 x ${estimate.unit_cost:.3f} = ${estimate.total_cost:.3f}"
    else:
        if estimate.count == 1:
            return f"Est. Cost: ${estimate.total_cost:.3f}"
        return (
            f"Est. Cost: {estimate.count} x ${estimate.unit_cost:.3f} = ${estimate.total_cost:.3f}"
        )


def get_pricing_table() -> dict:
    """Get the pricing table for display."""
    return PRICING.copy()
