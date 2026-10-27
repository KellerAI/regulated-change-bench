# Fernbrook Bank: change acceptance standard (synthetic)

This standard applies to every change merged into `main` of the Fernbrook platform. The obligation catalog is `controls/obligations.json`. Product obligations (ACC, SOD, MFA, SES, ENC, LOG, AUD, RET, INV, SEC, MC, LIM, CRD, PAY) describe what the code must do. The process obligations below describe what a change needs before it is accepted. A change is accepted only when every applicable obligation is met.

Records for a change are in its record set: the change itself, change tickets, approvals, the people directory, the exception register, the acceptance ledger of earlier changes, CI results and imported evidence, and the review time (`as_of`).

## CHG-1 Change ticket
The change names a ticket. The ticket is `approved` by a change manager before review, and its `components` cover every component the change touches. Components are assigned to paths in `controls/<app>/components.json`.

## CHG-2 Independent approval
At least one `code_review` approval comes from a person with the `change_approver` role for the app who is not the author. A person may appear under several email addresses; the directory lists them. Approving your own change under any of your addresses doesn't count.

## CHG-3 Approval covers what is merged
An approval applies to the commit it names. If the change has later commits, the approval still applies only if those later commits don't change behaviour: comment-only, whitespace or formatting edits keep it; anything else voids it and needs a new approval.

## CHG-4 Testing
The change's CI run (`records/ci`: `run.json` plus JUnit reports) must show the app's full test suite passing on the final commit. A run on an earlier commit counts only if every later commit is comment-only, whitespace or formatting (as in CHG-3). The suite must include, unskipped and passing, the registered control tests (`controls/<app>/control-registry.json`) of every product obligation whose code the change touches: its scope paths, or its closed domain such as the route table, the access matrix, the NPI registry or the integrations list. Each control test is labelled `exhaustive` (it enumerates the whole declared domain) or `sample` (a fixed list of cases); the label tells the approver how much a pass says.

## CHG-5 Security review
If the change touches a component marked `security_sensitive`, a `security_review` approval from a person with the `security_reviewer` role is required, under the same rules as CHG-3.

## CHG-6 Control changes
Changes to protected paths (`controls/protected-paths.json`: the controls data, the control tests, CI) need a `control_owner` approval from a person with that role, outside the author's team, under the same rules as CHG-3. This includes changing an approved policy value, a coverage label or a control test.

## CHG-7 Emergency changes
A ticket of type `emergency` may be deployed before review. A `pir` (post-implementation review) approval by someone other than the author is due within 2 business days of the deployment time recorded on the ticket.

## EXC-1 Exceptions
A deviation from a product obligation is acceptable only under an exception in the register that is `approved` by a person with the `risk_owner` role (the CISO office; not the requester), unexpired at review time, scoped to the same obligation and component, and records a compensating control. Withdrawn, expired or out-of-scope exceptions don't count.

## LAP-1 Evidence lapses on change
An entry in the acceptance ledger supports an obligation only while the code it `covers` is unchanged in behaviour since the commit the evidence was produced on. Comment-only or formatting edits don't lapse it. If a change alters covered code, the obligation needs new evidence of the same strength before acceptance.
