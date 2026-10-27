# Ponens arms

Imandra's **ponens** (MIT) as a pull request in the bank would meet it: the GitHub Action
(`imandra-ai/ponens/action`) on every PR, plus, for the second arm, a reasoning trace written by the PR's coding
agent. Two arms: `ponens-no-trace` and `ponens-agent-trace`.

## Install (by the user; nothing is vendored)

Source: github.com/imandra-ai/ponens at commit `2f91978` (release 1.22.0). `scripts/setup_tools.sh` does the
following, or do it by hand: clone that commit, then `uv venv .tools/ponens-venv --python 3.12 && uv pip install
--python .tools/ponens-venv/bin/python "<clone>/cli[schema]"`, and copy `<clone>/action` to
`.tools/ponens-src/action`. `ponens --version` must print 1.22.0 (it reads trace spec 1.15). The runner finds the
pieces through `PONENS_BIN`, `PONENS_PY` and `PONENS_ACTION` (defaults: that `.tools/` layout). Note: the published
action defaults to installing ponens **1.15.3** from GitHub (`ponens-version` input); the bench runs the action's
driver against the 1.22.0 CLI from the same commit as the driver, which is what `ponens-source: local` does in
Ponens's own CI.

## What Ponens reads

- **Trace** (spec 1.15, `ponens trace schema`): `trace_id`, `spec_version`, `actions[]` (`id`, `type`, `category`,
  `label`, `rationale`, `inputs`/`outputs` artifact ids), `artifacts[]` (`artifact_id`, `artifact_type`,
  `producer_action_id`, `derived_from[]`, typed `payload`), `outcome`, `trigger`, `policies[]`, `goals[]`.
  Declared gaps are `Residual` artifacts (`kind` assumption | unverified | out_of_scope | limitation |
  open_question | defeater ..., `severity`, `status`). A `ConformanceResult` payload needs `reference_artifact_id`,
  `target_artifact_id` and `status` (passed | failed | partial | unknown).
- **Goal** (Goal Contract v0.2, `spec/GOAL_CONTRACT_v0_2.md`): `intent`, `scope`, `acceptance[]` of typed criteria
  `{id, component, evidence: {artifact: <type>}, required, covers}`, optional `policies`, `criteria_review`
  (certification by a non-doer). Resolution is deterministic and **by lineage**: a criterion is met when an artifact
  of the required type is "about" its component (a symbol by lineage; a file or a named subject by what the
  artifact's payload names, e.g. `payload.obligation`). The evidence's own verdict decides: `passed`/`proved`/...
  -> `done`; `failed`/`refuted`/... -> `blocked`; `partial`/`unknown`/... -> `doing`; no evidence -> `todo`.
  An open `defeater` residual also blocks. Combinators (and/or/not/forall over selectors) exist but are unused here.
- Pitfall found while wiring it: a criterion's `statement` field is treated as an **exact-statement** match against
  the evidence payload, so a human-readable statement there leaves every criterion `todo`. The bank's goal puts the
  title in `label` instead.

## The CI action's behaviour (action/action.yml + action/run.py at 2f91978)

1. Find the trace: `inputs.trace`, else the single `.ponens/*.json` in the checkout, else reconstruct one from
   `inputs.transcript` with `ponens emit`.
2. **No trace found:** status `no-trace`, a "No reasoning trace" comment, and **exit 0 (green)** unless
   `require-trace: true` (default `false`). Confirmed by running the driver on our fixtures: `status=no-trace`, exit 0.
3. Validate (`ponens trace validate`): a malformed trace is `invalid` and fails the job.
4. Gate: `ponens trace check --json` over the trace's own policies plus any `policies:` / `policy-file:` inputs (none
   by default). With `fail-on: error` (default) only a failed **error-severity policy** turns the job red.
5. Resolve goals (`ponens trace enrich`) for the **scorecard only**: the job status ignores goals. Confirmed: a
   trace whose bank goal has a blocked criterion (a `failed` conformance) still gets `status=passed`, exit 0,
   "Governance passed, Goals 0/1 met".
6. Report: Markdown to the job summary and one PR comment. (No GitHub token here, so nothing is posted.)

## The two arms

- **ponens-no-trace** (Ponens's default on a PR without a trace): export the head commit (blob by blob, no
  `git archive`: no filter drivers), run the action driver
  with its default inputs. The PR has no `.ponens/` trace, so the check is green. Decision **ACCEPT**, no
  per-obligation statuses. Free, ~0.02 s.
- **ponens-agent-trace**: gpt-oss:120b (Ollama, think=high, schema-constrained JSON) plays the PR's coding agent with
  `prompts/ponens-pr-agent.md` and the same review packet the packet arms get. It returns steps, one conformance
  result per catalog obligation (passed | failed | partial | unknown, with an evidence strength and basis), and
  residuals. The harness builds the trace: one `Commit` action and ground-truth `Diff` artifact per commit, the
  agent's steps as actions, one `Specification` artifact per catalog obligation (the reference), one
  `ConformanceResult` per reported obligation (target = the change's Diff), residuals as `Residual` artifacts. It
  sets the **bank's goal** on the trace (intent author `human`): one required criterion per catalog obligation,
  `component: {obligation: <id>}`, `evidence: {artifact: "ConformanceResult"}`. The trace goes to
  `.ponens/trace.json` in the head export and the action driver runs; `ponens trace resolve --json` gives the
  per-criterion status.

## Verdict mapping

| Ponens result | Decision |
|---|---|
| no-trace (no trace published) | ACCEPT: the action passes it (green check) |
| CI status `invalid` (trace fails validation) | HOLD, `meta.error` set (the job is red, but nothing about the obligations is known) |
| CI status `failed` (an error-severity policy failed) | REJECT |
| any required bank criterion `blocked` (a failed conformance or an open defeater) | REJECT |
| every required bank criterion `done` | ACCEPT |
| otherwise (`doing`: partial/unknown evidence; `todo`: no evidence) | HOLD |

Per obligation: `done` -> shown, `blocked` -> refuted, `doing`/`todo` -> open. The action's own status and what it
would mean for the PR on its own (green = ACCEPT) are kept in `meta.ci_status`, `meta.ci_exit_code`,
`meta.ci_decision` and `meta.ci_goals_met`, so the report can show both "Ponens as shipped" (goals don't gate) and
"Ponens with our obligations as goals".

## Fixture results (2026-10-23)

| Arm | v-q7m2ka (expected REJECT, CHG-2) | v-h3tz9p (expected ACCEPT) |
|---|---|---|
| ponens-no-trace | ACCEPT (no-trace, green) | ACCEPT (no-trace, green) |
| ponens-agent-trace | REJECT: CHG-2 blocked, AUD-1 doing, 4 done; CI `passed`, goals 0/1 | HOLD: AUD-1 doing (agent said `partial`: sample-only control), 5 done; CI `passed`, goals 0/1 |
| time / tokens | 135.7 s; 6,050 in / 7,002 out | 84.7 s; 6,052 in / 5,150 out |

In both agent-trace runs the action itself reported "Governance passed" (exit 0): the CI check would have let both
changes merge.

## Open points

- The PR agent is the only source of conformance results: Ponens checks that the record is well-formed and resolves
  the goal deterministically, but it trusts what the agent says. A more adversarial PR agent
  (one that wants the change merged) would be a separate arm; this one is told to report what the evidence shows.
- Every catalog obligation is a required criterion, so the agent marks obligations the change cannot affect as
  `passed`. Ponens has no applicability notion besides selectors over components.
- Graded with ponens 1.22.0; the published action defaults to 1.15.3.
