## What this changes

## If it adds or changes a check

- [ ] The criterion is **binary**: it passes or it fails, with no judgement call
- [ ] A test asserts it **fires** on a violating fixture
- [ ] A test asserts it **does not fire** on a correct one
- [ ] `unverified` carries a reason saying *why* it cannot be checked

## Checks

- [ ] `python3 -m unittest discover -s tests`
- [ ] `agtmls-scorecard .` — this repository still scores at or above its baseline
