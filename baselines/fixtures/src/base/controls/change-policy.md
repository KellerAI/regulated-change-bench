# Change-management standard (payments)

1. Every change to the platform repository is reviewed and accepted before merge. The approver checks the
   change against every applicable obligation in `controls/obligations.json`.
2. A change references one change ticket (`records/change.json` -> `ticket`). The ticket must be `approved` and its
   `components` must include every component the change touches. Components come from `controls/components.json`.
3. Approvals are recorded in `approvals.json` and bind to a commit. An approval counts only for the commit it names.
   The code approver must hold the `code_approver` role and must not be the author. People are identified through
   `directory.json`; an alias is the same person.
4. Changes touching a security-sensitive component also need an approved `security_review` from a
   `security_reviewer`.
5. Control evidence: an obligation whose controls are exhaustive is shown only by its exhaustive control test passing
   on the final change. Sample tests do not discharge universal obligations on their own.
6. Deviations are acceptable only under an active exception in the exception register.
