"""Helpers shared by the CLI arms (claude, codex, grok) that run unattended.

Isolation (see baselines/README.md, "Isolation of the CLI arms"):
- `guard_env()`: refuse to start when API-key or base-URL variables are exported. The CLI arms run on subscription
  logins only; an exported key would silently switch them to API billing.
- `workspace()`: a throwaway directory per variant under ~/kab-worker/runs/<rand>/ holding the variant copy (the
  agent's only material), a throwaway HOME (with its own TMPDIR), a scratch dir for CI output, the CLI's private
  config dir and the run's logs. The original variant is never touched; the whole directory is deleted afterwards.
- `minimal_env()`: PATH, the throwaway HOME and TMPDIR, LANG, the git lockdown variables (GIT_ENV), plus exactly the
  variables an arm passes (its auth variables, CLI switches, JAVA_HOME / JUNIT_JAR / PYTHON for the ci/ scripts).
  Nothing inherited: no gh, ssh agent, or other credentials.
- `harden_git()`: the copy's .git/config is cut down to core settings and its hooks are removed.
- `run_cli()`: subprocess with a wall-clock timeout, stdout/stderr captured to files.
- `looks_usage_limited()`: subscription limit / rate limit wording, so the batch stops instead of burning variants.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

FORBIDDEN_EXACT = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY",
                   "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                   "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CURSOR_API_KEY", "CURSOR_API_ENDPOINT")
FORBIDDEN_RE = re.compile(r".*(_API_KEY|_BASE_URL)$")
USAGE_RE = re.compile(r"usage limit|rate[ -]?limit|limit (?:reached|exceeded)|quota|too many requests|"
                      r"out of (?:credits|usage)|try again (?:at|in|later)|resets? at", re.I)
AUTH_RE = re.compile(r"not logged in|invalid (?:api key|token|credentials)|authenticat(?:e|ion) (?:failed|error)|"
                     r"login required|unauthori[sz]ed|\b401\b", re.I)
# Files a CLI agent auto-loads as instructions or settings from its working tree. A variant should not contain them;
# if one does, the run records it (meta.agent_instruction_files) so the verdict can be judged with that in mind.
AGENT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude", ".mcp.json", "AGENTS.md", "AGENTS.override.md", ".codex",
               ".cursor", ".cursorrules", "GROK.md", ".grok")
# Real-home paths no arm may read (Claude permission deny rules; documentation for the others).
SENSITIVE_HOME = (".ssh", ".aws", ".config", ".claude", ".claude.json", ".codex", ".cursor", ".grokbot", ".gnupg",
                  ".netrc", ".git-credentials", ".gitconfig", ".docker", ".kube", ".zshrc", ".zprofile",
                  ".bash_profile", ".npmrc", ".pypirc", "Library", "Code", "Documents", "Desktop", "Downloads")


# git inside an agent's tools: no global/system config, no extra config from GIT_CONFIG_COUNT, forced overrides via
# GIT_CONFIG_PARAMETERS (the `git -c` channel, which beats repo config), no prompts or pagers.
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "0",
           "GIT_CONFIG_PARAMETERS": "'diff.external=' 'core.fsmonitor=' 'core.pager=cat' 'core.hooksPath=/dev/null'",
           "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "PAGER": "cat", "GIT_OPTIONAL_LOCKS": "0"}


class VariantRejected(RuntimeError):
    """The variant copy has a shape the agent arms refuse to run on (symlinks, git indirection)."""


def check_copy(root: Path, repo: Path) -> None:
    """Refuse a copy with any symlink, any `.git` entry other than repo/.git, a `.git` that is not a plain directory,
    a `gitdir:` pointer file anywhere, or git indirection (commondir, gitdir, object alternates): any of them could
    point the agent's tools outside the throwaway workspace."""
    gitdir = repo / ".git"
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                raise VariantRejected(f"symlink in variant copy: {p.relative_to(root)}")
            if name == ".git" and p != gitdir:
                raise VariantRejected(f"extra .git entry in variant copy: {p.relative_to(root)}")
        for name in filenames:
            p = Path(dirpath) / name
            try:
                with open(p, "rb") as f:
                    head = f.read(16)
            except OSError:
                continue
            if head.lstrip().lower().startswith(b"gitdir:"):
                raise VariantRejected(f"gitdir: pointer file in variant copy: {p.relative_to(root)}")
    if gitdir.exists() and (gitdir.is_symlink() or not gitdir.is_dir()):
        raise VariantRejected("repo/.git is not a plain directory (gitdir indirection)")
    for ind in ("commondir", "gitdir", "objects/info/alternates", "objects/info/http-alternates"):
        if (gitdir / ind).exists():
            raise VariantRejected(f"git indirection in variant copy: .git/{ind}")


