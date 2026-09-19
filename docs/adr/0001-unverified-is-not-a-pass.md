<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau -->
<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# ADR 0001 — An unverified criterion is neither a pass nor a fail

**Status:** accepted
**Date:** 2026-09-19

## Context

The rubric has a hundred criteria. Perhaps forty can be decided by reading a
repository; the rest need a running process, a coverage report, a network call,
or a judgement.

The tempting design is to check the forty and report a score out of forty.
Every repository then looks excellent, and the number is worthless — it says
"we pass the things we chose to check", which is true of any project.

This is not hypothetical. The repository this rubric was written for carries a
commit titled *"align repository with 10/10 gold standard"*. It shipped
alongside a CLI that crashed on three subcommands, an installer that destroyed
hand-written files, an analyzer that missed `curl | bash`, and a `make install`
that produced a binary unable to run a single command. The gate was green
throughout, because the gate checked what it checked.

## Decision

Four states, not two:

| State | In the score? | In coverage? |
| :--- | :--- | :--- |
| `pass` | numerator and denominator | yes |
| `fail` | denominator | yes |
| `n/a` | neither | **no** — genuinely inapplicable, requires a reason |
| `unverified` | neither | **yes** — counts against coverage, requires a reason |

Every report carries **two** numbers, and the renderer prints both:

- **score** — of what could be evaluated, how much passed.
- **coverage** — how much of the rubric could be evaluated at all.

Below 60% coverage the tool says so in prose, unprompted.

Categories nobody has written a checker for are declared as whole-category
placeholders rather than omitted, so they drag coverage down. Silently dropping
them would restore exactly the flattery this decision removes.

## Consequences

**Scores are lower and more useful.** This repository scored 3.7/10 at 35%
coverage on its own first run, which is a fair description of a repository a
few hours old.

**Coverage becomes the contribution that matters.** Raising it is worth more
than raising any score, and the issue template says so.

**`n/a` is a risk.** It leaves the denominator entirely, so a repository could
mark everything inapplicable and score 10/10 over nothing. The reason string is
the mitigation: it appears in the report, so the exemption is arguable rather
than invisible. If that proves insufficient, `n/a` should also count against a
separate applicability figure.

## Alternatives rejected

**Weight criteria.** Lets an important criterion outrank a trivial one.
Rejected: choosing the weights is the judgement the tool is supposed to remove,
and a weighted score cannot be audited by re-reading the rubric.

**Treat unverified as a failure.** Honest in one direction and useless in the
other — every repository scores near zero, the tool gets ignored, and nothing
improves.
