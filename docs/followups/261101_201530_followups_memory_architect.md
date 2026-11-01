# Follow-ups backlog — 261101_201530_followups_memory_architect

**Date:** N/A (why=serial V2 writer stores row authority, not a second timestamp truth)
**Source:** external-only follow-ups authority V2
**Status:** Draft
**Schema version:** followups.v2

## Follow-ups (backlog)

- P2 [ ] Явно обозначить planned observer counts в неполной диагностике s11 — cluster=quality — tags=ci,diagnostics,tests — to=architect — status=open — plan=null — item_id=p2-s11-observer-count-labels — source_ref=docs/plans/261101_1252_ci_runtime_timing_diagnostics.md — disposition_kind=null — disposition_ref=null — disposition_commit_oid=null — reason=null — why: Источник: docs/code_reviews/261101_1252_ci_runtime_timing_diagnostics.md#S2-Risk, risk:R1; Architect принял de-scoped follow-up в terminal plan. Scope: только labels трех spec-based counters в scripts/test_planveyor_init_capture.py. DoD: 1) timestamp_writer_process_count, added_boundary_writer_process_count и added_boundary_timestamp_file_write_count явно обозначены planned/expected; 2) incomplete observations не выдаются за actual count, отсутствие sidecar не доказывает отсутствие процесса; 3) retained original failure, UNKNOWN, business assertions и bounds подтверждены bounded regression без cause/runtime fix или вычитания observer cost.
