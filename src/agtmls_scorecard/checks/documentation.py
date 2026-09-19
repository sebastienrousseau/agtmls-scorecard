# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 5 — Documentation."""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Result, Status
from ..repo import Repo

TITLE = "Documentation"

LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
#: A target inside a code span is an example of link syntax, not a link. A
#: target containing `::` is a language path -- Rust intra-doc links are the
#: common case -- and no file was ever meant to exist there.
CODE_SPAN = re.compile(r"`[^`]*`")


def _adrs(repo: Repo) -> Result:
    directory = repo.root / "docs" / "adr"
    records = sorted(directory.glob("[0-9]*.md")) if directory.is_dir() else []
    if records:
        return Result("5.3", "Architectural decisions recorded", Status.PASS,
                      f"{len(records)} ADR(s)")
    return Result("5.3", "Architectural decisions recorded", Status.FAIL, "no docs/adr")


def _links(repo: Repo) -> Result:
    """Relative links that point at nothing.

    Only local targets: a network check would make the score depend on whether
    a site was up, which is not a property of the repository.
    """
    broken: list[str] = []
    for path in repo.by_suffix(".md"):
        text = CODE_SPAN.sub("", path.read_text(encoding="utf-8", errors="replace"))
        for target in LINK.findall(text):
            if "::" in target:
                continue
            target = target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            # A relative path does not contain a sentence. Markdown prose is
            # full of bracket-then-paren sequences that are not links at all,
            # and treating them as broken ones is how a checker earns its
            # first blanket suppression.
            if any(c in target for c in " \t") or len(target) > 200:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(repo.root)} -> {target}")
    if not broken:
        return Result("5.5", "No broken local link", Status.PASS, "all local targets resolve")
    return Result("5.5", "No broken local link", Status.FAIL,
                  f"{len(broken)}: {broken[0]}")


def _readme(repo: Repo) -> Result:
    text = repo.read("README.md")
    if not text:
        return Result("5.6", "README states what, why now, and non-goals", Status.FAIL, "no README.md")
    lowered = text.lower()
    has_why = any(k in lowered for k in ("## why", "why this exists", "why now", "# why"))
    has_limits = any(
        k in lowered
        for k in ("not do", "non-goal", "when not to", "will not", "deliberately not", "does not")
    )
    if has_why and has_limits:
        return Result("5.6", "README states what, why now, and non-goals", Status.PASS,
                      "rationale and boundaries both present")
    missing = []
    if not has_why:
        missing.append("no rationale section")
    if not has_limits:
        missing.append("no stated non-goals: a README that lists only capabilities oversells")
    return Result("5.6", "README states what, why now, and non-goals", Status.FAIL, "; ".join(missing))


def _changelog(repo: Repo) -> Result:
    text = repo.read("CHANGELOG.md")
    if not text:
        return Result("5.7", "Changelog maintained", Status.FAIL, "no CHANGELOG.md")
    if re.search(r"^##\s", text, re.MULTILINE):
        return Result("5.7", "Changelog maintained", Status.PASS, "has released or unreleased sections")
    return Result("5.7", "Changelog maintained", Status.FAIL, "no version sections")


def run(repo: Repo) -> list[Result]:
    return [
        Result("5.1", "Documented commands exist, and commands are documented", Status.UNVERIFIED,
               "needs the CLI surface; the repository's own surface validator covers this"),
        Result("5.2", "Every documented example runs in CI", Status.UNVERIFIED,
               "extracting and executing examples is a per-language job, not a static check"),
        _adrs(repo),
        Result("5.4", "Every public symbol documented", Status.UNVERIFIED,
               "rustdoc and docstring coverage are toolchain jobs; missing_docs in CI covers it"),
        _links(repo),
        _readme(repo),
        _changelog(repo),
        Result("5.8", "Manpage generated from the same source as --help", Status.UNVERIFIED,
               "requires running both and diffing; not attempted from a static read"),
        Result("5.9", "No README claim without an enforcing check", Status.UNVERIFIED,
               "mapping prose claims to checks needs judgement; it is the review step this "
               "tool is meant to inform, not replace"),
        Result("5.10", "Migration guide per breaking change", Status.UNVERIFIED,
               "needs release history and a definition of breaking that varies by project"),
    ]
