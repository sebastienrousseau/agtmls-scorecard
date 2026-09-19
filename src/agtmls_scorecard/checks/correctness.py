# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 1 — Correctness & Test Depth."""

from __future__ import annotations

import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Correctness & Test Depth"


def _tests_exist(repo: Repo) -> Result:
    candidates = [
        p for p in repo.files
        if "test" in p.name.lower() or "tests" in p.relative_to(repo.root).parts
    ]
    if not candidates:
        return Result("1.0", "Tests exist", Status.FAIL, "no test files found")
    return Result("1.0", "Tests exist", Status.PASS, f"{len(candidates)} test file(s)")


def _discovery(repo: Repo) -> Result:
    """A hand-maintained list of tests is a list someone will forget to update.

    The repository this tool was written for had exactly that: a `CASES` tuple
    that a new test class had to be added to, or it silently never ran.
    """
    offenders: list[str] = []
    for path in repo.by_suffix(".py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "unittest" not in text:
            continue
        if re.search(r"^CASES\s*=\s*\(", text, re.MULTILINE) and "loadTestsFromModule" not in text:
            offenders.append(str(path.relative_to(repo.root)))
    if offenders:
        return Result("1.3", "Tests are discovered, not hand-registered", Status.FAIL,
                      f"hand-maintained registry in {offenders[0]}")
    return Result("1.3", "Tests are discovered, not hand-registered", Status.PASS,
                  "no hand-maintained test registry")


def _no_silent_skips(repo: Repo) -> Result:
    """A skipped test reports green while proving nothing."""
    skips: list[str] = []
    patterns = (
        re.compile(r"#\[ignore\]"),
        re.compile(r"@(unittest\.)?skip\b"),
        re.compile(r"\.skip\s*\("),
        re.compile(r"\btodo!\s*\("),
    )
    linked = re.compile(r"(#\d+|issues?/\d+|reason\s*=)")
    for path in repo.by_suffix(".rs", ".py", ".mjs", ".js", ".ts"):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            if any(p.search(line) for p in patterns) and not linked.search(line):
                skips.append(f"{path.relative_to(repo.root)}:{index + 1}")
    if skips:
        return Result("1.6", "No unexplained skipped test", Status.FAIL,
                      f"{len(skips)}, e.g. {skips[0]}")
    return Result("1.6", "No unexplained skipped test", Status.PASS, "none")


def _matrix(repo: Repo) -> Result:
    text = repo.workflow_text
    if not text:
        return Result("1.9", "CI exercises the declared floor and ceiling", Status.NOT_APPLICABLE,
                      "no workflows")
    if "matrix:" in text and re.search(r"(os|python-version|node|toolchain)", text):
        return Result("1.9", "CI exercises the declared floor and ceiling", Status.PASS,
                      "a version or platform matrix is configured")
    return Result("1.9", "CI exercises the declared floor and ceiling", Status.FAIL,
                  "no matrix: a single configuration proves one configuration")


def run(repo: Repo) -> list[Result]:
    return [
        _tests_exist(repo),
        Result("1.1", "Every public entry point is executed by a test", Status.UNVERIFIED,
               "enumerating entry points and matching them to invocations needs the language's "
               "own tooling; the repository's dispatch test is the pattern that does it"),
        Result("1.2", "Coverage of the public surface >= 90%", Status.UNVERIFIED,
               "needs an instrumented run; no coverage artifact is read here"),
        _discovery(repo),
        Result("1.4", "Every fix lands with a test seen to fail first", Status.UNVERIFIED,
               "would mean replaying each fix commit against its parent; possible, not implemented"),
        Result("1.5", "Property or fuzz tests for every untrusted parser", Status.UNVERIFIED,
               "identifying which parsers take untrusted input needs intent"),
        _no_silent_skips(repo),
        Result("1.7", "Error paths tested, not only happy paths", Status.UNVERIFIED,
               "needs branch coverage, not a static read"),
        Result("1.8", "Golden outputs byte-exact and regenerable", Status.UNVERIFIED,
               "requires running each generator in --check mode"),
        _matrix(repo),
        Result("1.10", "Mutation score >= 70% on core logic", Status.UNVERIFIED,
               "needs cargo-mutants or mutmut; both are long-running build-environment tools"),
    ]
