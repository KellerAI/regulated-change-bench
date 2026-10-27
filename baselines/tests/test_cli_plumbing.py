"""Plumbing tests for the CLI arms with fake CLIs (no model, no login, no network, no AWS: KB_FAKE_AWS=1).

    python3 baselines/fixtures/build.py && .tools/venv/bin/python -m pytest -q baselines/tests
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAKES = Path(__file__).resolve().parent / "fakes"
FIXTURE = ROOT / "baselines" / "fixtures" / "v-q7m2ka"
sys.path.insert(0, str(ROOT))


def _run(mod, args, tmp_path, extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL"))}
    env.update({"SSH_AUTH_SOCK": "/tmp/fake-agent", "AWS_ACCESS_KEY_ID": "AKIAOUTEROUTEROUTER1"})
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, "-m", mod, *args, "--variant", str(FIXTURE), "--runs-dir",
                        str(tmp_path / "runs"), "--work-root", str(tmp_path / "work"), "--force"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def test_claude_agentic_isolation(tmp_path):
    env = {"KB_FAKE_AWS": "1", "KB_LEDGER": str(tmp_path / "ledger.jsonl")}
    _run("baselines.claude.run", ["--mode", "agentic", "--claude-cli", str(FAKES / "claude"),
                                  "--env", "PYTHON=/usr/bin/python3"], tmp_path, env)
    v = json.loads((tmp_path / "runs/claude-code/v-q7m2ka.json").read_text())
    assert v["decision"] == "HOLD" and v["meta"]["error"] is None
    # 1000 in x $4 + 2000 out x $20 + 100k cache read x $0.20 + 20k cache write x $5, per million tokens
    assert abs(v["meta"]["usd"] - 0.164) < 1e-9
    row = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[-1])
    assert row["arm"] == "claude-code" and abs(row["usd"] - 0.164) < 1e-9
    out = (tmp_path / "runs/claude-code/raw/v-q7m2ka.cli.stdout").read_text()
    dbg = json.loads(out.strip().splitlines()[-1])["debug"]
    argv = dbg["argv"]
    assert "bypassPermissions" not in argv and argv[argv.index("--permission-mode") + 1] == "default"
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob,Bash"
    assert argv[argv.index("--model") + 1] == "us.anthropic.claude-opus-5-5"
    allowed = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
    assert "Bash" not in allowed and "Bash(sh ci/run-tests.sh:*)" in allowed
    assert "Bash(git diff --output:*)" in argv[argv.index("--disallowedTools"):]
    sb = dbg["sandbox"]
    assert sb["enabled"] and sb["allowUnsandboxedCommands"] is False and sb["network"]["allowedDomains"] == []
    keys = set(dbg["env_keys"]) - {"__CF_USER_TEXT_ENCODING"}
    assert keys <= {"PATH", "HOME", "TMPDIR", "LANG", "PYTHON", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_USE_BEDROCK",
                    "AWS_PROFILE", "AWS_REGION", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE",
                    "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL", "DISABLE_AUTOUPDATER",
                    "DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                    "CLAUDE_CODE_NO_MODEL_FALLBACK", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_TERMINAL_PROMPT", "GIT_PAGER", "PAGER",
                    "GIT_OPTIONAL_LOCKS"}, keys
    assert dbg["cwd"].endswith("/v-q7m2ka/repo") and dbg["home"].startswith(str(tmp_path / "work"))
    assert dbg["gitcfg"].startswith("[core]") and "[" not in dbg["gitcfg"].split("\n", 1)[1]
    assert dbg["hooks"] is False and dbg["creds_mode"] == "0o400"
    err = (tmp_path / "runs/claude-code/raw/v-q7m2ka.cli.stderr").read_text()
    assert "fakeSecretKey0123456789abcdefABCDEF0123" not in err and "eyJhbGciOiJIUzI1NiJ9" not in err
    assert "[REDACTED]" in err
    assert not any((tmp_path / "work").iterdir()), "workspace not cleaned up"


def test_redaction():
    from baselines.common.redact import redact_text
    s = ("sha b0970d360e79f1c2a3b4c5d6e7f8091a2b3c4d5e path /home/x/kab-worker/runs/ab/v-q7m2ka/repo "
         "jwt eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijk key sk-ant-oat01-AbCdEf0123456789xyz "
         "gh gho_16C7e42F292c6912E7710c838347Ae178B4a aws AKIAIOSFODNN7EXAMPLE")
    r = redact_text(s)
    assert "b0970d360e79f1c2a3b4c5d6e7f8091a2b3c4d5e" in r and "/home/x/kab-worker/runs/ab/v-q7m2ka/repo" in r
    for secret in ("eyJhbGci", "sk-ant-oat01", "gho_16C7", "AKIAIOSFODNN7EXAMPLE"):
        assert secret not in r


def test_workspace_rejects_symlinks_and_git_indirection(tmp_path):
    import shutil
    from baselines.common import cliarm
    for name, mutate in (("v-link", lambda d: os.symlink("/etc/hosts", d / "repo" / "hosts")),
                         ("v-gitfile", lambda d: (shutil.rmtree(d / "repo" / ".git"),
                                                  (d / "repo" / ".git").write_text("gitdir: /tmp/elsewhere\n"))),
                         ("v-alt", lambda d: (d / "repo" / ".git" / "objects" / "info").mkdir(parents=True,
                                                                                             exist_ok=True)
                          or (d / "repo" / ".git" / "objects" / "info" / "alternates").write_text("/tmp/x\n")),
                         ("v-nested", lambda d: (d / "repo" / "apps" / ".git").mkdir()),
                         ("v-pointer", lambda d: (d / "records" / "notes.txt").write_text("gitdir: /etc\n"))):
        bad = tmp_path / name
        shutil.copytree(FIXTURE, bad, symlinks=True)
        mutate(bad)
        try:
            cliarm.workspace(bad, tmp_path / "work")
            raise AssertionError(f"{name} not rejected")
        except cliarm.VariantRejected:
            pass
    assert not any((tmp_path / "work").iterdir())
