<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau -->
<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

<h1 align="center">agtmls-scorecard</h1>

<p align="center">
  Score a repository against the AgtMLS rubric — and say how much of the
  rubric could actually be evaluated.
</p>

---

## Why this exists

The repository this rubric was written for carries a commit titled
*"align repository with 10/10 gold standard"*. It shipped alongside a CLI that
crashed on three subcommands, an installer that silently destroyed
hand-written files, a security analyzer that missed `curl | bash`, and a
`make install` that produced a binary unable to run a single command.

The gate was green throughout, because the gate checked what it checked.

A score is only worth having if it is a number a program computes. This tool
computes one — and prints, beside it, how much of the rubric it was able to
compute at all. **A 10/10 at 40% coverage is a true statement about 40% of the
rubric and says nothing about the rest**, so both numbers are printed, always.

## Use

```bash
pipx install agtmls-scorecard
agtmls-scorecard .
agtmls-scorecard ../other-repo --json
agtmls-scorecard . --fail-under 8 --min-coverage 0.4
```

```
  10.0/10  Security & Supply Chain           6/6 checked, 2 unverified
   7.5/10  Release Engineering               3/4 checked, 6 unverified
        FAIL 7.2     Version lives in one place
             0.0.6 appears in 75 authored files; each is a place it can drift

  SCORE     8.6/10   over the criteria that could be evaluated
  COVERAGE  44%    of the rubric could be evaluated at all
```

Use `--fail-under` **with** `--min-coverage`. Alone, `--fail-under` is
satisfied by a high score over three criteria.

## The four states

| State | Score | Coverage | Meaning |
| :--- | :--- | :--- | :--- |
| `pass` | ✔ | ✔ | Checked, and it holds |
| `fail` | ✔ | ✔ | Checked, and it does not |
| `n/a` | — | — | Genuinely inapplicable. **Requires a reason** |
| `unverified` | — | counts against | This tool cannot decide it. **Requires a reason** |

`unverified` is the important one. It is never silently a pass, and the
construction of a `Result` *raises* if an exemption carries no reason — an
unexplained exemption is how a rubric quietly stops meaning anything.

See [ADR 0001](docs/adr/0001-unverified-is-not-a-pass.md).

## What it does not do

- **It does not run your tests, benchmarks or builds.** It reads what they
  left behind. A benchmark is judged by whether its committed record contains
  durations, not by whether a `benches/` directory exists; a format is judged
  by whether CI validates it, not by whether the file is present. What needs
  execution — `--help` on every subcommand, MCP Inspector, a container per
  install path — stays `unverified` with the reason attached.
- **It does not replace review.** Criterion 5.9 — *no README claim without an
  enforcing check* — is permanently `unverified`, because mapping prose to
  checks is the judgement this tool exists to inform, not to make.
- **It does not grade.** It reports what it could see.

## Contributing a check

False positives matter more than missed findings. A scorecard that flags
correct work gets switched off, and a switched-off scorecard scores nothing
while looking like it scores everything.

So a new check needs a test that it **fires** on a violation *and* a test that
it **does not** on correct code. Every false positive found on this tool's
first run is pinned in `tests/` in both directions.

Raising **coverage** is worth more than raising any score.

## Licence

Apache-2.0 OR MIT.
