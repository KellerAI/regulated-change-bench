"""Isolation helpers shared by the seeder and the engine (no engine or bench logic here).

Running a change's code: an allowlisted environment, a throwaway HOME, and on macOS a sandbox-exec
profile with no network beyond loopback, no OS credential services, and no reads of user data. Exporting a commit:
raw blobs only, so no git attributes, filters or hooks run.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


UV_PYTHON = Path.home() / ".local" / "share" / "uv" / "python"


def sandbox_profile(writable: list[Path]) -> str:
    """Seatbelt profile for the change's code. Best effort on macOS: no network, no credential or
    launch/Apple-event services, writes only inside the run's own directories, and no reads of user
    data (home trees under every alias, other runs' temp dirs) beyond the pinned toolchain.
    Production runs belong in a VM or container; see README "Isolation"."""
    def sub(p: Path) -> str:
        return '(subpath "' + os.path.realpath(p).replace('"', '') + '")'
    w = " ".join(sub(p) for p in writable)
    r = " ".join(sub(p) for p in [*writable, ROOT / ".tools", UV_PYTHON])
    mach = " ".join(f'(global-name "{n}")' for n in (
        "com.apple.SecurityServer", "com.apple.securityd", "com.apple.coreservices.launchservicesd",
        "com.apple.coreservices.appleevents", "com.apple.nsurlsessiond", "com.apple.lsd.mapdb", "com.apple.lsd.modifydb"))
    homes = str(Path.home().parent)
    private = " ".join(sub(Path(p)) for p in (homes, os.path.realpath(homes), "/private/var/folders", "/private/tmp", "/Volumes"))
    return ("(version 1)(allow default)(deny network*)"
            '(allow network-bind network-inbound (local ip "localhost:*"))'
            '(allow network-outbound (remote ip "localhost:*"))'
            f"(deny mach-lookup {mach})"
            f'(deny file-write* (require-not (require-any {w} (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))))'
            f"(deny file-read-data file-read-xattr (require-all (require-any {private}) (require-not (require-any {r}))))")


def sandboxed(cmd: list[str], writable: list[Path] | None = None) -> list[str]:
    """macOS: confine the change's code with sandbox-exec. Elsewhere the worker VM is the boundary."""
    if os.environ.get("KAB_NO_SANDBOX") == "1":
        return cmd  # already inside an outer sandbox (e.g. a Codex workspace-write session)
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        return ["/usr/bin/sandbox-exec", "-p", sandbox_profile(writable or []), *cmd]
    return cmd


def tool_env(home: Path) -> dict:
    """Allowlisted environment for running the change's code: no inherited credentials or tokens."""
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home), "TMPDIR": str(home), "LANG": "C.UTF-8",
        "JAVA_HOME": os.environ.get("KAB_JAVA_HOME", "/opt/homebrew/opt/openjdk"),
        "JUNIT_JAR": os.environ.get("KAB_JUNIT_JAR", str(ROOT / ".tools" / "junit-console.jar")),
        "PYTHON": os.environ.get("KAB_PYTHON", str(ROOT / ".tools" / "venv" / "bin" / "python")),
        "PYTHONDONTWRITEBYTECODE": "1",
        "JAVA_TOOL_OPTIONS": f"-Djava.io.tmpdir={home} -XX:-UsePerfData",
    }


SHA = re.compile(r"^[0-9a-f]{7,40}$")


def check_sha(c: str) -> str:
    if not isinstance(c, str) or not SHA.match(c):
        raise RuntimeError(f"not a commit id: {c!r}")
    return c


def export_tree(repo: Path, commit: str, dest: Path) -> list[str]:
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    base = ["git", "-C", str(repo), "-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null"]
    listing = subprocess.run(base + ["ls-tree", "-r", "-z", "--end-of-options", check_sha(commit)],
                             capture_output=True, check=True, env=env).stdout
    entries, skipped = [], []
    for rec in listing.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha = meta.split()
        rel = path.decode()
        if kind != b"blob" or mode == b"120000" or rel.startswith("/") or ".." in Path(rel).parts:
            skipped.append(rel)
            continue
        entries.append((rel, sha.decode(), mode))
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(base + ["cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    root = dest.resolve()
    for rel, sha, mode in entries:
        proc.stdin.write(sha.encode() + b"\n")
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        size = int(header[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if not str(out.parent.resolve()).startswith(str(root)):
            raise RuntimeError(f"path escapes export root: {rel}")
        out.write_bytes(data)
        if mode == b"100755":
            out.chmod(0o755)
    proc.stdin.close()
    proc.wait()
    return skipped
