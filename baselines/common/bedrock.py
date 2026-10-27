"""Amazon Bedrock helpers for the paid arms (Claude packet and agentic on Bedrock, and the Ponens PR agent if moved).

Needs boto3. Account and profile: KB_AWS_PROFILE (default `default`) and KB_AWS_REGION (default us-east-1); the profile
must be able to invoke the system inference profile `us.anthropic.claude-opus-5-5` (Claude Opus 5.5). SSO profiles
refresh non-interactively while the SSO session lasts; the runners never log in.

Price (USD per million tokens), Claude Opus 5.5: input 4.00, output 20.00, cache read 0.20, cache write 5.00
(1.25 x input, 5-minute TTL): Anthropic's list price as of 2026-10. Bedrock is partner-priced: confirm on
aws.amazon.com/bedrock/pricing before quoting. Thinking tokens are billed as output.
"""

from __future__ import annotations

import configparser
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Dict, Optional

PROFILE = os.environ.get("KB_AWS_PROFILE", "default")
REGION = os.environ.get("KB_AWS_REGION", "us-east-1")
OPUS = "us.anthropic.claude-opus-5-5"
PRICE = {OPUS: {"in": 4.00, "out": 20.00, "cache_read": 0.20, "cache_write": 5.00}}
PRICE_BASIS = ("Bedrock Opus 5.5 list price $4/M in, $20/M out, $0.20/M cache read, $5/M cache write "
               "x actual token counts")


def usd(usage: Dict[str, int], model: str = OPUS) -> float:
    p = PRICE[model]
    return round((usage.get("input_tokens", 0) * p["in"] + usage.get("output_tokens", 0) * p["out"]
                  + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
                  + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]) / 1e6, 6)


def session(profile: str = PROFILE):
    import boto3
    return boto3.Session(profile_name=profile, region_name=REGION)


FAKE = os.environ.get("KB_FAKE_AWS") == "1"   # tests only: no AWS calls, dummy credentials


def check_credentials(profile: str = PROFILE) -> str:
    """Raise SystemExit with a clear message when the profile can't get credentials non-interactively."""
    if FAKE:
        return "000000000000"
    try:
        ident = session(profile).client("sts").get_caller_identity()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"AWS profile {profile!r} has no working credentials ({type(e).__name__}: "
                         f"{str(e)[:200]}). Needs a human login (for example `aws sso login`); "
                         f"the runners never log in.")
    return ident["Account"]


def role_credentials(profile: str = PROFILE) -> Dict[str, str]:
    """Short-lived role credentials for `profile`, fetched fresh (GetRoleCredentials with the cached SSO token, so
    nothing is written except the SDK's normal SSO-token refresh), with their expiry. Falls back to the session's
    resolved credentials for non-SSO profiles."""
    if FAKE:
        return {"aws_access_key_id": "ASIAFAKEFAKEFAKEFAKE", "aws_secret_access_key": "fakeSecretKey0123456789abcdefABCDEF0123",
                "aws_session_token": "fakeSessionToken", "expires": "2099-01-01T00:00:00Z"}
    s = session(profile)
    cfg = s._session.full_config.get("profiles", {}).get(profile, {})
    if "sso_account_id" in cfg and "sso_role_name" in cfg:
        from botocore.tokens import SSOTokenProvider
        tok = SSOTokenProvider(s._session, profile_name=profile).load_token()
        access = tok.get_frozen_token().token
        sess_name = cfg.get("sso_session")
        sso_region = (s._session.full_config.get("sso_sessions", {}).get(sess_name, {}).get("sso_region")
                      or cfg.get("sso_region") or REGION)
        rc = s.client("sso", region_name=sso_region).get_role_credentials(
            roleName=cfg["sso_role_name"], accountId=cfg["sso_account_id"], accessToken=access)["roleCredentials"]
        exp = _dt.datetime.fromtimestamp(rc["expiration"] / 1000, _dt.timezone.utc)
        return {"aws_access_key_id": rc["accessKeyId"], "aws_secret_access_key": rc["secretAccessKey"],
                "aws_session_token": rc["sessionToken"], "expires": exp.strftime("%Y-%m-%dT%H:%M:%SZ")}
    fc = s.get_credentials().get_frozen_credentials()
    return {"aws_access_key_id": fc.access_key, "aws_secret_access_key": fc.secret_key,
            "aws_session_token": fc.token or "", "expires": ""}


def write_profile_files(dest: Path, profile: str = PROFILE) -> Dict[str, str]:
    """A read-only (0400) AWS config + credentials pair for one profile, holding fresh short-lived role credentials,
    for a CLI subprocess. Returns the env vars that point at them (AWS_PROFILE, AWS_REGION, AWS_CONFIG_FILE,
    AWS_SHARED_CREDENTIALS_FILE) plus the secrets to redact under the key `_secrets`."""
    dest.mkdir(parents=True, exist_ok=True)
    creds = role_credentials(profile)
    conf = configparser.ConfigParser()
    conf[f"profile {profile}"] = {"region": REGION}
    cred = configparser.ConfigParser()
    cred[profile] = {k: v for k, v in creds.items() if k.startswith("aws_") and v}
    cfile, kfile = dest / "config", dest / "credentials"
    for path, cp in ((cfile, conf), (kfile, cred)):
        if path.exists():
            path.chmod(0o600)
        with open(path, "w") as f:
            cp.write(f)
        path.chmod(0o400)
    return {"AWS_PROFILE": profile, "AWS_REGION": REGION, "AWS_CONFIG_FILE": str(cfile),
            "AWS_SHARED_CREDENTIALS_FILE": str(kfile), "_expires": creds["expires"],
            "_secrets": json.dumps([creds["aws_secret_access_key"], creds["aws_session_token"]])}


def invoke_messages(body: dict, model: str = OPUS, profile: str = PROFILE, read_timeout: int = 1800) -> dict:
    """InvokeModel with Anthropic's native Messages body (anthropic_version bedrock-2023-05-31)."""
    from botocore.config import Config
    client = session(profile).client("bedrock-runtime",
                                     config=Config(read_timeout=read_timeout, retries={"max_attempts": 3,
                                                                                         "mode": "adaptive"}))
    payload = {"anthropic_version": "bedrock-2023-05-31", **body}
    r = client.invoke_model(modelId=model, body=json.dumps(payload), contentType="application/json",
                            accept="application/json")
    return json.loads(r["body"].read())
