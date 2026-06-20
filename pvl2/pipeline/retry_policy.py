"""
Retry policy for parser output.

The router owns extraction. This module only decides whether a low-quality table
page deserves another pass with a stronger LlamaParse configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.quality import TableQualityAssessment


TIER_ORDER = {
    "fast": 0,
    "cost_effective": 1,
    "agentic": 2,
    "agentic_plus": 3,
}


@dataclass
class TableRetryPolicy:
    enabled: bool = True
    min_score: float = 0.86
    retry_tier: str = "agentic_plus"
    retry_spatial: bool = True
    retry_aggressive_tables: bool = True
    retry_disable_cache: bool = True
    min_improvement: float = 0.03


def has_low_quality_page(
    assessments: dict[int, TableQualityAssessment],
    policy: TableRetryPolicy,
) -> bool:
    return any(item.score < policy.min_score for item in assessments.values())


def can_escalate(
    current_tier: str,
    current_spatial: bool,
    current_aggressive_tables: bool,
    policy: TableRetryPolicy,
) -> bool:
    if not policy.enabled:
        return False

    current_rank = TIER_ORDER.get(current_tier, 0)
    retry_rank = TIER_ORDER.get(policy.retry_tier, current_rank)
    if retry_rank > current_rank:
        return True
    if policy.retry_spatial and not current_spatial:
        return True
    if policy.retry_aggressive_tables and not current_aggressive_tables:
        return True
    return False


def should_retry_table_group(
    assessments: dict[int, TableQualityAssessment],
    current_tier: str,
    current_spatial: bool,
    current_aggressive_tables: bool,
    policy: TableRetryPolicy,
) -> bool:
    return (
        has_low_quality_page(assessments, policy)
        and can_escalate(current_tier, current_spatial, current_aggressive_tables, policy)
    )
