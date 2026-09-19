# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The scoring model.

The single decision that makes this tool worth having: **an unverified
criterion is not a passing one, and it is not a failing one either.**

A rubric of a hundred criteria where forty are checked and sixty are opinions
can be made to read 10/10 by scoring only the forty. That is how a scorecard
becomes the thing it was meant to prevent, and the repository this tool was
written for has a commit titled "align repository with 10/10 gold standard"
that shipped four ship-blocking defects, so the failure mode is not
hypothetical.

So a report carries two numbers, and neither is optional:

  * **score** — of the criteria this tool can actually evaluate, how many pass.
  * **coverage** — how much of the rubric it could evaluate at all.

A score of 10/10 at 40% coverage is a true statement about 40% of the rubric
and says nothing about the rest. Printing both is what keeps it honest.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Status(enum.Enum):
    """The outcome of evaluating one criterion."""

    PASS = "pass"
    FAIL = "fail"
    #: Genuinely does not apply here — no WASM target, no HTTP surface.
    #: Removed from both numerator and denominator, and requires a reason.
    NOT_APPLICABLE = "n/a"
    #: This tool cannot evaluate it. Excluded from the score and counted
    #: against coverage, never silently treated as a pass.
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Result:
    """One criterion, evaluated."""

    criterion: str
    title: str
    status: Status
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status in (Status.NOT_APPLICABLE, Status.UNVERIFIED) and not self.detail:
            raise ValueError(
                f"{self.criterion}: {self.status.value} requires a reason. An unexplained "
                "exemption is how a rubric quietly stops meaning anything."
            )


@dataclass
class CategoryReport:
    """Results for one category of the rubric."""

    id: str
    title: str
    results: list[Result] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status is Status.PASS)

    @property
    def evaluated(self) -> int:
        """Criteria this tool could actually decide."""
        return sum(1 for r in self.results if r.status in (Status.PASS, Status.FAIL))

    @property
    def unverified(self) -> int:
        return sum(1 for r in self.results if r.status is Status.UNVERIFIED)

    @property
    def not_applicable(self) -> int:
        return sum(1 for r in self.results if r.status is Status.NOT_APPLICABLE)

    @property
    def score(self) -> float:
        """Out of ten, over the criteria that were evaluated.

        Returns 0.0 when nothing could be evaluated: a category this tool
        cannot see is not a category that passes.
        """
        if self.evaluated == 0:
            return 0.0
        return round(10.0 * self.passed / self.evaluated, 1)

    @property
    def coverage(self) -> float:
        """Fraction of applicable criteria this tool could decide."""
        applicable = len(self.results) - self.not_applicable
        if applicable == 0:
            return 1.0
        return round(self.evaluated / applicable, 3)

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.status is Status.FAIL]


@dataclass
class Report:
    """A scored repository."""

    repo: str
    path: str
    categories: list[CategoryReport] = field(default_factory=list)

    @property
    def score(self) -> float:
        evaluated = sum(c.evaluated for c in self.categories)
        if evaluated == 0:
            return 0.0
        passed = sum(c.passed for c in self.categories)
        return round(10.0 * passed / evaluated, 1)

    @property
    def coverage(self) -> float:
        applicable = sum(len(c.results) - c.not_applicable for c in self.categories)
        if applicable == 0:
            return 1.0
        return round(sum(c.evaluated for c in self.categories) / applicable, 3)

    @property
    def weakest(self) -> list[CategoryReport]:
        """Categories with failures, worst first. What to fix next."""
        return sorted(
            (c for c in self.categories if c.failures),
            key=lambda c: (c.score, -len(c.failures)),
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "repo": self.repo,
            "path": self.path,
            "score": self.score,
            "coverage": self.coverage,
            "note": (
                "score is over evaluated criteria only; coverage is how much of the "
                "rubric could be evaluated. A high score at low coverage is a true "
                "statement about a small part of the rubric."
            ),
            "categories": [
                {
                    "id": c.id,
                    "title": c.title,
                    "score": c.score,
                    "coverage": c.coverage,
                    "passed": c.passed,
                    "evaluated": c.evaluated,
                    "unverified": c.unverified,
                    "not_applicable": c.not_applicable,
                    "results": [
                        {
                            "criterion": r.criterion,
                            "title": r.title,
                            "status": r.status.value,
                            "detail": r.detail,
                        }
                        for r in c.results
                    ],
                }
                for c in self.categories
            ],
        }
