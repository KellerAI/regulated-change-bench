# Regulated-change benchmark

A benchmark for one question: when a change lands in a regulated bank's code base, does an automated reviewer
check the change against the bank's obligations, and does it tell an approver the truth?

It is a synthetic bank platform (a baseline mortgage-origination app in Java and a baseline payment service in
Python), a catalog of 27 obligations the bank has written for itself (each one maps to NYDFS Part 500, SOX ITGC,
the FFIEC IT Handbook or SOC 2), and 270 changes. Each change comes with everything an approver would have:
the diff and the repository history, the change ticket, the approvals, the people directory, the exception
register, the acceptance ledger of earlier changes, the imported evidence, and the change's own CI run. Some
changes violate one obligation; their clean twins look the same from the outside and violate nothing. The answer
keys were sealed, with their hashes committed, before any reviewer was scored. Authored by Keller AI. The long-form write-up is at
[kellerai.io/resources/benchmarking-regulated-change-review](https://kellerai.io/resources/benchmarking-regulated-change-review).
Corrections: `CORRECTIONS.md`.

Seven reviewer configurations ran on the same changes with frozen prompts. None of them is ours, and this
repository contains no product. The verdict files are published so every number below can be recounted.

## Three findings

From `RESULTS.md`, regenerated from the published verdicts by `scripts/results.py`. Every number names its split:
**held-out** (136 changes, 88 defective, families written by a second model lineage and sealed before scoring) or
**seen** (134 changes, 76 defective, families written by the benchmark builder).

**1. Reviewers trust evidence that no longer covers the change.** The hardest defects were not in the code's
behaviour. They were changes that altered a function covered by an earlier proof record or a bounded model-check
result, without renewing that evidence. On held-out, in the credit-response evidence family, Grok missed 3 of 4,
Qwen 3.8 missed 4 of 4, Ponens with an agent-written trace missed 2 of 4, and Claude Code with tools, plain Opus
and gpt-oss missed 1 of 4 each; in the retained-chain evidence family Qwen 3.8 missed 4 of 4, Ponens with a
trace 2 of 4, and plain Opus, gpt-oss and Grok 1 of 4 each. On seen, the proof-lapse family
was the only family that plain Opus (1 of 3) and Grok (2 of 3) missed at all.

**2. Reviewers block approved exceptions they cannot verify.** Plain Opus rejected 13 of 48 clean changes on
held-out and 24 of 58 on seen; gpt-oss rejected 21 and 29; Grok rejected 12 and 21. The clean changes they rejected
most are the ones a bank handles through its records: a retention job with a legal-hold exception, an MFA deviation
under a correctly scoped and current exception, a ticket whose components cover the change, and a credit or
authority threshold changed with the approvals the policy requires.

**3. The open-source CI gate for agent traces passes everything by default.** The Ponens CI action with no trace
published reports a green check on 88 of 88 defective held-out changes and 76 of 76 seen ones. Given a trace
written by the change's own coding agent, it still passed 14 of 88 defective held-out changes and 8 of 76 seen
ones. An agent's own trace is self-attestation; the gate resolves it faithfully, and faithfully is not
the same as independently.

Context for the table: Claude Code with tools (Opus 5.5, read-only tools, allowed to run the repository's CI)
missed 1 of 88 held-out defects at about $0.45 and 84 seconds per change, and cleared 37 of 48 clean changes. The
same model reading a review packet with no tools missed 2 and cleared 29. The local models were slower and missed
more. The reviewers are listed in a fixed order by kind, not by score.

### Held-out split, all 136 changes

| Reviewer | False all-clears (of 88 defective) | 95% upper bound | Clean cleared (of 48) | False alarms | Clean held | USD | s/change |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, packet (no tools) | 2/88 | 7.0% | 29/48 | 13 | 6 | $27.65 ($0.20/change, Bedrock list price) | 24 |
| gpt-oss-120b, packet (local) | 5/88 | 11.6% | 23/48 | 21 | 4 | $0 API, local compute | 115 |
| Qwen 3.8 27B, packet (local) | 13/88 | 22.5% | 44/48 | 4 | 0 | $0 API, local compute | 186 |
| Grok 4.7 via Cursor agent, packet (ask mode) | 4/88 | 10.1% | 30/48 | 12 | 6 | plan quota | 181 |
| Claude Code with tools (Opus 5.5) | 1/88 | 5.3% | 37/48 | 2 | 9 | $61.16 ($0.45/change, Bedrock list price) | 84 |
| Ponens CI action, no trace (default) | 88/88 | 100.0% | 48/48 | 0 | 0 | $0 (no model call) | 0 |
| Ponens goal resolution, post-hoc trace (gpt-oss-120b) | 14/88 | 23.7% | 30/48 | 5 | 13 | $0 API, local compute | 154 |

Every reviewer covers all 136 held-out changes and all 134 seen changes. On the seen split the full-split false
all-clears are: Opus 1 of 76, gpt-oss 5, Qwen 3.8 4, Grok 2, Claude Code with tools 0, Ponens with an agent-written
trace 8, and Ponens with no trace 76 of 76. Qwen 3.8 and Ponens with an agent-written trace were first run on a
30-change common subsets (19 defective on seen, 22 on held-out) and filled in to the whole split afterwards, once the keys had been
unsealed, so their rows are not blind in the sealing sense (`PROTOCOL.md`, section 7). The full tables, the seen
split, the common-subset tables and the per-family breakdown are in `RESULTS.md`. Eight seen-split clean labels are
disputed since v1.1; see `CORRECTIONS.md`. `RESULTS.md` reports the seen split both ways.

## Run it yourself

```sh
sh scripts/setup_tools.sh                                  # pytest venv and the JUnit console jar under .tools/
python3 scripts/unpack_variants.py                         # clone the 270 variant bundles into variants/*/*/repo/
python3 scripts/results.py                                 # recount RESULTS.md from the published runs/ and the keys
# a fresh replication (needs Ollama and a pulled model; writes beside the published verdicts, never over them):
python3 -m baselines.ollama.run --model gpt-oss:120b --variants-dir variants/test-heldout --runs-dir runs-mine/test-heldout
python3 scripts/results.py --runs-dir runs-mine --extra-arm gpt-oss-120b "gpt-oss-120b (my rerun)"
sh scripts/gate.sh                                         # before you publish anything: names, paths, secrets
```

The fourth command is one example. Every runner takes `--variants-dir` and `--runs-dir`: `baselines/claude/run.py`
(`--mode packet` or `--mode agentic`, Bedrock), `baselines/ollama/run.py` (any pulled model), `baselines/grok/run.py`
(Cursor's agent CLI), `baselines/ponens/run.py` (`--mode no-trace` or `--mode agent-trace`). `baselines/README.md`
describes each arm, what it saw, and how the tool-using arms are isolated. Scoring needs nothing but Python 3.

To regenerate changes with new seeds, see `bench/seeder/API.md`; the two published packs are `bench/seeder/packs/dev`
(the seen families) and `bench/seeder/packs/heldout` (the held-out families). Regenerated variants get fresh random
ids, so they score against their own new key, not the published ones.

## Submit a configuration for a new reviewer

1. Add a runner under `baselines/<name>/run.py` that reads one variant (`baselines/common/variant.py`) and writes
   one verdict per change in the format below, through `baselines/common/runner.drive`. Packet arms get the review
   packet from `baselines/common/packet.py`; tool-using arms get a copy of the variant and may run `ci/`.
2. Use the frozen prompts in `baselines/prompts/` unchanged, or add a new prompt file and record its SHA-256 in
   every verdict's `meta.prompt_sha256`.
3. Run the reviewer on both splits (or on the common subset in `runs/<split>/subset-paid.txt` if it is expensive),
   commit `runs/<split>/<name>/v-*.json`, run `python3 scripts/results.py`, and open a pull request. Say what the
   reviewer is, what it could read, whether it could run CI, what it cost and how you priced it. Register the arm
   with `--extra-arm`, or add it to `ARMS` and `COST` in `scripts/results.py`, or it will not appear in the tables.

```json
{"variant": "v-…", "arm": "…", "decision": "ACCEPT|REJECT|HOLD",
 "obligations": [{"id": "ENC-1", "status": "shown|open|refuted", "note": "…"}],
 "summary": "…", "meta": {"elapsed_s": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0, "error": null}}
```

## Caveats

- The platform, the obligations and the changes are synthetic. Nothing here measures performance on a real
  bank's code or records.
- Each reviewer ran once per change; there are no repeats and no variance estimates. The one-sided 95% bound on the
  false all-clear rate is the honest summary of a single pass.
- The held-out split has 24 families of several changes each, so misses cluster by family; the per-family
  breakdown is the right place to read them.
- The tool-using arm could run the repository's CI; the packet arms saw a fixed review packet; Grok ran through
  Cursor's agent CLI in read-only mode, not a Grok CLI. These are different conditions, stated in `PROTOCOL.md`.
- "$0 API, local compute" means no API charge, not no cost.
- Nothing here has been reproduced independently yet. Reproduction is invited; the verdicts, keys, variants,
  prompts and runners are all in this repository.

## The open question

Machine-checked proofs now exist for real open-source code. A proof checks the code against a specification. The
changes that got through in this benchmark were not wrong against any specification: an earlier proof still
proved its theorem, the tests still passed, the exception had simply expired, the ticket simply did not name the
component. Proofs check the code. Who checks the change against the obligations?

## Layout

| Path | What |
|---|---|
| `platform/` | the synthetic bank platform: two apps, `controls/` (obligations, policy, approved data), `ci/` |
| `obligations/` | the catalog builder and the citation check for the 27 obligations |
| `bench/seeder/` | the variant generator, oracles and the two family packs |
| `bench/key/` | the sealed artefacts and their commitments, plus the unsealed keys for both test splits |
| `bench/score/` | the scorer |
| `baselines/` | frozen prompts, the runners for every arm that ran, fixtures and plumbing tests |
| `variants/<split>/<id>/` | `records/` plus `repo.bundle` for each of the 270 changes |
| `runs/<split>/<arm>/` | one verdict file per change, as written by the runners (host names and app names replaced, see `PROTOCOL.md`) |
| `RESULTS.md`, `reports/results.json` | regenerated by `scripts/results.py` |
| `PROTOCOL.md` | splits, sealing, freeze order, metrics, fairness notes, limits |

## Licence

Code under Apache-2.0 (`LICENSE`); the obligations, variants, keys and verdicts under CC BY 4.0 (`LICENSE-DATA.md`).
