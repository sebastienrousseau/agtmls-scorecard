# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 10 — Governance & Community."""

from __future__ import annotations

import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Governance & Community"

REQUIRED = [
    ("LICENSE", ("LICENSE", "LICENSE.md", "LICENSE-APACHE", "LICENSE-MIT")),
    ("CODE_OF_CONDUCT", ("CODE_OF_CONDUCT.md",)),
    ("CONTRIBUTING", ("CONTRIBUTING.md",)),
    ("SECURITY", ("SECURITY.md",)),
    ("SUPPORT", ("SUPPORT.md",)),
]


def run(repo: Repo) -> list[Result]:
    missing = [name for name, candidates in REQUIRED if not repo.exists(*candidates)]
    files = (
        Result("10.1", "Community health files present", Status.FAIL, f"missing {', '.join(missing)}")
        if missing
        else Result("10.1", "Community health files present", Status.PASS, "all five present")
    )

    citation = repo.read("CITATION.cff")
    if citation is None:
        cff = Result("10.2", "CITATION.cff present and parseable", Status.FAIL, "absent")
    elif all(key in citation for key in ("cff-version", "title", "authors")):
        cff = Result("10.2", "CITATION.cff present and parseable", Status.PASS, "required keys present")
    else:
        cff = Result("10.2", "CITATION.cff present and parseable", Status.FAIL,
                     "missing cff-version, title or authors")

    templates = repo.root / ".github"
    has_issue = (templates / "ISSUE_TEMPLATE").is_dir() or (templates / "issue_template.md").exists()
    has_pr = any((templates / n).exists() for n in ("PULL_REQUEST_TEMPLATE.md", "pull_request_template.md"))
    if has_issue and has_pr:
        tmpl = Result("10.3", "Issue and pull request templates", Status.PASS, "both present")
    else:
        absent = [n for n, ok in (("issue", has_issue), ("pull request", has_pr)) if not ok]
        tmpl = Result("10.3", "Issue and pull request templates", Status.FAIL,
                      f"no {' or '.join(absent)} template")

    # Dependabot or Renovate: an ecosystem this size cannot be updated by hand.
    has_bot = repo.exists(".github/dependabot.yml", ".github/dependabot.yaml",
                          "renovate.json", ".github/renovate.json")
    updates = (
        Result("10.7", "Dependency update automation", Status.PASS, "configured")
        if has_bot
        else Result("10.7", "Dependency update automation", Status.FAIL,
                    "no dependabot or renovate config")
    )

    support = repo.read("SUPPORT.md") or ""
    window = re.search(r"latest\s+`?\d|supported versions|support window", support, re.IGNORECASE)
    policy = (
        Result("10.8", "Stated support window", Status.PASS, "SUPPORT.md states what is supported")
        if window
        else Result("10.8", "Stated support window", Status.FAIL,
                    "SUPPORT.md does not say which versions get fixes")
    )

    roadmap = repo.exists("ROADMAP.md", "docs/ROADMAP.md", "docs/ECOSYSTEM.md")
    plan = (
        Result("10.10", "Public roadmap", Status.PASS, "present")
        if roadmap
        else Result("10.10", "Public roadmap", Status.FAIL, "none found")
    )

    return [
        files, cff, tmpl,
        Result("10.4", "Branch protection: signed commits, required checks", Status.UNVERIFIED,
               "needs the GitHub API and repository admin scope"),
        Result("10.5", "OpenSSF Scorecard >= 9.0", Status.UNVERIFIED,
               "needs the Scorecard API; a badge in a README is a claim, not a reading"),
        Result("10.6", "OpenSSF Baseline level met", Status.UNVERIFIED,
               "no machine-readable Baseline assertion exists in this repository"),
        updates, policy,
        Result("10.9", "Shared reusable CI across the ecosystem", Status.UNVERIFIED,
               "requires comparing against sibling repositories, which this tool scores one at a time"),
        plan,
    ]
