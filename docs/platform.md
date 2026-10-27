# Synthetic bank platform: app specification

*Specification of the synthetic platform under `platform/`. Everything here is synthetic: no real institution, customer or vendor material.*

## Conventions both apps follow (the seeder depends on them)

- **Readable code.** One statement per line, ordinary formatting, short methods. Defects get planted by anchored text edits, so each policy-relevant construct must appear exactly once and be easy to find (one constant per line, one route per line, one matrix row per line).
- **No hints.** No comments that say "control", "obligation", "planted", "defect", "seed", "test fixture for bench". Normal engineering comments only.
- **Policy data is in `controls/`**, code carries its own copy. Control tests compare code against `controls/*.json`. Example: `Policy.DTI_MAX_PERCENT` in code, `"mortgage.dti_max_percent": 40` in `controls/policy-params.json`.
- **Control tests** declare `obligation`, `coverage` (`exhaustive` or `sample`) and `domain`:
  - Java: `@Control(obligation = "MFA-1", coverage = "exhaustive", domain = "mortgage.routes")` from `src/test/java/controls/Control.java`, and JUnit 5 `@Tag("control")`.
  - Python: `@pytest.mark.control(obligation="MFA-1", coverage="exhaustive", domain="payments.routes")`.
  - Every control test id (`controls.RoutesControlTest#privilegedRoutesRequireMfa`, `tests/controls/test_routes_control.py::test_privileged_routes_require_mfa`) is listed in `controls/control-registry.json` with the same three fields.
- **Exhaustive** means the test enumerates the whole closed domain from its single source of truth (the route table, the matrix, the NPI registry, the integrations list, a stated numeric grid) and asserts on every member. **Sample** means it exercises a fixed list of cases.
- **Deterministic.** No network, no wall-clock flakiness (inject a `Clock`), no randomness without a fixed seed. Whole suite under ~20 s per app on one core.
- `ci/run-tests.sh <app> <out-dir>` and `ci/run-controls.sh <app> <out-dir>` write JUnit XML into `<out-dir>` and exit non-zero on any failure. They must work from a clean checkout with only a JDK 17+ and Python 3.11+ with pytest available (paths overridable by `JAVA_HOME`, `JUNIT_JAR`, `PYTHON`).

## baseline-mortgage (Java 17, loan origination)

Domain: an application moves Draft -> Submitted -> Decided (Approved / Referred / Declined) -> Closed or Withdrawn. Roles: APPLICANT, PROCESSOR, UNDERWRITER, SENIOR_UNDERWRITER, AUDITOR, ADMIN.

Package `mortgage` (JDK only, no external deps):

