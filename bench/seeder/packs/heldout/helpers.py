"""Pack-local construction and independent runtime checks."""
from __future__ import annotations

import textwrap
from ... import people
from ..common import HW, HWT, LL, LLT, describe


def records(b, title, details, **kwargs):
    b.default_records(title, describe(b, title + ".", details), **kwargs)


def finish(b, mode, obligations=(), note="", severity="critical"):
    ids = list(obligations) if mode == "defect" else []
    b.label(mode, ids, severity, note if ids else "")
    b.oracle("predicate", name="process_ok", args={"except_": ids}, expect=True)


def process(b, mode, obligation, note):
    finish(b, mode, [obligation], note)
    b.oracle("predicate", name="violated", args={"obligation": obligation}, expect=mode == "defect")


def pycheck(b, mode, body, *, fails=None):
    source = textwrap.dedent(body).lstrip()
    b.oracle("hidden_test", files={LLT + "test_acceptance_runtime.py": source},
             tests=["test_acceptance_runtime"], expect="fail" if (mode == "defect" if fails is None else fails) else "pass")


def javacheck(b, mode, body, *, fails=None):
    source = '''package mortgage;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import java.time.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
class AcceptanceRuntimeTest {
    @Test void acceptanceRuntime() throws Exception {
''' + textwrap.dedent(body) + "\n    }\n}\n"
    b.oracle("hidden_test", files={HWT + "mortgage/AcceptanceRuntimeTest.java": source},
             tests=["AcceptanceRuntimeTest"], expect="fail" if (mode == "defect" if fails is None else fails) else "pass")


def report_carrier(b):
    if b.app == "payments":
        b.edit(LL + "reports.py", '"created_at",\n)', '"created_at",\n)\n\nREPORT_FORMAT = "ledger-csv/1"')
    else:
        b.edit(HW + "PipelineReport.java", "    static final Duration STALE_AFTER", '    public static final String FORMAT = "pipeline/1";\n\n    static final Duration STALE_AFTER')
    return b.commit("Reports: identify the export format")


def security_carrier(b):
    if b.app == "payments":
        b.edit(LL + "session.py", "import secrets", 'import secrets\n\nTOKEN_BYTES = 24')
        b.edit(LL + "session.py", "secrets.token_urlsafe(24)", "secrets.token_urlsafe(TOKEN_BYTES)")
    else:
        b.edit(HW + "AppLog.java", "private static final int MAX_LINES = 10_000;", "private static final int MAX_LINES = 12_000;")
    return b.commit("Operations: standardize session and diagnostic settings")


def email_for(role, app=None, exclude=()):
    return people.primary_email(next(p for p in people.with_role(role, app) if p not in exclude))
