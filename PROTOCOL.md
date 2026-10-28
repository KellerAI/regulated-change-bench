# Protocol

How the benchmark was built, sealed, run and scored. Dates and times are Pacific (UTC-7) and come from the
commits of the private build repository; the public repository was assembled from it afterwards.

## 1. Question

On blind seeded changes to a synthetic regulated platform, which automated reviewers give a **false all-clear**
(ACCEPT on a change that violates an obligation), and at what cost in false alarms, holds, money and time?

## 2. The platform and the obligations

One repository, "the Fernbrook Bank platform" (a synthetic institution; no real bank, customer, vendor or person):

- `apps/baseline-mortgage`: a loan-origination service in Java 17 (JDK only, JUnit 5), package `mortgage`.
- `apps/baseline-payments`: a payment-disbursement service in Python 3.11 (standard library, pytest), package `payments`.
- `controls/`: the bank-owned area. `obligations.json` (27 obligations), `change-policy.md` (the change-management
  standard, process obligations CHG-1 to CHG-7, EXC-1, LAP-1), and per app the approved access policy, policy
  parameters, asset inventory, components map, control-test registry and protected paths.
- Control tests live in the apps' test trees and are registered with an obligation, a coverage label
  (`exhaustive` over a closed domain, or `sample`) and a domain. Some obligations deliberately have sample-only
  tests, as real banks do.

The obligations are the bank's own concrete wording. Each one maps to a public rule or framework (NYDFS 23 NYCRR
Part 500 as amended 2023; PCAOB AS 2201 and AS 2110; COSO 2013; the FFIEC IT Examination Handbook, Development,
Acquisition, and Maintenance and Architecture, Infrastructure, and Operations booklets; AICPA Trust Services
Criteria). `obligations/citations.md` records the check of every citation against the source, with the fit of each
("direct", "maps to", or "bank policy goes beyond the rule"). The rule texts are paraphrased, never quoted at
length, and nothing claims that a control satisfies a regulation.

Labels are ground truth, not policy artefacts: a change is defective only if the code or the records actually
violate an obligation as the catalog and the change standard define it, confirmed by an oracle. A clean change
touching a sample-only obligation is labelled clean.

## 3. A variant

Every reviewer saw the same thing per change: `repo/` (a git repository with the platform's main history, prior
accepted changes, and the change branch of one to three commits) and `records/` (the change request, tickets,
approvals bound to commit ids, the people directory with aliases, the exception register, the acceptance ledger
of earlier changes with their evidence, imported evidence documents, the change's own CI run as JUnit XML with
`run.json`, and the review time). Variant ids are random. Nothing in a variant names its family, mode or label;
commit messages, PR prose and author names come from pools shared by clean and defective variants, and a leak
scan drops any variant whose text mentions seeding, defects, oracles or benchmarks.

## 4. Families, oracles and splits

A family is a template that applies a realistic carrier change (a new field, route, report, integration,
refactor, parameter update) and either plants exactly one obligation violation (two when one implies the other,
for example a defect that also leaves CI red) or produces a clean twin that looks the same and violates nothing.
Every variant carries an oracle: a hidden test stronger than the shipped controls, or a predicate that re-derives
a process obligation from the records and git. The generator runs the oracle at build time and discards any
variant whose oracle disagrees with its label; discards are counted in the key.

| Split | Families | Written by | Seed | Changes | Defective | Clean | Discarded |
|---|---|---|---|---|---|---|---|
| seen (`test-seen`) | 38 (`bench/seeder/packs/dev`) | the benchmark builder | `test-B` | 134 | 76 | 58 | 2 (oracle disagreement) |
| held-out (`test-heldout`) | 24 (`bench/seeder/packs/heldout`) | a second model lineage, see below | `test-C` | 136 | 88 | 48 | 0 |

The clean share was set at about 40% per split. The two splits are never pooled.

**How the held-out pack was authored.** A separate agent of a different model lineage (an OpenAI GPT model
through the Codex CLI, in a workspace-write sandbox with no network) wrote the 24 held-out families from the apps,
the obligation catalog, the change standard and the seeder's API documentation only. Its workspace held none of
the first builder's families, runners, prompts, results or design notes. Its pack and its full session log were
sealed on 2026-10-23 at 13:52, before any scoring (commitments `heldout-pack` and `heldout-author-log` in
`bench/key/COMMITMENTS.md`). The pack's own README, written by that agent, is published with it.

## 5. Sealing, commitments and freeze order