def _inside(path: Path, root: Path) -> Path:
    rp = path.resolve()
    if rp != root.resolve() and root.resolve() not in rp.parents:
        raise VariantRejected(f"{path} resolves outside the workspace ({rp})")
    return rp
_KEEP_CORE = ("repositoryformatversion", "filemode", "bare", "logallrefupdates", "ignorecase", "precomposeunicode",
              "symlinks")


def harden_git(repo: Path) -> List[str]:
    """Strip the copied repo's .git/config to core settings (and extensions.objectformat), and remove hooks, so no
    variant-supplied config (diff.external, textconv drivers, core.fsmonitor, core.pager, aliases, includes) or hook
    can run when the agent uses git. Returns what was removed, for the run's meta."""
    import configparser
    root = repo.parent.parent  # ws.root
    gitdir = _inside(repo / ".git", root)
    removed: List[str] = []
    cfg_path = _inside(gitdir / "config", root)
    if cfg_path.is_file():
        cp = configparser.RawConfigParser(strict=False)
        try:
            cp.read(cfg_path)
            sections = cp.sections()
        except configparser.Error:
            sections = ["<unparseable>"]
            cp = configparser.RawConfigParser()
        lines = ["[core]"]
        if cp.has_section("core"):
            for k, v in cp.items("core"):
                if k in _KEEP_CORE:
                    lines.append(f"\t{k} = {v}")
                else:
                    removed.append(f"core.{k}")
        if cp.has_section("extensions") and cp.has_option("extensions", "objectformat"):
            lines += ["[extensions]", f"\tobjectformat = {cp.get('extensions', 'objectformat')}"]
        removed += [f"[{x}]" for x in sections if x not in ("core", "extensions")]
        cfg_path.write_text("\n".join(lines) + "\n")
    for name in ("hooks", "info/attributes"):
        p = _inside(gitdir / name, root)
        if p.is_dir():
            if any(f for f in p.iterdir() if not f.name.endswith(".sample")):
                removed.append(f".git/{name}/*")
            shutil.rmtree(p)
        elif p.is_file():
            removed.append(f".git/{name}")
            p.unlink()
    return removed


def guard_env(extra_allowed=()) -> None:
    bad = [k for k in os.environ if (k in FORBIDDEN_EXACT or FORBIDDEN_RE.match(k)) and k not in extra_allowed]
    if bad:
        raise SystemExit(f"refusing to start: {', '.join(sorted(bad))} exported (the CLI arms use subscription "
                         f"logins only; unset them)")


