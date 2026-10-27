"""Seal and unseal answer keys and held-out packs.

    python -m bench.seal seal   <plain> <name>      -> bench/key/<name>.enc, commitment appended, plain deleted
    python -m bench.seal unseal <name> <out-path>   -> decrypts for scoring (write outside the repo)

Passphrase: the environment variable KAB_SEAL_PASS, or the contents of the file named by KAB_SEAL_PASS_FILE. It
never enters the repo. Limits: anyone holding the passphrase can unseal. Blindness is by procedure (every arm's
verdicts are written before the key is unsealed, and the commitment hashes are committed before any scoring).
The original benchmark run kept the passphrase in the builder's OS credential store; the sealed files and their
commitments in bench/key/COMMITMENTS.md are published as they were, and the unsealed keys are published beside them.
"""
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYDIR = ROOT / "bench" / "key"


def passphrase() -> str:
    pw = os.environ.get("KAB_SEAL_PASS", "")
    if not pw and os.environ.get("KAB_SEAL_PASS_FILE"):
        pw = Path(os.environ["KAB_SEAL_PASS_FILE"]).read_text().strip()
    if not pw:
        raise SystemExit("set KAB_SEAL_PASS or KAB_SEAL_PASS_FILE")
    return pw


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def seal(plain: Path, name: str):
    KEYDIR.mkdir(parents=True, exist_ok=True)
    enc = KEYDIR / f"{name}.enc"
    env = dict(os.environ, KAB_PASS=passphrase())
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-in", str(plain), "-out", str(enc),
                    "-pass", "env:KAB_PASS"], check=True, env=env)
    line = f"| {name} | {time.strftime('%Y-%m-%d %H:%M %Z')} | `{sha256(plain)}` | `{sha256(enc)}` | {plain.stat().st_size} |\n"
    com = KEYDIR / "COMMITMENTS.md"
    if not com.exists():
        com.write_text("# Sealed artefacts\n\nSHA-256 of each plaintext and its ciphertext, recorded at sealing time and committed before any arm is scored against it.\n\n| name | sealed at | plaintext sha256 | ciphertext sha256 | bytes |\n|---|---|---|---|---|\n")
    with com.open("a") as f:
        f.write(line)
    plain.unlink()
    print(f"sealed {name}: {enc}")


def unseal(name: str, out: Path):
    enc = KEYDIR / f"{name}.enc"
    env = dict(os.environ, KAB_PASS=passphrase())
    subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-in", str(enc), "-out", str(out),
                    "-pass", "env:KAB_PASS"], check=True, env=env)
    want = None
    for row in (KEYDIR / "COMMITMENTS.md").read_text().splitlines():
        cells = [c.strip(" `") for c in row.split("|")]
        if len(cells) > 3 and cells[1] == name:
            want = cells[3]
    got = sha256(out)
    if want and got != want:
        raise SystemExit(f"commitment mismatch for {name}: {got} != {want}")
    print(f"unsealed {name} -> {out} (commitment {'verified' if want else 'not found'})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "seal":
        seal(Path(sys.argv[2]), sys.argv[3])
    elif cmd == "unseal":
        unseal(sys.argv[2], Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
