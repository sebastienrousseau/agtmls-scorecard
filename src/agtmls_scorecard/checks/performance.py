# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 3 — Performance & Efficiency.

This category scored 0.0 at zero coverage until now, which the tool reported
honestly and which therefore said nothing at all about whether anything was
fast. The difficulty is real: performance is the one category where presence
proves least. A `benches/` directory, a `criterion` dependency and a file
called `benchmark.py` are all compatible with measuring nothing.

So every check here reads an **artifact with numbers in it**, not a filename:

  * a benchmark record is one that contains durations;
  * a baseline is one that records a per-workload figure CI can compare to;
  * a scaling claim is one that states growth against input size.

What cannot be read from a checkout stays `unverified` with the reason. CI
wall time needs the forge's API; a cache hit rate needs a run.

Evidence formats
----------------

Any JSON under `benchmarks/`, `bench/` or `benches/`, plus a top-level
`bench-baseline.json` or `benchmark-baseline.json`. Durations are recognised
by key: anything ending `_ms`, `_ns`, `_s`, or named `p50`/`p95`/`mean`/
`median`/`duration`/`elapsed`.

Three optional declarations let a repository say what a number *means*, since
a bare figure cannot:

  ``"cold_start_budget_ms"`` and per-workload ``"interactive": true``
      which figures criterion 3.10's budget governs. Without them the budget
      has nothing to bind to and 3.10 stays unverified.

  ``"wall_s"``
      a recorded gate duration, for 3.3. Running the gate to find out would
      mean executing the repository under inspection.

  ``"cold_paths"``
      measurements that are superlinear on purpose because they are not on a
      hot path. Undeclared counts as hot, so the default stays strict and the
      exemption has to be written down where a reviewer sees it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import Result, Status
from ..repo import Repo

TITLE = "Performance & Efficiency"

BENCH_DIRS = ("benchmarks", "bench", "benches")
BASELINE_NAMES = ("bench-baseline.json", "benchmark-baseline.json", "baseline.json")
DURATION_KEY = re.compile(
    r"(_ms|_ns|_us|_s)$|^(p50|p95|p99|mean|median|min|max|duration|elapsed|wall)",
    re.IGNORECASE,
)
#: Gate duration budget, criterion 3.3.
GATE_BUDGET_S = 60.0
#: Anything that dispatches independent work in parallel.
CONCURRENCY = re.compile(
    r"ThreadPoolExecutor|ProcessPoolExecutor|multiprocessing|concurrent\.futures"
    r"|\brayon\b|par_iter|--jobs\b|-j\s*\d|xargs\s+-P|matrix:",
)
#: A cache whose key is derived from content, not from a date or a constant.
CONTENT_CACHE = re.compile(r"hashFiles\(|sha256|digest|content[_-]?hash", re.IGNORECASE)
SIZE_BUDGET = re.compile(
    r"(max|budget|ceiling|limit)[_\s-]*(size|bytes|kb|mb)|(size|bytes|kb|mb)[_\s-]*(budget|ceiling|limit)",
    re.IGNORECASE,
)
BYTE_CAP = re.compile(r"MAX_[A-Z_]*BYTES|max_bytes|size_limit|read\(\s*\d+\s*\)")


def _json_docs(repo: Repo) -> list[tuple[Path, object]]:
    """Every benchmark-ish JSON document in the repository, parsed."""
    candidates: list[Path] = []
    for name in BASELINE_NAMES:
        path = repo.root / name
        if path.is_file():
            candidates.append(path)
    for directory in BENCH_DIRS:
        base = repo.root / directory
        if base.is_dir():
            candidates.extend(sorted(base.rglob("*.json")))
    out = []
    for path in candidates:
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return out


def _durations(document: object) -> int:
    """How many duration-valued keys a document carries, at any depth."""
    count = 0
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (int, float)) and DURATION_KEY.search(str(key)):
                    count += 1
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return count


def _baseline(repo: Repo) -> tuple[Path, dict] | None:
    for name in BASELINE_NAMES:
        path = repo.root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("workloads"), dict):
            return path, data
    return None