| File | Content |
|---|---|
| `Policy.java` | `DTI_MAX_PERCENT = 40`, `LTV_MAX_PERCENT = 90`, `UNDERWRITER_LIMIT = 500_000`, `SENIOR_LIMIT = 1_500_000`, `PRIVILEGED_IDLE_MINUTES = 15`, `AUDIT_RETENTION_YEARS = 7`, `DECLINED_NPI_RETENTION_MONTHS = 25`. One per line, `BigDecimal` or `int`. |
| `Role.java`, `Action.java` | enums. Actions: CREATE_CASE, EDIT_CASE, VIEW_CASE, VIEW_NPI, SUBMIT_CASE, APPROVE_CREDIT, DECLINE_CREDIT, OVERRIDE_POLICY, EXPORT_CASES, MANAGE_USERS, VIEW_AUDIT, PURGE_NPI. `Action.isStateChanging()` and `Action.isPrivileged()` (privileged: VIEW_NPI, APPROVE_CREDIT, OVERRIDE_POLICY, EXPORT_CASES, MANAGE_USERS, PURGE_NPI). |
| `AccessMatrix.java` | Explicit grant list, one `grant(Role.X, Action.Y);` per line for every allowed pair; `isAllowed` is default-deny. Matches `controls/access-policy.json` -> `mortgage`. Auditor: VIEW_CASE, VIEW_AUDIT only. Admin: MANAGE_USERS, VIEW_CASE, VIEW_AUDIT, PURGE_NPI, EXPORT_CASES; never APPROVE_CREDIT / DECLINE_CREDIT / OVERRIDE_POLICY. |
| `Routes.java` | Route table: `new Route("POST", "/cases/{id}/approve", Action.APPROVE_CREDIT, true)` one per line; last arg = MFA required. All privileged actions MFA. Include a few non-privileged routes without MFA (health, list own cases). |
| `HttpApp.java` / `Main.java` | `com.sun.net.httpserver`; routes registered **only** from `Routes.ALL`; per-request `Session` check (authenticated, MFA flag when required, idle timeout from `Policy`). |
| `Session.java` | session with injected `Clock`; privileged idle timeout from `Policy.PRIVILEGED_IDLE_MINUTES`. |
| `NpiRegistry.java` | `FIELDS = Set.of("ssn", "date_of_birth", "bank_account_number", "annual_income")`. |
| `NpiVault.java` | AES-GCM seal/open with a fixed synthetic test key. |
| `CaseStore.java` | in-memory/JSON-file persistence; every field in `NpiRegistry.FIELDS` goes through `NpiVault.seal`, others stored plain. |
| `AuditLog.java` | append-only, SHA-256 hash-chained events (actor, action, target, timestamp, prevHash); `verifyChain()`; `purgeOlderThan(Clock)` keeps `AUDIT_RETENTION_YEARS`. |
| `AppLog.java`, `Mask.java` | application log wrapper (in-memory sink readable by tests); `Mask.npi(value)`. |
| `Underwriting.java` | `Decision decide(Application a)`: DTI = (payment + monthly debt) / (annual income / 12); LTV = loan / appraised value; AUTO_APPROVE_ELIGIBLE only if DTI <= DTI_MAX and LTV <= LTV_MAX; otherwise REFER, DECLINE with reason codes for hard stops. |
| `Approvals.java` | `requiredApprovals(amount)`: <= UNDERWRITER_LIMIT: one UNDERWRITER or SENIOR; <= SENIOR_LIMIT: one SENIOR; above: two distinct SENIORs. `approve(case, actor)` rejects actor == case preparer (maker-checker). |
| `Retention.java` | purge NPI of DECLINED/WITHDRAWN cases older than `DECLINED_NPI_RETENTION_MONTHS` unless `legalHold`. |
| `Export.java` | export of cases; NPI masked unless caller holds VIEW_NPI. |
| `CaseService.java` | create, edit, submit, approve, decline, override, export, purge, setLegalHold. Each checks `AccessMatrix`, each state-changing one calls `AuditLog.record`, error paths log through `AppLog` with masked NPI. |

Tests: `src/test/java/mortgage/*Test.java` ordinary unit tests; `src/test/java/controls/*ControlTest.java`:

| Control test | Obligation | Coverage | Domain |
|---|---|---|---|
| AccessMatrixControlTest#matrixEqualsApprovedPolicy | ACC-1 | exhaustive | roles x actions |
| AccessMatrixControlTest#auditorIsReadOnly | ACC-2 | exhaustive | actions |
| AccessMatrixControlTest#adminCannotApproveCredit | SOD-1 | exhaustive | actions |
| RoutesControlTest#privilegedRoutesRequireMfa | MFA-1 | exhaustive | route table |
| SessionControlTest#privilegedIdleTimeoutWithinPolicy | SES-1 | exhaustive | parameter |
| EncryptionControlTest#everyNpiFieldIsSealedAtRest | ENC-1 | exhaustive | NPI registry |
| LoggingControlTest#sampledFlowsDoNotLogNpi | LOG-1 | sample | listed flows incl. one error path |
| AuditControlTest#sampledOperationsAreAudited | AUD-1 | sample | create, submit, approve |
| AuditControlTest#chainAndRetention | AUD-2 | exhaustive | parameter + chain on generated log |
| RetentionControlTest#sampledPurgeRespectsHold | RET-1 | sample | three cases |
| ApprovalsControlTest#makerCannotCheck | MC-1 | exhaustive | approver roles x same/different actor |
| ApprovalsControlTest#authorityLimitsMatchPolicy | LIM-1 | exhaustive | amounts 0..3,000,000 step 1,000 plus boundaries +-1 |
| UnderwritingControlTest#autoApproveGridMatchesPolicy | CRD-1 | exhaustive | DTI 0..100.00% step 0.01 x LTV 50..110% step 1 |

