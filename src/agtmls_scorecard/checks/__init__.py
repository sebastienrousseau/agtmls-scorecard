# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The ten categories of the rubric.

All ten are implemented. Four of them -- performance, developer experience,
observability and interoperability -- were whole-category placeholders until
now, which meant the tool reported 0.0 at zero coverage for 40 of the 100
criteria. That was honest, and it was also the reason a repository could read
9.3/10 while nothing had ever checked whether it was fast, diagnosable,
scriptable or conformant.

Implementing them is expected to *lower* published scores, because criteria
that were invisible become criteria that can fail. A number that only ever
moves up is not measuring anything.

PENDING is kept, empty, on purpose: it is the mechanism for declaring a
category nobody has written a checker for, and deleting it would make the next
omission silent instead of counted.
"""

from __future__ import annotations

from ..model import CategoryReport, Result, Status
from ..repo import Repo
from . import (
    correctness,
    documentation,
    dx,
    governance,
    interoperability,
    maintainability,
    observability,
    performance,
    release,
    security,
)

IMPLEMENTED = [
    ("correctness", correctness),
    ("security", security),
    ("performance", performance),
    ("dx", dx),
    ("documentation", documentation),
    ("observability", observability),
    ("release", release),
    ("interoperability", interoperability),
    ("maintainability", maintainability),
    ("governance", governance),
]

#: (id, title, why no checker exists yet)
PENDING: list[tuple[str, str, str]] = []


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