def _measures_time(repo: Repo) -> Result:
    title = "A benchmark suite that measures time"
    if repo.kind == "docs":
        return Result("3.1", title, Status.NOT_APPLICABLE,
                      "no build or runtime surface to measure")
    documents = _json_docs(repo)
    if not documents:
        return Result("3.1", title, Status.FAIL,
                      "no benchmark record: a harness that commits no numbers "
                      "cannot be shown to have measured anything")
    best = max((( _durations(d), p) for p, d in documents), key=lambda x: x[0])
    if best[0] == 0:
        return Result("3.1", title, Status.FAIL,
                      f"{best[1].name} carries no duration-valued field; "
                      "a benchmark that re-runs validators is not a benchmark")
    return Result("3.1", title, Status.PASS,
                  f"{best[0]} duration field(s) in {best[1].relative_to(repo.root)}")


def _baseline_gated(repo: Repo) -> Result:
    title = "Committed baseline, and CI fails on a regression"
    if repo.kind == "docs":
        return Result("3.2", title, Status.NOT_APPLICABLE, "nothing to regress")
    found = _baseline(repo)
    if found is None:
        return Result("3.2", title, Status.FAIL,
                      "no committed baseline: without one, 'slower than what?' has no answer")
    path, data = found
    gated = re.search(r"(bench|criterion)\S*\s+.*--check|--check.*bench|benchmark.*regress",
                      repo.workflow_text, re.IGNORECASE)
    if not gated:
        return Result("3.2", title, Status.FAIL,
                      f"{path.name} exists but no workflow compares against it; "
                      "an unread baseline is a file, not a gate")
    workloads = len(data.get("workloads", {}))
    return Result("3.2", title, Status.PASS,
                  f"{workloads} workload(s) in {path.name}, compared in CI")


def _gate_duration(repo: Repo) -> Result:
    title = f"Full local gate under {GATE_BUDGET_S:.0f}s"
    for path, document in _json_docs(repo):
        if isinstance(document, dict) and isinstance(document.get("wall_s"), (int, float)):
            wall = float(document["wall_s"])
            if wall <= GATE_BUDGET_S:
                return Result("3.3", title, Status.PASS,
                              f"{wall:.1f}s recorded in {path.relative_to(repo.root)}")
            return Result("3.3", title, Status.FAIL,
                          f"{wall:.1f}s recorded in {path.relative_to(repo.root)}")
    return Result("3.3", title, Status.UNVERIFIED,
                  "no committed run record carries a wall_s field; running the gate "
                  "to find out would score a repository by executing it")


def _scaling(repo: Repo) -> Result:
    title = "No worse than linear growth in any hot path"
    if repo.kind == "docs":
        return Result("3.5", title, Status.NOT_APPLICABLE, "no hot path")
    for path, document in _json_docs(repo):
        if isinstance(document, dict) and isinstance(document.get("growth"), dict):
            growth = document["growth"]
            size = float(growth.get("size", 0) or 0)
            if size <= 1:
                continue
            # The criterion is about a *hot path*. A measurement the artifact
            # declares cold -- a pairwise comparison that runs once per gate,
            # never per request -- is superlinear on purpose and saying so is
            # not a defect. Undeclared counts as hot, so the default stays
            # strict and the escape hatch has to be written down.
            cold = set(document.get("cold_paths") or [])
            over = {
                key: value for key, value in growth.items()
                if key != "size" and key not in cold
                and isinstance(value, (int, float)) and value > size * 1.5
            }
            detail = f"growth at x{size:.0f} input recorded in {path.relative_to(repo.root)}"
            if over:
                return Result("3.5", title, Status.FAIL,
                              f"{detail}; superlinear: " +
                              ", ".join(f"{k} x{v:.0f}" for k, v in sorted(over.items())) +
                              '; declare it in "cold_paths" if it is not a hot path')
            if cold:
                detail += f"; {len(cold)} path(s) declared cold"
            return Result("3.5", title, Status.PASS, detail)
    return Result("3.5", title, Status.UNVERIFIED,
                  "no scaling measurement committed; complexity cannot be read off "
                  "a source tree without knowing which path is hot")


def _concurrency(repo: Repo) -> Result:
    title = "Independent work runs concurrently"
    sources = repo.by_suffix(".py", ".rs", ".js", ".ts", ".sh")
    for path in sources:
        if CONCURRENCY.search(path.read_text(encoding="utf-8", errors="replace")):
            return Result("3.6", title, Status.PASS,
                          f"parallel dispatch in {path.relative_to(repo.root)}")
    if CONCURRENCY.search(repo.workflow_text):
        return Result("3.6", title, Status.PASS, "CI fans work out across a matrix")
    return Result("3.6", title, Status.FAIL,
                  "nothing dispatches independent work in parallel; a serial gate "
                  "is a gate whose cost is the sum of its parts")


