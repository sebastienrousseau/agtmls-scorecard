# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The ten categories of the rubric.

Six are implemented. The other four — performance, developer experience,
observability and interoperability — are declared here as whole-category
placeholders rather than omitted, because a rubric that silently drops the
categories nobody wrote a checker for is how 10/10 stops meaning anything.
They count against coverage until someone implements them.
"""

from __future__ import annotations

from ..model import CategoryReport, Result, Status
from ..repo import Repo
from . import correctness, documentation, governance, maintainability, release, security

IMPLEMENTED = [
    ("correctness", correctness),
    ("security", security),
    ("documentation", documentation),
    ("release", release),
    ("maintainability", maintainability),
    ("governance", governance),
]

#: (id, title, why no checker exists yet)
PENDING = [
    ("performance", "Performance & Efficiency",
     "needs a benchmark harness and a committed baseline to compare against; "
     "presence of a benches/ directory proves nothing about what it measures"),
    ("dx", "API & Developer Experience",
     "needs the CLI surface enumerated and each command invoked; the pattern exists "
     "in agtmls' own dispatch test but is not generalised here"),
    ("observability", "Observability & Diagnostics",
     "needs a running process to inspect for structured output and exit codes"),
    ("interoperability", "Interoperability & Standards Conformance",
     "needs each emitted format validated against its upstream schema, which means "
     "network access and per-format validators"),
]


def evaluate(repo: Repo) -> list[CategoryReport]:
    reports = [
        CategoryReport(id=identifier, title=module.TITLE, results=module.run(repo))
        for identifier, module in IMPLEMENTED
    ]
    reports.extend(
        CategoryReport(
            id=identifier,
            title=title,
            results=[Result(f"{identifier}.*", f"All of {title}", Status.UNVERIFIED, reason)],
        )
        for identifier, title, reason in PENDING
    )
    return reports
