# Writing a defect pack

A pack is a Python package under `bench/seeder/packs/<name>/` exposing:

```python
NAME = "<name>"
FAMILIES = [Family(...), ...]
def attach_prior(b): ...   # optional: add the pack's prior acceptance ledger and evidence files
```

Generate a split with:

```sh
.tools/venv/bin/python -m bench.seeder.generate --pack <name> --split <split> --seed <seed> \
    --count 60 --out work/variants/<split> --key work/keys/<split>.json --jobs 6 [--only fam1,fam2]
```

Dropped variants print their reason (failed anchor, oracle disagreement, leak). Fix the family until nothing drops.

## Family

```python
from bench.seeder.packs.common import Family

def apply(b, mode):          # mode is "defect" or "clean"
    ...                      # edit files, commit, build records, perturb, label, add oracles

FAMILIES = [Family(name="...", app="baseline-mortgage" | "baseline-payments", apply=apply, modes=("defect", "clean"))]
```

`Family(..., after_prior=fn)` runs `fn(b, mode)` after `attach_prior`, for families that change the ledger or evidence.

One family, two modes. The **clean** mode must look like the defect mode from the outside: same kind of carrier change, similar size, similar PR text, and it must violate **nothing**. The **defect** mode plants **exactly one** violation (one obligation, occasionally two when one implies the other, e.g. a code defect that also leaves CI red).

## VariantBuilder (`b`)

| Member | Use |
|---|---|
| `b.app`, `b.rng`, `b.author`, `b.as_of` | the app, a seeded `random.Random`, the PR author (person id), the review time |
| `b.read(rel)`, `b.write(rel, text)`, `b.delete(rel)`, `b.has(rel, needle)` | files relative to the repo root (`apps/...`, `controls/...`) |
| `b.edit(rel, old, new, count=1)` | anchored replace; raises `SeedError` unless `old` occurs exactly `count` times |
| `b.commit(message, who=None)` | commit on the change branch (default author `b.author`); returns the SHA |
| `b.head`, `b.base`, `b.changed_paths()` | current head, main, files changed base..head |
| `b.default_records(title, description, emergency=False)` | records for a well-run change: approved ticket covering the touched components, a code review by an independent change approver on head, a security review if a security-sensitive component is touched, a control-owner approval if a protected path is touched, the people directory, a background exception register, `as_of`. Returns `b.records`, which you then mutate |
| `b.approval(kind)` | the first approval of that kind in `b.records["approvals"]` |
| `b.ci_commit = sha` | make the PR's CI run on an earlier commit (default: head) |
| `b.extra["ci_started_at"]` | override the CI start time |
| `b.records["evidence"][rel] = doc` | add an evidence file under `records/evidence/rel` |
| `b.label(mode, obligations, severity, note)` | the sealed answer; obligations are the violated ids, empty when clean |
| `b.oracle(kind, **spec)` | a check that confirms the label (below) |

People are in `bench/seeder/people.py` (`with_role`, `engineers`, `primary_email`, `alias_email`). Never use real names.

Order inside `apply`: edit, commit (one to three commits), `default_records`, perturb records, `label`, `oracle`.

## Oracles

Every variant needs at least one oracle, and the generator drops it if any oracle disagrees.

- `b.oracle("hidden_test", files={rel: source}, tests=["HiddenX"], expect="fail"|"pass")`: the files are added to an export of head (never to the variant) and the full suite runs; the named tests must fail (defect) or pass (clean). Use this for product obligations, written stronger than the shipped control tests (e.g. exercise the exact path you broke).
- `b.oracle("predicate", name="violated", args={"obligation": "CHG-3"}, expect=True)`: re-derives a process obligation from the records (`bench/seeder/oracles.py`).
- `b.oracle("predicate", name="process_ok", args={"except_": ["CHG-3"]}, expect=True)`: no *other* process obligation is violated. Add it to every variant (empty `except_` for clean ones).
- `b.oracle("ci", tests=["ControlTestName"], expect="fail"|"pass")`: the PR's own CI result for named tests.

## Records formats

`records/`: `change.json`, `tickets.json` (an emergency ticket needs `deployed_at`), `approvals.json` (`reviewer`, `kind` = code_review | security_review | control_owner | pir, `decision`, `commit`, `at`), `directory.json`, `exceptions.json` (`id`, `obligation`, `component`, `scope`, `status`, `requested_by`, `approved_by`, `approved_at`, `expires` as a date, `compensating_control`), `ledger.json`, `ci/run.json` plus JUnit XML, `evidence/`, `as_of.json`.

Ledger entry:

```json
{"record": "ACR-0412", "change": "CHG-23911", "obligation": "LIM-1", "status": "shown",
 "evidence": {"kind": "proof_record", "ref": "evidence/proofs/lim1.json", "commit": "<sha on main>",
              "covers": [{"path": "apps/.../Approvals.java", "symbol": "requiredApprovals"}],
              "coverage": "exhaustive", "domain": "amount in [0, 10^9]", "rerunnable": false},
 "accepted_by": "<email>", "accepted_at": "<iso>"}
```

Evidence documents: `proof-record/v1` (Theorem-style: `statement_id`, `property`, `obligation`, `status` proved | refuted | counterexample | blocked | withheld, `target` {commit, path, symbol}, `checker`, `premises`, `assumptions`, `checked_by`, `checked_at`, `coverage`), `modelcheck-result/v1` (`model`, `command`, `scope`, `result` no_counterexample | counterexample, `obligation`, `commit`, `covers`), and Ponens-style traces (`format: ponens-trace/...`).

## Rules for authors

- No leaks. Nothing in code, comments, commit messages, PR text or records may hint at the label: no "seed", "defect", "planted", "oracle", "benchmark", "family", "twin", "test fixture" (the generator scans and drops).
- Realistic carriers. Changes a bank engineer would plausibly make: a new field, route, report, integration, refactor, parameter update, bug fix, dependency of a feature.
- Code must compile and the PR's own CI should normally pass. Most real defects get through because something made CI green (a sample control that doesn't reach the broken path, a weakened or skipped control, CI on an earlier commit, a bypass of a closed domain). A red-CI defect is allowed but should be the minority.
- Labels are ground truth: label `defect` only if the code or records really violate the obligation as the bank's catalog (`controls/obligations.json`) and change standard (`controls/change-policy.md`) define it.
