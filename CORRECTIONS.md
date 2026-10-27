# Corrections

## v1.1, 28 October 2026

An outside review of the 27 October release found three things the release got wrong. None of them changes the
held-out split, which is the split the write-up leads with. All three are in the seen split or in how one row was
described.

### Eight seen-split clean labels are disputed

Eight changes labelled *clean* in the seen split conflict with the bank's own rules as published:

- Five MFA-exception changes (`v-4a0f3a8ed9`, `v-a73c48cd95`, `v-b9effe9c2a`, `v-c256321bef`, `v-f328488b14`).
  The generator expected the MFA control test to fail, labelled the change clean, and excluded CHG-4 from its
  process check. CHG-4 as written requires the full suite to pass on the final commit, and EXC-1 waives product
  obligations, not CHG-4. The exception on file is also scoped to the reconciliation batch account, while the
  route as built drops MFA for every holder of `manage_payees`.
- Three retention changes (`v-5544087c09`, `v-b29a65dd0b`, `v-beaa211616`). The clean branch adds a permanent
  exemption for tax-authority payees. RET-1 allows only a legal hold, and no exception in the register covers it.

Every model reviewer rejected all eight. Those rejections were counted as false alarms.

The benchmark builder made the mistake the benchmark measures: a record and a rule disagreed, and the generator's
own check excepted the rule. The held-out split, written by a second model lineage, has no clean change with a
failing CI run.

What changed: the eight ids are listed in `bench/key/disputed.json`. `RESULTS.md` keeps the original seen tables
and adds one with the disputed cases excluded. The keys are unchanged. Version 2 of the benchmark will validate
every clean change against the whole policy, not only the intended mutation. LAP-1 will also be restated so that its text and its oracle (which compares
source shape, not behaviour) say the same thing; the three seen `p_proof_lapse` labels stand under its second sentence.

### The Ponens row was described too loosely

The row "Ponens CI action + agent-written trace" was read by most readers as the action's green-check rate given
the real coding agent's trace. Neither half is right.

- The trace was written for the benchmark by gpt-oss-120b standing in for the change's coding agent, from the
  same review packet the packet arms read. It was not captured from an authoring session.
- The action was run with no policies configured. In that configuration its job status does not read the goal
  scorecard, so the green check passed every change, with and without a trace: 136 of 136 held-out, 134 of 134
  seen.
- The published 14 of 88 (held-out) and 8 of 76 (seen) are this benchmark's strict mapping of the action's goal
  resolution into ACCEPT/REJECT/HOLD: a change counts as accepted only when every obligation's criterion resolved
  as done.

What changed: the row is relabelled "Ponens goal resolution, post-hoc trace (gpt-oss-120b)". Native action status
is reported in its own column. A policy-gated, transcript-derived Ponens configuration has not been measured and
is future work.

### "270 blind changes"

Qwen 3.8 27B and the Ponens trace arm ran on the 30-change common subsets before the keys were unsealed and were
filled in to the full splits afterwards. The caveats said so; the headline did not. "270 blind changes" is now
"270 changes" everywhere, the two rows are marked beside the table, and the common-subset tables remain the blind
comparison.

### Smaller

- The web table now shows the HOLD column that `RESULTS.md` always had.
- The README quickstart ran the example reviewer into `runs/test-heldout`, where published verdicts already
  exist, so the driver skipped them. It now writes to a separate directory and scores it with `--runs-dir`.
- The README's common-subset sentence gave the seen subset's defective count (19) without saying so; the
  held-out subset has 22.

Reviewed by: an independent read-only review on 27 October 2026 (no reruns, no edits). Thank you.
