# Baseline arms

Runners for the reviewer configurations. Each reviews one variant (`records/` plus `repo/`, see `PROTOCOL.md`
section 3) and writes `runs/<split>/<arm>/<variant>.json` in the verdict format below; raw model output goes to
`runs/<split>/<arm>/raw/` (gitignored, never published). Standard library only, Python 3.9+, except where noted.

| Arm | Runner | Input | Needs |
|---|---|---|---|
| opus-packet | `python3 -m baselines.claude.run --mode packet` | packet | boto3, an AWS profile with Bedrock access (`KB_AWS_PROFILE`, `KB_AWS_REGION`) |
| claude-code | `python3 -m baselines.claude.run --mode agentic` | variant copy, read-only tools | the `claude` CLI (`KB_CLAUDE_CLI`), Bedrock as above |
| gpt-oss-120b | `python3 -m baselines.ollama.run --model gpt-oss:120b` | packet | a local Ollama server with the model already pulled |
| qwen3.8-27b | `python3 -m baselines.ollama.run --model qwen3.8:27b-mxfp8` | packet | as above |
| grok-cli | `python3 -m baselines.grok.run --model grok-4.7-medium` | packet, as a file in a throwaway workspace | Cursor's `agent` CLI with a logged-in account (`KB_CURSOR_AGENT`) |
| ponens-no-trace | `python3 -m baselines.ponens.run --mode no-trace` | head export | Ponens 1.22.0 (`ponens/README.md`) |
| ponens-agent-trace | `python3 -m baselines.ponens.run --mode agent-trace` | packet -> trace -> head export | Ponens 1.22.0 and Ollama with `gpt-oss:120b` |

Common options: `--variant DIR` (repeatable) or `--variants-dir DIR`, `--runs-dir` (default `runs/`; use
`runs/<split>`), `--force`, `--limit N`, `--max-usd X` (paid arms: stop before a variant whose cost ceiling would
take the ledger past X; a $500 cap always applies). Variants that already have a verdict are skipped. The CLI arms
take `--env JAVA_HOME=... --env JUNIT_JAR=... --env PYTHON=...` for the repository's `ci/` scripts and
`--work-root` (`KB_WORK_ROOT`, default `~/kab-worker/runs`) for their throwaway workspaces.

## Verdict format

```json
{"variant": "v-…", "arm": "…", "decision": "ACCEPT|REJECT|HOLD",
 "obligations": [{"id": "ENC-1", "status": "shown|open|refuted", "note": "…"}],
 "summary": "…", "meta": {"elapsed_s": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0, "error": null}}
```

`common/verdict.py` normalises synonyms (APPROVE -> ACCEPT, violated -> refuted), drops "not applicable" entries,
and writes an unparseable answer, unknown decision or runner failure as HOLD **with `meta.error` set**; the scorer
buckets those as errors first. The model's decision is never rewritten to match its statuses; disagreement sets
`meta.inconsistent`.

## Shared pieces (`common/`)

- `variant.py`: loads `repo/` and `records/`; base and head from `records/change.json`.
- `packet.py`: the review packet for the no-tool arms: the obligation catalog, change standard and the rest of
  `controls/` at the base commit (the approved versions, whatever the change does to them), the commits, the diff,
  the full text of changed files at head, every record file verbatim, and a CI digest. `python3 -m
  baselines.common.packet <variant> --out packet.md` prints its manifest. Token estimate = characters / 3.6.
- `jsonx.py`: verdict extraction from free text (reasoning blocks stripped, balanced objects scanned, light repair).
- `ledger.py`: `runs/cost-ledger.jsonl` rows `{"ts","arm","variant","usd","basis"}` and the cap check.
- `redact.py`: token-shaped strings (JWTs, API keys, GitHub tokens, AWS key ids, PEM blocks, bearer values, long
  high-entropy base64) are replaced in every saved file.
- `cliarm.py`: workspace, environment and subprocess helpers for the CLI arms.

Prompts (`prompts/`, frozen; every verdict records `meta.prompt_sha256`): `review.md` (system prompt for packet
arms), `review-agentic.md` (tool-using CLI arms), `ponens-pr-agent.md` (the PR agent that writes a Ponens trace).
None mentions seeding, benchmarks or defects.

## Fixtures and tests

`python3 baselines/fixtures/build.py` builds two tiny variants in `fixtures/v-*/` (gitignored, reproducible
commit ids) that differ only in who gave the code review: an alias of the author (expected REJECT, CHG-2) or an
independent approver (expected ACCEPT). `KB_FAKE_AWS=1 python3 -m pytest -q baselines/tests` runs the plumbing
tests with a fake `claude` CLI: no model, no login, no network.

## Isolation of the CLI arms

Some variants deliberately contain prompt-injection text, and the agentic arm executes tools under real
credentials. For every CLI arm:

- **Throwaway workspace.** Each variant is copied under `--work-root` with a throwaway HOME and TMPDIR, a scratch
  dir for CI output and a private CLI config dir; the agent's cwd is the copy's `repo/`. The whole directory is
  deleted after the run (`--keep-work` keeps it).
- **Copy checks.** A copy is refused if any path in it is a symlink, if it has any `.git` entry other than
  `repo/.git`, if `repo/.git` is not a plain directory, if any file is a `gitdir:` pointer, or if the repository
  uses git indirection (`commondir`, `gitdir`, object alternates).
- **No checkout filters.** Where an arm needs the head tree as files (Ponens), it is written blob by blob, never
  via `git archive` or a checkout, so in-tree attributes and repo config cannot run filter drivers.
- **Git lockdown.** The copy's `.git/config` is cut to `[core]` basics, hooks and `info/attributes` are removed,
  and the environment forces `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_COUNT=0` and
  overrides for `diff.external`, `core.fsmonitor`, `core.pager` and `core.hooksPath`.
- **Minimal environment.** PATH, the throwaway HOME and TMPDIR, LANG, the git variables, the arm's own auth
  variables and CLI switches, and `JAVA_HOME`, `JUNIT_JAR`, `PYTHON` for `ci/`. Nothing else is inherited. The
  runners refuse to start if any `*_API_KEY` or `*_BASE_URL` is exported.
- **Claude Code (agentic, Bedrock):** short-lived role credentials in a read-only config and credentials pair in the
  private config dir; default permission mode (never `bypassPermissions`); `--tools Read,Grep,Glob,Bash` with an
  allowlist limited to reading, `git diff|log|show`, and the two `ci/` scripts; Write, Edit, WebFetch, WebSearch
  and sub-agents denied; Claude Code's own Bash sandbox on with no network and writes only in the copy, scratch and
  throwaway HOME; read deny rules for credential and personal paths; settings only from the private settings file;
  hooks disabled; no MCP servers. The verdict is the final message.
- **Redaction.** Every saved raw output and verdict passes through `common/redact.py`.

Residual risks are the usual ones for agent sandboxes: path-scoped deny lists cover known credential locations,
not everything on the machine; `ci/` scripts execute the variant's own test code inside the sandbox; a variant
that contained `CLAUDE.md`, `AGENTS.md` or similar would be recorded in `meta.agent_instruction_files` (the
published variants contain none; the `repo/.claude` entry in the agentic verdicts is created by the CLI itself at
run time).
