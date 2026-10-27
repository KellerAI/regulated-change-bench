"""Synthetic people directory for the Fernbrook Bank platform.

Names are invented. Nobody here maps to a real person.
"""

DOMAIN = "fernbrook.example"

PEOPLE = [
    # lending engineering (baseline-mortgage)
    {"id": "p-praman", "name": "Priya Raman", "team": "lending-eng", "roles": ["engineer"], "apps": ["baseline-mortgage"],
     "aliases": ["p.raman", "praman-hw"]},
    {"id": "p-tortega", "name": "Tomas Ortega", "team": "lending-eng", "roles": ["engineer"], "apps": ["baseline-mortgage"],
     "aliases": ["t.ortega"]},
    {"id": "p-nokafor", "name": "Nneka Okafor", "team": "lending-eng", "roles": ["engineer"], "apps": ["baseline-mortgage"],
     "aliases": ["n.okafor"]},
    {"id": "p-wli", "name": "Wen Li", "team": "lending-eng", "roles": ["engineer", "change_approver"], "apps": ["baseline-mortgage"],
     "aliases": ["w.li", "wenli-hw"]},
    {"id": "p-dfarrell", "name": "Declan Farrell", "team": "lending-eng", "roles": ["engineer", "change_approver"], "apps": ["baseline-mortgage"],
     "aliases": ["d.farrell"]},
    # payments engineering (payments)
    {"id": "p-abello", "name": "Aisha Bello", "team": "payments-eng", "roles": ["engineer"], "apps": ["baseline-payments"],
     "aliases": ["a.bello", "abello-hw"]},
    {"id": "p-jweiss", "name": "Jonah Weiss", "team": "payments-eng", "roles": ["engineer"], "apps": ["baseline-payments"],
     "aliases": ["j.weiss"]},
    {"id": "p-lnguyen", "name": "Linh Nguyen", "team": "payments-eng", "roles": ["engineer"], "apps": ["baseline-payments"],
     "aliases": ["l.nguyen"]},
    {"id": "p-mcosta", "name": "Mara Costa", "team": "payments-eng", "roles": ["engineer", "change_approver"], "apps": ["baseline-payments"],
     "aliases": ["m.costa", "mcosta-hw"]},
    {"id": "p-ssantos", "name": "Sofia Santos", "team": "payments-eng", "roles": ["engineer", "change_approver"], "apps": ["baseline-payments"],
     "aliases": ["s.santos"]},
    # security (second set of eyes for security-sensitive components)
    {"id": "p-ihalvorsen", "name": "Ines Halvorsen", "team": "platform-security", "roles": ["security_reviewer"], "apps": ["*"],
     "aliases": ["i.halvorsen"]},
    {"id": "p-kmensah", "name": "Kofi Mensah", "team": "platform-security", "roles": ["security_reviewer"], "apps": ["*"],
     "aliases": ["k.mensah"]},
    # controls office (owns controls/ and control tests)
    {"id": "p-rstein", "name": "Rachel Stein", "team": "controls-office", "roles": ["control_owner"], "apps": ["*"],
     "aliases": ["r.stein"]},
    {"id": "p-btran", "name": "Bao Tran", "team": "controls-office", "roles": ["control_owner"], "apps": ["*"],
     "aliases": ["b.tran"]},
    # technology risk (exceptions)
    {"id": "p-hvasquez", "name": "Helena Vasquez", "team": "ciso-office", "roles": ["risk_owner"], "apps": ["*"],
     "aliases": ["h.vasquez"]},
    {"id": "p-ohaddad", "name": "Omar Haddad", "team": "ciso-office", "roles": ["risk_owner"], "apps": ["*"],
     "aliases": ["o.haddad"]},
    # change management
    {"id": "p-gkim", "name": "Grace Kim", "team": "change-mgmt", "roles": ["change_manager"], "apps": ["*"],
     "aliases": ["g.kim"]},
    {"id": "p-ebrandt", "name": "Erik Brandt", "team": "change-mgmt", "roles": ["change_manager"], "apps": ["*"],
     "aliases": ["e.brandt"]},
    # automation
    {"id": "p-bot", "name": "Platform Bot", "team": "platform", "roles": ["automation"], "apps": ["*"], "aliases": []},
]

BY_ID = {p["id"]: p for p in PEOPLE}


def primary_email(pid: str) -> str:
    p = BY_ID[pid]
    first, *rest = p["name"].lower().split()
    return f"{first}.{rest[-1]}@{DOMAIN}" if rest else f"{first}@{DOMAIN}"


def emails(pid: str) -> list[str]:
    return [primary_email(pid)] + [f"{a}@{DOMAIN}" for a in BY_ID[pid]["aliases"]]


def alias_email(pid: str, i: int = 0) -> str:
    return f"{BY_ID[pid]['aliases'][i]}@{DOMAIN}"


def directory() -> dict:
    return {
        "people": [
            {"person_id": p["id"], "name": p["name"], "team": p["team"], "roles": p["roles"],
             "apps": p["apps"], "emails": emails(p["id"])}
            for p in PEOPLE
        ],
        "notes": "Emails listed for a person are all the same individual.",
    }


def with_role(role: str, app: str | None = None) -> list[str]:
    out = []
    for p in PEOPLE:
        if role in p["roles"] and (app is None or "*" in p["apps"] or app in p["apps"]):
            out.append(p["id"])
    return out


def engineers(app: str) -> list[str]:
    return [p["id"] for p in PEOPLE if "engineer" in p["roles"] and app in p["apps"]]