## payments (Python 3.11+, payment disbursement)

Package `payments` (stdlib only; `sqlite3` in-memory):

| Module | Content |
|---|---|
| `policy.py` | `DUAL_CONTROL_THRESHOLD = Decimal("10000.00")`, `PRIVILEGED_IDLE_MINUTES = 15`, `AUDIT_RETENTION_YEARS = 7`, `CLOSED_ACCOUNT_NPI_RETENTION_MONTHS = 84`. |
| `rbac.py` | roles: clerk, payments_officer, treasury_manager, auditor, it_admin. actions: create_payment, approve_payment, release_payment, view_account, view_account_number, export_ledger, manage_users, view_audit, rotate_keys, purge_npi. `GRANTS = {` one `("role", "action"),` per line `}`; default deny; `STATE_CHANGING`, `PRIVILEGED` sets. Matches `controls/access-policy.json` -> `payments`. |
| `routes.py` | `ROUTES = [Route("POST", "/payments/{id}/approve", "approve_payment", mfa=True), ...]` one per line. |
| `app.py` | WSGI app (`wsgiref`), dispatch only through `ROUTES`; session check with MFA flag and idle timeout. |
| `session.py` | session with injected clock. |
| `npi.py` | `NPI_FIELDS = frozenset({"account_number", "routing_number", "tax_id", "date_of_birth"})`. |
| `vault.py` | stdlib authenticated encryption (HMAC-SHA256 keystream + MAC), clearly marked synthetic; `seal`/`open`. |
| `store.py` | sqlite3; every statement uses `?` parameters; NPI columns stored sealed. |
| `payments.py` | create, approve, release. Amount >= threshold: two distinct approvers, neither the creator. Release is idempotent on `instruction_id` (second release is a no-op returning the first result). |
| `integrations.py` | `INTEGRATIONS = [Integration("core-banking", "https://core.fernbrook.example/api"), ...]` one per line; every one must be https and appear in `controls/asset-inventory.json`. |
| `audit.py` | hash-chained append-only audit; retention purge. |
| `logs.py` | logger wrapper with masking; in-memory sink for tests. |
| `retention.py` | purge NPI of closed accounts older than retention unless legal hold. |
| `service.py` | operations wiring the above; each state-changing operation audited. |

Tests: `tests/test_*.py` ordinary; `tests/controls/test_*_control.py` mirroring the Java table for ACC-1, ACC-2, SOD-1, MFA-1, SES-1, ENC-1, ENC-2 (exhaustive over integrations), LOG-1 (sample), AUD-1 (sample), AUD-2, RET-1 (sample), INV-1 (exhaustive), SEC-1 (exhaustive: AST scan of every `.execute(`/`.executemany(` call site in `payments/`, first argument must be a string literal and parameters passed separately; the test also fails if it finds a call it can't classify), MC-1, PAY-1 (exhaustive amount grid with boundaries), PAY-2 (sample: release twice).

## controls/

`obligations.json` follows `engine/contract/obligation.schema.json` (written alongside). Until that exists, use: `{"id","title","statement","form","app","domain":{"name","source","closed"},"params","scope":{"paths":[...]},"evidence_required","controls":[test ids],"maps_to":[{"framework","section"}],"owner","severity"}`.

`components.json`: `{"<glob>": {"component": "mortgage.access", "security_sensitive": true}}` covering every source path. Security-sensitive: access, routes/http/app, session, vault/npi/store-encryption, audit, logs.

`protected-paths.json`: `controls/**`, `apps/baseline-mortgage/src/test/java/controls/**`, `apps/baseline-payments/tests/controls/**`, `ci/**` (paths relative to `platform/`, which becomes each variant repo root).