Keys and the held-out pack were encrypted (`openssl enc -aes-256-cbc -pbkdf2`, 200,000 iterations) with a
passphrase that never entered the repository. The SHA-256 of each plaintext and of each ciphertext was committed
before any arm was scored (`bench/key/COMMITMENTS.md`; the ciphertexts are published beside it):

| Artefact | Sealed at | Plaintext SHA-256 |
|---|---|---|
| test-seen key | 2026-10-23 13:30 | `773ee3aaa5917f4885ccf0f3dae60a22c44621e1720970eabba48feb8c831e82` |
| test-heldout key | 2026-10-23 13:52 | `2d1ac8086229799f0df886f0f3df94a6c6eed7a315a03934ae7af79a048d85f7` |
| held-out pack source | 2026-10-23 13:52 | `c178469ecdb5953fd8639dfa541fa9a77053a1a87b0adfb9f870ea882afde4b6` |
| held-out author's session log | 2026-10-23 13:52 | `c04d9ef7bebe64e21d43d594e070834bbe29c153bf51e75f0ba6d6524041390c` |

Order of events, from the build repository's commit timestamps:

1. 2026-10-23 13:30: the seen split generated and its key sealed; commitment committed. 13:31: the three prompts
   frozen (tag `prompts-frozen`).
2. 2026-10-23 13:52: the held-out split generated from the independently authored pack; key, pack and author log
   sealed; commitments committed.
3. 2026-10-23 13:52 to 22:30: every arm ran on the seen split. 22:30: the seen key unsealed and the split scored.
4. 2026-10-23 to 2026-10-24: every arm ran on the held-out split. 2026-10-24 14:26: the held-out key unsealed and
   the split scored.

No prompt, runner or arm was changed between the freeze and the scoring of a split.

## 6. Reviewers (arms)

All arms used the frozen prompts in `baselines/prompts/`. Every verdict records the SHA-256 of the prompt it was
given (`meta.prompt_sha256`), the elapsed time, the token counts where the backend reports them, and the cost
basis.

| Arm (directory) | What it is | What it saw | Model, version |
|---|---|---|---|
| `opus-packet` | Claude Opus 5.5 on Amazon Bedrock, one call, no tools | the review packet | `us.anthropic.claude-opus-5-5`, effort high, max 32,000 output tokens |
| `claude-code` | Claude Code with tools: the `claude` CLI in print mode on Bedrock, read-only tools (Read, Grep, Glob; Bash only for `sh ci/run-tests.sh`, `sh ci/run-controls.sh`, `git diff`, `git log`, `git show`), network off, writes confined to a scratch directory. This is the Claude Code CLI, not a hosted code-review product | a throwaway copy of the whole variant; could run the repository's CI | CLI 2.1.287, `us.anthropic.claude-opus-5-5`, effort high, per-change budget $8 |
| `gpt-oss-120b` | gpt-oss:120b on a local Ollama server, one call, no tools, schema-constrained answer | the review packet | `gpt-oss:120b`, think high, seed 7, context 65,536 |
| `qwen3.8-27b` | Qwen 3.8 27B on local Ollama, one call, no tools, schema-constrained answer | the review packet | `qwen3.8:27b-mxfp8`, think on, seed 7, context 65,536 |
| `grok-cli` | Grok 4.7 through Cursor's agent CLI in read-only "ask" mode with its sandbox on, in a workspace holding only the packet. The arm name is historical: no standalone Grok CLI with a scoped login was available | the review packet, as a file | `grok-4.7-medium`, `cursor-agent 2026.10.22` |
| `ponens-no-trace` | Imandra's Ponens CI action run as a pull request without a published trace would meet it, with the action's default inputs | an export of the head commit | Ponens 1.22.0 (commit `2f91978`), action driver from the same commit |
| `ponens-agent-trace` | the same action, after a local model playing the change's coding agent writes the reasoning trace from the review packet; the verdict is Ponens's own deterministic goal resolution over the bank's 27 obligations as acceptance criteria | the packet (agent), the head export with the trace (action) | PR agent `gpt-oss:120b`, think high; Ponens 1.22.0 |

The review packet (`baselines/common/packet.py`) holds, in order: the obligation catalog, the change standard and
the rest of `controls/` at the base commit (the approved versions); the commits; the diff; the full text of every
changed file at head; every record file verbatim; and a digest of the CI run (run record, suite counts, failures,
and the test cases by class). Packets were 25,000 to 45,000 tokens.

Not run: the Codex CLI was not run (no scoped login was available on the machine that ran the CLI arms). The
Grok arm ran through Cursor's agent rather than a Grok CLI for the same reason.