def _content_cache(repo: Repo) -> Result:
    title = "Repeated work is cached, keyed by content"
    uses_cache = any("actions/cache" in ref for _, ref in repo.action_uses)
    if uses_cache and CONTENT_CACHE.search(repo.workflow_text):
        return Result("3.7", title, Status.PASS, "CI cache keyed on file contents")
    if uses_cache:
        return Result("3.7", title, Status.FAIL,
                      "a cache that is not keyed on content serves stale results "
                      "or never hits; neither is a cache")
    for path in repo.by_suffix(".py", ".rs"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "cache" in text.lower() and CONTENT_CACHE.search(text):
            return Result("3.7", title, Status.PASS,
                          f"content-keyed cache in {path.relative_to(repo.root)}")
    return Result("3.7", title, Status.FAIL,
                  "no cache: every run pays for work whose inputs did not change")


def _memory_bounded(repo: Repo) -> Result:
    title = "Memory is bounded for any single input"
    for path in repo.by_suffix(".py", ".rs"):
        if BYTE_CAP.search(path.read_text(encoding="utf-8", errors="replace")):
            return Result("3.8", title, Status.PASS,
                          f"explicit size cap in {path.relative_to(repo.root)}")
    return Result("3.8", title, Status.UNVERIFIED,
                  "no explicit byte cap found, but whether this repository reads "
                  "untrusted input at all needs intent this tool does not have")


def _size_budget(repo: Repo) -> Result:
    title = "Artifact size tracked against a committed ceiling"
    if repo.kind == "docs":
        return Result("3.9", title, Status.NOT_APPLICABLE, "ships no artifact")
    if SIZE_BUDGET.search(repo.workflow_text):
        return Result("3.9", title, Status.PASS, "a size ceiling is enforced in CI")
    if not repo.workflows.get("release.yml"):
        return Result("3.9", title, Status.NOT_APPLICABLE,
                      "no release workflow, so no published artifact to bound")
    return Result("3.9", title, Status.FAIL,
                  "a release workflow publishes an artifact with no size ceiling; "
                  "growth is then only noticed by users downloading it")


def _cold_start(repo: Repo) -> Result:
    title = "Cold start under the stated budget for interactive surfaces"
    found = _baseline(repo)
    if found is None:
        return Result("3.10", title, Status.UNVERIFIED,
                      "no baseline recording a cold-start figure")
    path, data = found
    budget = data.get("cold_start_budget_ms")
    if not isinstance(budget, (int, float)):
        return Result("3.10", title, Status.UNVERIFIED,
                      f"{path.name} records no cold_start_budget_ms, so there is no "
                      "stated budget to hold the numbers to")
    interactive = {
        name: entry for name, entry in data["workloads"].items()
        if isinstance(entry, dict) and entry.get("interactive")
    }
    if not interactive:
        return Result("3.10", title, Status.UNVERIFIED,
                      f"{path.name} marks no workload \"interactive\": true, so which "
                      "figures the budget governs is undeclared")
    over = {
        name: entry["p50_ms"] for name, entry in interactive.items()
        if isinstance(entry.get("p50_ms"), (int, float)) and entry["p50_ms"] > budget
    }
    if over:
        return Result("3.10", title, Status.FAIL,
                      f"over the {budget:.0f}ms budget: " +
                      ", ".join(f"{k} {v:.0f}ms" for k, v in sorted(over.items())))
    worst = max(e["p50_ms"] for e in interactive.values())
    return Result("3.10", title, Status.PASS,
                  f"{len(interactive)} interactive workload(s), worst P50 "
                  f"{worst:.0f}ms against a {budget:.0f}ms budget")


def run(repo: Repo) -> list[Result]:
    return [
        _measures_time(repo),
        _baseline_gated(repo),
        _gate_duration(repo),
        Result("3.4", "CI wall time under 10 minutes", Status.UNVERIFIED,
               "needs the forge's run history; a declared timeout-minutes is an "
               "upper bound nobody was held to, not a measurement"),
        _scaling(repo),
        _concurrency(repo),
        _content_cache(repo),
        _memory_bounded(repo),
        _size_budget(repo),
        _cold_start(repo),
    ]