def cli_path() -> str:
    """System dirs plus the usual CLI install locations (~/.local/bin, Homebrew, a Homebrew node for npm launchers)."""
    home = str(Path.home())
    dirs = [f"{home}/.local/bin", f"{home}/.local/node/bin", "/opt/homebrew/bin", "/opt/homebrew/opt/node/bin",
            "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return ":".join(d for d in dirs if Path(d).is_dir())


@dataclass
class Workspace:
    root: Path      # ~/kab-worker/runs/<rand>/
    variant: Path   # root/<variant-id>/  (repo/ + records/)
    home: Path      # root/home  (throwaway HOME; TMPDIR = home/tmp)
    scratch: Path   # root/scratch (CI out-dirs)
    cfg: Path       # root/cfg  (private CLI config)
    logs: Path      # root/logs
    git_removed: Optional[List[str]] = None   # what harden_git() stripped from the copy

    @property
    def repo(self) -> Path:
        return self.variant / "repo"

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def agent_files(self) -> List[str]:
        found = []
        for base in (self.variant, self.repo):
            for name in AGENT_FILES:
                if (base / name).exists():
                    found.append(str((base / name).relative_to(self.variant)))
        return found


def workspace(variant_dir: Path, work_root) -> Workspace:
    work_root = Path(os.path.expanduser(str(work_root)))
    work_root.mkdir(parents=True, exist_ok=True)
    root = work_root / secrets.token_hex(6)
    root.mkdir(mode=0o700)
    dst = root / variant_dir.name
    shutil.copytree(variant_dir, dst, symlinks=True)
    ws = Workspace(root=root, variant=dst, home=root / "home", scratch=root / "scratch", cfg=root / "cfg",
                   logs=root / "logs")
    for d in (ws.home, ws.home / "tmp", ws.scratch, ws.cfg, ws.logs):
        d.mkdir(mode=0o700, exist_ok=True)
    try:
        check_copy(root, ws.repo)
        if (ws.repo / ".git").is_dir():
            ws.git_removed = harden_git(ws.repo)
    except Exception:
        ws.cleanup()
        raise
    return ws


def minimal_env(ws: Workspace, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {"PATH": cli_path(), "HOME": str(ws.home), "TMPDIR": str(ws.home / "tmp") + "/", "LANG": "en_US.UTF-8",
           **GIT_ENV}
    env.update(extra or {})
    return env


def toolchain_env(pairs: List[str]) -> Dict[str, str]:
    """--env KEY=VALUE pairs for the ci/ scripts; only toolchain variables are accepted."""
    allowed = {"JAVA_HOME", "JUNIT_JAR", "PYTHON"}
    out = {}
    for kv in pairs:
        k, _, v = kv.partition("=")
        if k not in allowed:
            raise SystemExit(f"--env {k}: only {sorted(allowed)} may be passed to the agent")
        out[k] = os.path.expanduser(v)
    return out


@dataclass
class CliRun:
    returncode: Optional[int]
    timed_out: bool
    elapsed_s: float
    stdout: str
    stderr: str


def run_cli(argv: List[str], cwd: Path, env: Dict[str, str], timeout_s: float, stdin_text: Optional[str] = None,
            log_dir: Optional[Path] = None) -> CliRun:
    t0 = time.time()
    log_dir = log_dir or cwd
    so, se = log_dir / "cli.stdout", log_dir / "cli.stderr"
    with open(so, "w") as fo, open(se, "w") as fe:
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.PIPE if stdin_text is not None else
                             subprocess.DEVNULL, stdout=fo, stderr=fe, text=True, start_new_session=True)
        timed_out = False
        try:
            p.communicate(input=stdin_text, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=20)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
    return CliRun(returncode=p.returncode, timed_out=timed_out, elapsed_s=round(time.time() - t0, 2),
                  stdout=so.read_text(errors="replace"), stderr=se.read_text(errors="replace"))


def looks_usage_limited(*texts: str) -> bool:
    """Apply only to a failed CLI call's error output, never to a model's answer (which may discuss rate limits)."""
    return any(t and USAGE_RE.search(t[-4000:]) for t in texts)


def looks_auth_failed(*texts: str) -> bool:
    return any(t and AUTH_RE.search(t[-4000:]) for t in texts)


def read_token(path: Path) -> str:
    """A mode-600 token file owned by the user; the value is only ever passed through the environment."""
    st = path.stat()
    if st.st_uid != os.getuid() or (st.st_mode & 0o077):
        raise SystemExit(f"{path}: must be owned by you with mode 600 (is {oct(st.st_mode & 0o777)})")
    tok = path.read_text().strip()
    if not tok:
        raise SystemExit(f"{path}: empty")
    return tok


def redact(text: str, secret: Optional[str]) -> str:
    return text.replace(secret, "[REDACTED]") if secret and text else text
