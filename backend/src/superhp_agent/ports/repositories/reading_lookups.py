"""Persistence capability for reader-initiated contextual lookup facts.

The port records only stable reading facts. It does not calculate difficulty,
change annotation density, display alerts, or start the recommendation Agent.
"""

from collections.abc import Collection
from typing import Protocol, runtime_checkable

from superhp_agent.contracts import ReadingLookupSummary
from superhp_agent.corpus import ReadingUnit


@runtime_checkable
class ReadingLookupRepository(Protocol):
    """Record successful lookup clicks and aggregate selected reading units."""

    def record_lookup(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        was_annotated: bool = False,
    ) -> int: ...

    def summarize_lookups(
        self,
        *,
        unit_ids: Collection[str],
    ) -> ReadingLookupSummary: ...