**Fairness notes.** The tool-using arm could read the repository and run CI; the packet arms saw a fixed packet and
could not. Grok's harness (Cursor's agent) differs from the other CLIs. The local models carry "$0 API, local
compute": no API charge was incurred, not no cost. The Claude arms are priced at Bedrock's list price for Opus 5.5
from actual token counts (input $4, output $20, cache read $0.20, cache write $5 per million); Bedrock is partner-
priced, so treat those figures as list, not invoice. The Ponens no-trace arm makes no model call. One run per
change for every arm.

## 7. Metrics

Per arm and per split, from `bench/score/score.py`:

- **False all-clear** (primary): ACCEPT on a defective change. Count, rate, and the one-sided 95% Clopper-Pearson
  upper bound on the rate. The count of critical-severity misses is reported separately.
- **False alarm**: REJECT on a clean change.
- **Hold**: HOLD on a clean change (the cost of caution). HOLD on a defective change is not a false all-clear.
- **Clean clearance**: ACCEPT on a clean change.
- **Localization**: among caught defective changes, those whose verdict names a planted obligation as `refuted`
  or `open` (in `reports/results.json`).
- **Cost**: USD as priced above, or the stated basis. **Time**: wall seconds per change.
- **Errors**: no parseable verdict, or a runner failure. They count as "not ACCEPT" and are listed separately.
  There was one error across the published runs (Grok, seen split: a dropped connection).

The 30-change common subset per split (`runs/<split>/subset-paid.txt`) is a random sample on which every arm ran
first. Qwen 3.8 and Ponens with a post-hoc trace (gpt-oss-120b) were then run on the rest of each split, the held-out split and
the seen split, after the keys had been unsealed (the seen key on 2026-10-23, 22:30), with the frozen prompts, the
same model digests and no change to any runner or to the Ponens engine. Those two arms' rows are therefore not
blind in the sealing sense on either split, and the two arms are compared with the others on the common subset
where blindness matters. Every arm now covers all 134 seen changes and all 136 held-out changes; the "Changes"
column of each table in `RESULTS.md` gives each arm's n.

## 8. What the published files are, and what was changed for publication

The verdict files under `runs/` are the files the runners wrote, with these substitutions applied uniformly to the
platform, the variants (including their git history, so commit ids differ from the originals and were remapped in
every record and verdict that cites one), the keys, the prompts and the verdict texts:

- the two synthetic app names and the synthetic bank name were replaced (the bank is now "Fernbrook"; the apps are
  `baseline-mortgage`, package `mortgage`, and `baseline-payments`, package `payments`);
- the host name and user paths that the JUnit reports in `records/ci/` carried from the machine that generated
  the variants were replaced by `dev-laptop-7.local` and `/home/ci/...` (two verdicts reason about that host name;
  their wording was adjusted to match);
- the name of a bounded model-checking tool used for one kind of prior evidence was replaced by "ModelCheck";
- run metadata that identified the cloud account, profile or session was removed from `meta`.

Consequences a reader should know: the published keys are the unsealed plaintexts after the same substitutions,
so their hashes differ from the commitments; the unmodified plaintexts exist and can be shown to a reviewer who
wants to verify a commitment. The packet hash recorded in each verdict (`meta.packet_sha256`) is the hash of the
packet as the reviewer saw it, which the renamed variant no longer reproduces byte for byte. Of the three frozen
prompts, `review-agentic.md` names the two apps and so has a new hash (`c8082a273cd0386bc94cadaef31563cf0af6736e4e47ffc5b66b15e521096894`;
frozen: `4fcac1b56c32b25a887e506bc121ac3ac06396c2358319de642804f8afc4e4bf`); `review.md` and `ponens-pr-agent.md`
are byte-identical to the frozen versions. The raw model transcripts behind the verdicts are not published.

## 9. Limits

- Synthetic platform, synthetic obligations that map to public rules. Nothing here is evidence of performance on
  a bank's code.
- One builder authored the applications, the obligations and the seen families. The held-out pack and the fresh
  test seeds are the guard against tuning; they are not an outside adjudicator.
- Ground truth comes from oracles written by the same pipeline (hidden tests and record predicates);
  disagreements drop a variant rather than relabel it.
- One run per change; no repeats, no variance estimate beyond the binomial bound.
- Misses are correlated within the 24 held-out families (several changes per family), so a family that fools a
  reviewer counts more than once; the per-family breakdown in `RESULTS.md` shows this.
- The results have not been independently reproduced. Reproduction is invited: the variants, keys, prompts,
  runners and verdicts are all here, and `scripts/results.py --check` runs in CI.
