# Код-ревью — наблюдение времени CI в s02 и s11

**Date:** 01.11.2026 19:23 +0300
**Target:** BUNDLE=current bundle_sha256=4c534ea3e2de0ddb4e3f70ea19a6934c264b5ce88dc637ca3a15851a30630815
**Spec:** docs/plans/261101_1252_ci_runtime_timing_diagnostics.md
**Status:** ✅ OK

Замечания: S1 не обнаружены; одна S2 `risk:R1` — planned observer counts при неполном s11 запуске выглядят фактическими. Contracts новых findings не добавляет. Обещанный phase report materialized; обе code lanes завершены, downstream closeout и публикация этим verdict не закрываются.

## reviewer_code_risk
- Lane status: complete
- Target snapshot: BUNDLE=current bundle_sha256=4c534ea3e2de0ddb4e3f70ea19a6934c264b5ce88dc637ca3a15851a30630815
- run_id: reviewer_code_risk_20261101T160418Z
- runner_id: codex-native-collab
- session_key: /root/reviewer_code_risk_sol_xhigh_v2
- thread_id: 01a19403-8df0-7ba1-9bfb-1f7cee20a97c
- sid: unknown
- profile: unknown
- model: unknown
- reasoning_effort: unknown
- prompt_file: docs/tools/prompts/reviewer_status_driven.md
- Coverage domains: correctness, tests quality, security/privacy, subprocess/timeouts, races/locks/atomicity, performance, observability, integrations, failure semantics
- Findings: `risk:R1 severity=S2 domain=observability` — неполный запуск выдаёт planned observer counts за фактические; подробности в `## S2 Risk`.
- No findings reason: N/A (why=одна S2 risk:R1; S1 не найдено).
- Support: `docs/code_reviews/assets/261101_1252_ci_runtime_timing_diagnostics/reviewer_code_risk_20261101T160418Z.json`.
- Support SHA-256: `750124645053d3b889412939658fe6b24d4303bd7c49c9dbc279fa5d53ea0273`.
- Source refs: `scripts/test_contract_authority_shell.py:636`, `scripts/test_contract_authority_shell.py:1243`, `scripts/test_planveyor_init_capture.py:292`, `scripts/test_planveyor_init_capture.py:3812`, `scripts/test_planveyor_init_capture.py:3891`.
- Outcome / limits: source-bound Coder executions независимо перечитаны Risk; свежие controlled/partition checks и incomplete diagnostic probe не заявлены behavioral rerun, physical timeout или hosted proof. Immutable support самостоятельно открыт Contracts finalizer-ом.

## reviewer_code_contracts
- Lane status: complete
- Target snapshot: BUNDLE=current bundle_sha256=4c534ea3e2de0ddb4e3f70ea19a6934c264b5ce88dc637ca3a15851a30630815
- run_id: reviewer_code_contracts_20261101T161648Z
- runner_id: codex-native-collab
- session_key: /root/reviewer_code_contracts_sol_xhigh_v2
- thread_id: 01a19404-e037-78b0-ba01-bc4b39c5a18f
- sid: unknown
- profile: unknown
- model: unknown
- reasoning_effort: unknown
- prompt_file: docs/tools/prompts/reviewer_status_driven.md
- Coverage domains: plan fidelity, architecture/design fit, maintainability, canon/materialization/build drift, API/schema, documentation/registry, integration semantics, config/deploy/rollout, review artifact truthfulness, LLM/prompt/meta-review
- Uses plan lane-run artifact: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md::Evidence`, helper-selected run `reviewer_code_risk_20261101T160418Z`; независимые selector readbacks до diff и непосредственно перед materialization дали `state=selected`, actual rc=0.
- Finalizer proof: полный frozen prompt, current plan/draft, target-local AGENTS/playbook, exact two-target diff, helper-selected compact carrier и полный immutable support прочитаны самостоятельно. Fresh public snapshot совпал с nested support byte identities и compact target; source/support не менялись. Прочитаны все шесть исходных Coder logs, `results.tsv`, обе provenance/observations, before/after inventory и Risk incomplete probe; фактические records из raw logs точно совпали с handoff-observations.
- Reused evidence: шесть Coder method executions на тех же source hashes и runtime/manifest pins; новое исполнение этих длительных methods не заявляется. Actual rc=0/Ran 1/OK/zero skips/errors/failures/expected failures/unexpected successes проверены отдельно от авторского summary. Fresh Contracts controlled rc0/rc2/nonterminal timeout parity и partition `--check` обеих axes прошли rc=0; partition не исполнял suite.
- Findings: новых Contracts findings нет; `risk:R1` независимо подтверждён исходным `len(writers)`/spec-based expression и прочитанным exact-source incomplete probe, сохранён как S2.
- No findings reason: AC1–AC6 соответствуют двум текущим test blobs; AC7 materialized ниже с raw intervals, source-state и границами измерения. Immutable Risk support является lifecycle evidence, не новым implementation target. Runtime/API/schema/defaults/config/manifest/workflow/authority не меняются; все прежние assertion/fail/subTest AST и 38/58 method IDs сохранены.
- Source refs: `docs/code_drafts/261101_1252_ci_runtime_timing_diagnostics__code_draft.md`, `docs/playbooks/review_staged_or_commit.md`, `docs/adr/003-single-live-review-route.md`, `docs/adr/004-exact-bundle-truth-and-closeout.md`, `docs/adr/006-doc-lint-scoped-closeout-gate.md`, `docs/tools/verify_suite.md`, два implementation targets выше.
- Delta / outcome: наружные test timings и раздельные raw/boundary/writer-body observations добавлены без cause fix; обе mandatory negative s11 ветки и `126:0` сохранены. AC8, standalone indexed scanner, semantic commit и Manager terminal family остаются downstream-owned.
- Limits: local provider-free fixtures; Python 3.10 — compatibility axis, 3.12 — native axis. Нет hosted/full-suite/cause/publication acceptance. Model/profile/effort/SID не раскрыты окружением; suffix handle не использован как доказательство модели.

## Lane synthesis / aggregate verdict
- Source lanes: reviewer_code_risk, reviewer_code_contracts
- Canonical mapping: `risk:R1 -> accepted_risk` (S2, owner=Architect для disposition); новых canonical B IDs нет.
- Finding: risk:R1
  - source_lane: reviewer_code_risk
  - lane_finding_id: risk:R1
  - synthesis_disposition: accepted_risk
  - canonical_ref: docs/code_reviews/261101_1252_ci_runtime_timing_diagnostics.md#S2-Risk
  - audit_status: pending_post_merge_audit
  - followup_plan: N/A
- Aggregate status: ✅ OK
- Обоснование disposition: issue ограничен интерпретацией counters у incomplete diagnostics; original exception/non-green и missing observations остаются видимыми. Все текущие primary logs полны. Отчёт ниже явно называет эти значения planned/spec counts; новые execution/cause/publication решения не выведены из них. Architect решает дальнейшую bounded работу.

## S1 Blocker
Нет.

## S2 Risk
### R1) Planned counts выглядят фактическими при неполном s11 запуске
- Источник: `risk:R1`; owner=Architect, blocker=no.
- `scripts/test_planveyor_init_capture.py:3891`–3893 вычисляет `timestamp_writer_process_count`, `added_boundary_writer_process_count` и `added_boundary_timestamp_file_write_count` по всему `writers`/spec set. В обоих `finally` paths (`:3960`, `:4116`) этот set передаётся и при исключении до запуска части writers.
- Impact: incomplete timing report приписывает запланированным операциям числовой вид выполненных. Прочитанный exact-source probe с timeout-shaped failure, без subprocess и доступных sidecars, дал counts 4/2/2, четыре missing observations, `original_failure` и `UNKNOWN` для интервалов. Исходный отказ не замаскирован; это не false pass и не physical timeout proof.
- Рекомендация: назвать три поля planned/expected; actual counts публиковать только при достаточном наблюдении, иначе `UNKNOWN`. Отсутствие sidecar само по себе не доказывает отсутствие процесса.
- Evidence: immutable support выше; `.tmp/ci_p2_proof/reviewer-risk-001/incomplete-observer-count-probe.json`, SHA-256 `c8d709ddae9ef54afded4434383ed99ab2523ab69e297da607be93b8aceabca1`.
- Disposition: accepted_risk для текущего bounded review; дальнейший fix/follow-up выбирает Architect. Здесь implementation не изменялся.

## S3 Nit
Нет.

## Контекст и границы доказательства
Review content target — current explicit bundle относительно WORK HEAD `11ace6c3b3338740ea13dc9f9ef91080651e9c7f`. Canonical scope helper вернул шесть exact paths: два test targets, origin plan, code draft, этот единственный review и объявленный immutable Risk support. Source diff: 285 insertions / 69 deletions, только два targets. Index пуст; out-of-scope implementation delta не обнаружена. `Mode: reuse-thread`; semantic observation marker отсутствует, поэтому новый observation/outcome receipt не создаётся.

Fresh native prerequisite Contracts выполнен в объявленном process-local envelope с outer `login:false`, явно supplied PYBIN до login shell и bare `python3` внутри. Python 3.12.14, samefile=true, physical TMPDIR outside Git, actual rc=0. Все 11 Operator decision hashes проверены; исходный failed Planner probe и append-only Q1 history сохранены. Это launch prerequisite, не behavioral/hosted proof. Содержимое private dictionary не открывалось.

Raw logs остаются transient evidence; следующий report содержит durable observations, portable identities и явные `<REDACTED>`. Никакой inherited П1 gate exception: scope link/basic-hygiene route взят из текущих П2 Decisions/Commands и ADR 006. Known canonical five-link debt/rc=1 остаётся внешним долгом.

## Phase report — локальные наблюдения
### Source и runtime provenance

Эти execution observations привязаны к `git_head=11ace6c3b3338740ea13dc9f9ef91080651e9c7f`, `source_state=dirty`. HEAD — база; он **не** обозначает новые test bytes. Source snapshot перед executions captured UTC `2026-11-01T12:28:46.850855+00:00`; итоговый Coder evidence readback captured UTC `2026-11-01T14:07:15.052762+00:00`. Последующий Contracts readback подтвердил те же hashes; эти шесть methods Contracts повторно не запускал.

| Carrier | Actual SHA-256 | Binding |
| --- | --- | --- |
| `scripts/test_contract_authority_shell.py` | `6ecc69ba0dd5f3dc87acfc762ca19bf1fd6b21c06e2f67489976963a7aa31465` | dirty source, 207082 bytes |
| `scripts/test_planveyor_init_capture.py` | `02841e0b128d7f06bf9e24fd04ecc33a504dba36d3860045133d7940de681010` | dirty source, 321615 bytes |
| `scripts/test_shards.json` | `bb18fa43385c3d9bcb97eb3ada28302030e09e4ff37848519cc0d869d942c260` | unchanged manifest |
| `.github/workflows/checks.yml` | `edb9c56bb01e8a1038b8f6010bb1199e8e47e534e34b71f93afd59ad4a7eee6c` | unchanged workflow, 105 min budgets |

Frozen external runtime: `e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4`, clean. Fixture identity/runtime assertions остаются прежними; public-command fixture test использует своё существующее attested source/runtime setup. Frozen facade pin не подменяет эти fixture checks.

| Axis | Actual Python identity | Executable SHA-256 | Surface / OS / arch / runner / image |
| --- | --- | --- | --- |
| `3.10` | `3.10.22`, conda-forge, build `Oct 6 2026 22:55:54`, `Clang 19.1.7` | `cc0939d53d6d23b36e6d02b39a43808569758bb575af507b9efa6bb4f84251ee` | local / Darwin 27.2.0 / arm64 / UNKNOWN / UNKNOWN |
| `3.12` | `3.12.14`, build `Sep 3 2026 03:46:19`, `Clang 21.1.8` | `9e78d18ffca959d9f44a7c363360a4b24f108e3eab576bd525c42031612a1505` | local / Darwin 27.2.0 / arm64 / UNKNOWN / UNKNOWN |

Executable identities из actual provenance совпали с fresh readback выбранных interpreters. Private absolute executable = `<REDACTED>`; hosted runner/image здесь не измерялись. Разница чисел между последовательными local axes не является доказательством влияния версии Python.

### Идентичность локальных исполнений

Короткие IDs далее однозначно раскрываются здесь. У каждой строки методов тот же dirty source/manifest/frozen-runtime binding из предыдущей секции. Команда каждого исполнения: `env -u PLANVEYOR_ROOT PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1 "$p2_python" -B -m unittest -v <literal ID>`.

| ID | Literal unittest ID |
| --- | --- |
| `s02` | `test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_candidate_format_correction_all_roles_and_bounded_outcomes` |
| `s11` | `test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe` |
| `s02-negative` | `test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture` |

UTC ниже — наблюдаемый `mtime` завершённого log artifact из Coder readback, а не timestamp отдельной child phase; UTC начала каждого command = `UNKNOWN`. `unittest` summary seconds сохранены как напечатаны runner-ом, с его исходным округлением; это не raw monotonic samples. Обе axes исполнялись последовательно, не как controlled benchmark.

| Axis | ID | UTC log observation | actual rc | Ran | skips/errors/failures/expected failures/unexpected successes | unittest seconds | Log SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `3.10` | `s02` | `2026-11-01T13:12:55.426337+00:00` | `0` | `1` | `0/0/0/0/0` | `2648.172` | `0996297992458ce795378e8e3e1f2c15c152bad23cf0d574d70dae47fac3f3e5` |
| `3.10` | `s11` | `2026-11-01T13:13:45.875724+00:00` | `0` | `1` | `0/0/0/0/0` | `50.340` | `bb6a38aa096ad8712d693d5d83f3970f20a2cd5cac69ad1701288b20f7891e13` |
| `3.10` | `s02-negative` | `2026-11-01T13:13:55.938685+00:00` | `0` | `1` | `0/0/0/0/0` | `9.951` | `bcdb6b5ef842d6a28339d8b824fc098a3d1bd16da9f63965b604b9d2869c7690` |
| `3.12` | `s02` | `2026-11-01T14:05:34.612333+00:00` | `0` | `1` | `0/0/0/0/0` | `3096.852` | `d724ba34274b0926f60b44655a45265c8aa00eead81e22403b116bc4784930f8` |
| `3.12` | `s11` | `2026-11-01T14:06:27.467785+00:00` | `0` | `1` | `0/0/0/0/0` | `52.749` | `e3ff55783acae8094c89c782ea927549ef19cac2427a4534ea68c6382d4b0faf` |
| `3.12` | `s02-negative` | `2026-11-01T14:06:38.542587+00:00` | `0` | `1` | `0/0/0/0/0` | `10.946` | `3b98c438835b5082c125c1ec2351a6e21bbffe4cea5e32b20b664cd0ef3849de` |

Literal log locators:

- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.10-test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_candidate_format_correction_all_roles_and_bounded_outcomes.log`
- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.10-test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe.log`
- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.10-test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture.log`
- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.12-test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_candidate_format_correction_all_roles_and_bounded_outcomes.log`
- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.12-test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe.log`
- `.tmp/ci_p2_proof/coder-20261101T120648Z/3.12-test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture.log`

### s02: raw наружные интервалы всех команд

Для каждой строки: `clock=time.monotonic`, `units=seconds`; `elapsed=end-start` без дополнительного округления. Таблица содержит все 115 primary terminal rows и одну negative row на каждой axis, в исходном порядке. Измеряется наружный вызов helper, включая подготовку argument/environment expression и `subprocess.run`; child internal phases не измерены. `actual_rc=2` в отрицательных сценариях является фактическим ожидаемым отказом команды; общий unittest при этом rc=0.

Колонка `argv` — точная ссылка в следующий исчерпывающий каталог sanitized argument vectors. Private absolute components и transient cycle/reservation UUID заменены на `<REDACTED>`; аргументы, порядок, flags и command-role сохранены. Raw argv и точная fixture/cycle identity доступны только в hash-bound transient logs. Outer `role` не подменяет отдельный `--role` из argv; разные prefix collectors остаются видимыми в каталоге.

| argv | Sanitized argument vector |
| --- | --- |
| `A01` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_docs_closeout","<REDACTED>","--json"]` |
| `A02` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","begin","--plan-ref","<REDACTED>","--docs-closeout-json","-"]` |
| `A03` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Architect","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json"]` |
| `A04` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_docs_closeout","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--json"]` |
| `A05` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","sibling","close","--cycle","<REDACTED>"]` |
| `A06` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","sibling","close","--cycle","<REDACTED>","--commit"]` |
| `A07` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","reserve-general-pi-correction","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Architect","--docs-closeout-json","-"]` |
| `A08` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Architect","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json","--format-correction-reservation-id","<REDACTED>"]` |
| `A09` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Coder","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json"]` |
| `A10` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","reserve-general-pi-correction","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Coder","--docs-closeout-json","-"]` |
| `A11` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Coder","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json","--format-correction-reservation-id","<REDACTED>"]` |
| `A12` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Planner","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json"]` |
| `A13` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","reserve-general-pi-correction","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Planner","--docs-closeout-json","-"]` |
| `A14` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Planner","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json","--format-correction-reservation-id","<REDACTED>"]` |
| `A15` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Reviewer","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json"]` |
| `A16` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","reserve-general-pi-correction","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Reviewer","--docs-closeout-json","-"]` |
| `A17` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Reviewer","--source-ref","<REDACTED>","--followups-capture-cycle-id","<REDACTED>","--input","-","--json","--format-correction-reservation-id","<REDACTED>"]` |
| `A18` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","checkpoint-general-pi","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>"]` |
| `A19` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","prepare-role","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Architect"]` |
| `A20` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","submit-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Architect","--input","-","--write"]` |
| `A21` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","bind-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Architect","--submission-current","--write"]` |
| `A22` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","prepare-role","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Coder"]` |
| `A23` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","submit-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Coder","--input","-","--write"]` |
| `A24` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","bind-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Coder","--submission-current","--write"]` |
| `A25` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","prepare-role","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Planner"]` |
| `A26` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","submit-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Planner","--input","-","--write"]` |
| `A27` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","bind-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Planner","--submission-current","--write"]` |
| `A28` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","prepare-role","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Reviewer"]` |
| `A29` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","submit-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Reviewer","--input","-","--write"]` |
| `A30` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","bind-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--role","Reviewer","--submission-current","--write"]` |
| `A31` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_followups_capture","freeze-ordinary-v2","--plan-ref","<REDACTED>","--capture-cycle-id","<REDACTED>","--write"]` |
| `A32` | `["<REDACTED>/bin/planveyor","--project","<REDACTED>","planveyor_runtime_py","process_improvements_collect.py","--role","Architect","--source-ref","<REDACTED>","--input","-","--json"]` |

#### s02 / Python 3.10

| ID | № | Outer role | Subcase | Label | argv | Raw start | Raw end | Raw elapsed | actual rc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `s02` | `1` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `223223.716391041` | `223239.540723791` | `15.824332749994937` | `0` |
| `s02` | `2` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `223239.540998041` | `223247.920223708` | `8.379225667013088` | `0` |
| `s02` | `3` | `Architect` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `223247.920371875` | `223257.03180175` | `9.111429875018075` | `2` |
| `s02` | `4` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `223257.042606666` | `223274.853616708` | `17.811010042001726` | `0` |
| `s02` | `5` | `Architect` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `223274.86484375` | `223328.687441916` | `53.82259816600708` | `0` |
| `s02` | `6` | `Architect` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `223328.687586583` | `223383.94289325` | `55.25530666700797` | `0` |
| `s02` | `7` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A07` | `223383.943171541` | `223417.481378375` | `33.53820683399681` | `0` |
| `s02` | `8` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A07` | `223417.481779375` | `223438.05614825` | `20.574368875008076` | `2` |
| `s02` | `9` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `223438.056335791` | `223456.188957791` | `18.132621999975527` | `0` |
| `s02` | `10` | `Architect` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A08` | `223456.18925275` | `223492.419458458` | `36.230205708008725` | `0` |
| `s02` | `11` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `223492.497712125` | `223508.209522291` | `15.711810165987117` | `0` |
| `s02` | `12` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `223508.20983725` | `223516.648926416` | `8.439089166000485` | `0` |
| `s02` | `13` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `223516.649057` | `223525.924349458` | `9.275292457983596` | `2` |
| `s02` | `14` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `223525.924622958` | `223544.301700625` | `18.377077666984405` | `0` |
| `s02` | `15` | `Architect` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `223544.312542875` | `223598.528214` | `54.21567112498451` | `0` |
| `s02` | `16` | `Architect` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `223598.528347583` | `223653.156349083` | `54.628001500008395` | `0` |
| `s02` | `17` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A07` | `223653.156624333` | `223685.886536916` | `32.72991258298862` | `0` |
| `s02` | `18` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A07` | `223685.88693625` | `223706.581571291` | `20.694635040999856` | `2` |
| `s02` | `19` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `223706.581803583` | `223725.047127208` | `18.465323625016026` | `0` |
| `s02` | `20` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A08` | `223725.047391583` | `223758.142984333` | `33.09559275000356` | `2` |
| `s02` | `21` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A08` | `223758.167265625` | `223778.086393458` | `19.91912783301086` | `2` |
| `s02` | `22` | `Architect` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `223778.086608166` | `223832.759582208` | `54.672974042012356` | `0` |
| `s02` | `23` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `223832.828446333` | `223848.606544125` | `15.7780977920047` | `0` |
| `s02` | `24` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `223848.606822541` | `223856.687701916` | `8.080879374989308` | `0` |
| `s02` | `25` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `223856.687879333` | `223868.4719815` | `11.784102167002857` | `0` |
| `s02` | `26` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `223868.472155041` | `223877.296699541` | `8.824544500006596` | `2` |
| `s02` | `27` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `223877.296987916` | `223895.327439916` | `18.030452000006335` | `0` |
| `s02` | `28` | `Coder` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `223895.338160625` | `223949.097043458` | `53.75888283300446` | `0` |
| `s02` | `29` | `Coder` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `223949.097231875` | `224002.96425625` | `53.86702437500935` | `0` |
| `s02` | `30` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A10` | `224002.964500583` | `224034.550073375` | `31.585572791984305` | `0` |
| `s02` | `31` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A10` | `224034.550399875` | `224054.055714791` | `19.50531491599395` | `2` |
| `s02` | `32` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224054.055914708` | `224071.90727175` | `17.851357042003656` | `0` |
| `s02` | `33` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A11` | `224071.907533708` | `224104.453063083` | `32.545529374998296` | `0` |
| `s02` | `34` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `224104.532496416` | `224120.193867208` | `15.661370791989611` | `0` |
| `s02` | `35` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `224120.194159458` | `224128.259817833` | `8.065658374980558` | `0` |
| `s02` | `36` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `224128.260014666` | `224139.977683416` | `11.71766874997411` | `0` |
| `s02` | `37` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `224139.977897833` | `224148.879182666` | `8.901284832973033` | `2` |
| `s02` | `38` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224148.879496958` | `224166.798537` | `17.91904004200478` | `0` |
| `s02` | `39` | `Coder` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `224166.810205333` | `224220.594577916` | `53.78437258300255` | `0` |
| `s02` | `40` | `Coder` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `224220.594711083` | `224274.1426795` | `53.54796841699863` | `0` |
| `s02` | `41` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A10` | `224274.14295475` | `224305.693331916` | `31.550377166015096` | `0` |
| `s02` | `42` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A10` | `224305.693675333` | `224325.124708916` | `19.431033583008684` | `2` |
| `s02` | `43` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224325.124887375` | `224343.008439958` | `17.88355258302181` | `0` |
| `s02` | `44` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A11` | `224343.008741291` | `224375.517586625` | `32.50884533399949` | `2` |
| `s02` | `45` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A11` | `224375.528562041` | `224395.095758791` | `19.567196749994764` | `2` |
| `s02` | `46` | `Coder` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `224395.095956208` | `224448.543076916` | `53.447120707976865` | `0` |
| `s02` | `47` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `224448.613627` | `224464.216763166` | `15.603136165998876` | `0` |
| `s02` | `48` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `224464.217056625` | `224472.291291875` | `8.074235250009224` | `0` |
| `s02` | `49` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `224472.291455416` | `224483.805048666` | `11.513593249983387` | `0` |
| `s02` | `50` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `224483.80521875` | `224492.502532166` | `8.69731341599254` | `0` |
| `s02` | `51` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A12` | `224492.502681875` | `224501.18084425` | `8.678162374999374` | `2` |
| `s02` | `52` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224501.181141416` | `224519.030674666` | `17.849533250002423` | `0` |
| `s02` | `53` | `Planner` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `224519.041245333` | `224571.973810416` | `52.932565082999645` | `0` |
| `s02` | `54` | `Planner` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `224571.97394475` | `224625.277771958` | `53.30382720800117` | `0` |
| `s02` | `55` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A13` | `224625.278081875` | `224656.513328833` | `31.235246958007338` | `0` |
| `s02` | `56` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A13` | `224656.513693916` | `224676.006037666` | `19.492343749996508` | `2` |
| `s02` | `57` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224676.006210875` | `224693.816021583` | `17.809810708014993` | `0` |
| `s02` | `58` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A14` | `224693.816319083` | `224726.396163` | `32.579843916988466` | `0` |
| `s02` | `59` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `224726.488308` | `224742.008150583` | `15.519842582987621` | `0` |
| `s02` | `60` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `224742.008510416` | `224749.990616291` | `7.982105875009438` | `0` |
| `s02` | `61` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `224749.990818166` | `224761.73098425` | `11.740166083996883` | `0` |
| `s02` | `62` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `224761.731145875` | `224770.430692541` | `8.69954666600097` | `0` |
| `s02` | `63` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A12` | `224770.430836041` | `224779.118006125` | `8.687170084012905` | `2` |
| `s02` | `64` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224779.118272` | `224796.576251291` | `17.457979291008087` | `0` |
| `s02` | `65` | `Planner` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `224796.586828125` | `224850.061958791` | `53.47513066598913` | `0` |
| `s02` | `66` | `Planner` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `224850.062092416` | `224903.417333583` | `53.35524116700981` | `0` |
| `s02` | `67` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A13` | `224903.417593291` | `224934.725395041` | `31.307801749993814` | `0` |
| `s02` | `68` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A13` | `224934.725745833` | `224954.147919083` | `19.422173250000924` | `2` |
| `s02` | `69` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `224954.148131083` | `224971.790688583` | `17.64255749998847` | `0` |
| `s02` | `70` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A14` | `224971.790939291` | `225004.234109666` | `32.44317037498695` | `2` |
| `s02` | `71` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A14` | `225004.245226541` | `225023.931626291` | `19.686399750004057` | `2` |
| `s02` | `72` | `Planner` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `225023.931829875` | `225077.426328375` | `53.49449850001838` | `0` |
| `s02` | `73` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `225077.496480041` | `225093.622892125` | `16.126412083976902` | `0` |
| `s02` | `74` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `225093.62323925` | `225101.729957` | `8.10671774999355` | `0` |
| `s02` | `75` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `225101.730151708` | `225111.058444833` | `9.328293124999618` | `0` |
| `s02` | `76` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `225111.058588041` | `225119.771717166` | `8.71312912501162` | `0` |
| `s02` | `77` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A12` | `225119.771893` | `225128.410887416` | `8.638994415989146` | `0` |
| `s02` | `78` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A15` | `225128.411040375` | `225137.113483666` | `8.702443290996598` | `2` |
| `s02` | `79` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225137.113755708` | `225154.933149125` | `17.819393416983075` | `0` |
| `s02` | `80` | `Reviewer` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `225154.9452385` | `225208.55823175` | `53.61299325001892` | `0` |
| `s02` | `81` | `Reviewer` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `225208.558399833` | `225263.585582125` | `55.02718229198945` | `0` |
| `s02` | `82` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A16` | `225263.585834375` | `225295.04462475` | `31.458790375007084` | `0` |
| `s02` | `83` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A16` | `225295.044976333` | `225314.611750916` | `19.56677458298509` | `2` |
| `s02` | `84` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225314.611940125` | `225333.145622083` | `18.53368195798248` | `0` |
| `s02` | `85` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A17` | `225333.145956041` | `225366.486762916` | `33.340806874999544` | `0` |
| `s02` | `86` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A18` | `225366.510012833` | `225374.493498875` | `7.983486042008735` | `0` |
| `s02` | `87` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A19` | `225374.493631291` | `225382.557970708` | `8.064339417003794` | `0` |
| `s02` | `88` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A20` | `225382.558149291` | `225391.058808833` | `8.500659542012727` | `0` |
| `s02` | `89` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A21` | `225391.058977375` | `225399.47070425` | `8.41172687499784` | `0` |
| `s02` | `90` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A22` | `225399.470872541` | `225407.580920708` | `8.110048167000059` | `0` |
| `s02` | `91` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A23` | `225407.58107` | `225415.612320458` | `8.03125045800698` | `0` |
| `s02` | `92` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A24` | `225415.612464083` | `225423.856415583` | `8.243951499985997` | `0` |
| `s02` | `93` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A25` | `225423.856574208` | `225431.995834333` | `8.139260124997236` | `0` |
| `s02` | `94` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A26` | `225431.995985666` | `225440.026929208` | `8.030943541991292` | `0` |
| `s02` | `95` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A27` | `225440.027082125` | `225448.077658` | `8.05057587500778` | `0` |
| `s02` | `96` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A28` | `225448.077807291` | `225456.14112625` | `8.063318959000753` | `0` |
| `s02` | `97` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A29` | `225456.141394541` | `225464.194734708` | `8.053340167010901` | `0` |
| `s02` | `98` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A30` | `225464.19487025` | `225472.207448208` | `8.012577957997564` | `0` |
| `s02` | `99` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A31` | `225472.207595958` | `225480.420021458` | `8.212425500008976` | `0` |
| `s02` | `100` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225480.420159208` | `225497.17772975` | `16.75757054198766` | `0` |
| `s02` | `101` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `225497.252038708` | `225513.012808625` | `15.760769917018479` | `0` |
| `s02` | `102` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `225513.013128125` | `225521.104667791` | `8.091539665998425` | `0` |
| `s02` | `103` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `225521.104877833` | `225530.308214875` | `9.20333704201039` | `0` |
| `s02` | `104` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `225530.308354333` | `225539.062420416` | `8.754066082998179` | `0` |
| `s02` | `105` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A12` | `225539.062589541` | `225547.769514` | `8.706924459023867` | `0` |
| `s02` | `106` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A15` | `225547.769678791` | `225556.469509166` | `8.699830375000602` | `2` |
| `s02` | `107` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225556.469776416` | `225574.4587585` | `17.98898208400351` | `0` |
| `s02` | `108` | `Reviewer` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `225574.4806075` | `225627.853885958` | `53.373278457991546` | `0` |
| `s02` | `109` | `Reviewer` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `225627.854013833` | `225682.452309791` | `54.5982959579851` | `0` |
| `s02` | `110` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A16` | `225682.45259875` | `225714.8025345` | `32.34993574998225` | `0` |
| `s02` | `111` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A16` | `225714.802874958` | `225734.55055475` | `19.747679791995324` | `2` |
| `s02` | `112` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225734.550735416` | `225752.238319708` | `17.687584291998064` | `0` |
| `s02` | `113` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A17` | `225752.238569208` | `225784.731487333` | `32.492918124975404` | `2` |
| `s02` | `114` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A17` | `225784.742384` | `225804.354739791` | `19.612355790974107` | `2` |
| `s02` | `115` | `Reviewer` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `225804.354947458` | `225857.862956541` | `53.50800908301608` | `0` |
| `s02-negative` | `1` | `Architect` | `collector-Architect` | `collector-Architect` | `A32` | `225909.416259541` | `225918.559170666` | `9.142911125003593` | `2` |

#### s02 / Python 3.12

| ID | № | Outer role | Subcase | Label | argv | Raw start | Raw end | Raw elapsed | actual rc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `s02` | `1` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `225933.328918083` | `225950.19250025` | `16.86358216701774` | `0` |
| `s02` | `2` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `225950.192809583` | `225958.811104166` | `8.618294582993258` | `0` |
| `s02` | `3` | `Architect` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `225958.811286916` | `225968.382135916` | `9.57084900001064` | `2` |
| `s02` | `4` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `225968.395724958` | `225987.306917833` | `18.911192874977132` | `0` |
| `s02` | `5` | `Architect` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `225987.318033375` | `226044.769939416` | `57.45190604100935` | `0` |
| `s02` | `6` | `Architect` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `226044.770125458` | `226102.668887125` | `57.89876166702015` | `0` |
| `s02` | `7` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A07` | `226102.669122041` | `226136.614073125` | `33.94495108400588` | `0` |
| `s02` | `8` | `Architect` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A07` | `226136.61438125` | `226158.567899041` | `21.953517791000195` | `2` |
| `s02` | `9` | `Architect` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `226158.568136041` | `226178.491994916` | `19.923858875001315` | `0` |
| `s02` | `10` | `Architect` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A08` | `226178.49232775` | `226219.394251375` | `40.90192362500238` | `0` |
| `s02` | `11` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `226219.476062041` | `226237.245408958` | `17.76934691698989` | `0` |
| `s02` | `12` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `226237.245761125` | `226247.225813416` | `9.980052291008178` | `0` |
| `s02` | `13` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `226247.226029333` | `226258.1382605` | `10.912231167021673` | `2` |
| `s02` | `14` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `226258.138591958` | `226279.147928083` | `21.009336124989204` | `0` |
| `s02` | `15` | `Architect` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `226279.160057333` | `226340.866435458` | `61.70637812500354` | `0` |
| `s02` | `16` | `Architect` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `226340.8666015` | `226403.526540041` | `62.65993854100816` | `0` |
| `s02` | `17` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A07` | `226403.526792458` | `226441.345910291` | `37.81911783301621` | `0` |
| `s02` | `18` | `Architect` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A07` | `226441.346267875` | `226464.776392` | `23.43012412500684` | `2` |
| `s02` | `19` | `Architect` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `226464.77662275` | `226487.48493975` | `22.708316999982344` | `0` |
| `s02` | `20` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A08` | `226487.485240458` | `226526.503898166` | `39.01865770801669` | `2` |
| `s02` | `21` | `Architect` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A08` | `226526.517602666` | `226560.369260708` | `33.851658041996416` | `2` |
| `s02` | `22` | `Architect` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `226560.36970725` | `226625.085523083` | `64.71581583298394` | `0` |
| `s02` | `23` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `226625.214147166` | `226648.456019916` | `23.241872749989852` | `0` |
| `s02` | `24` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `226648.456562875` | `226659.056779041` | `10.600216165999882` | `0` |
| `s02` | `25` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `226659.0570135` | `226674.682189791` | `15.625176291010575` | `0` |
| `s02` | `26` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `226674.682399208` | `226686.011904208` | `11.329505000001518` | `2` |
| `s02` | `27` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `226686.012202083` | `226708.909545208` | `22.897343125019688` | `0` |
| `s02` | `28` | `Coder` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `226708.922784041` | `226775.611354125` | `66.68857008399209` | `0` |
| `s02` | `29` | `Coder` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `226775.611626333` | `226845.342664916` | `69.73103858300601` | `0` |
| `s02` | `30` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A10` | `226845.34300475` | `226884.121667625` | `38.77866287500365` | `0` |
| `s02` | `31` | `Coder` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A10` | `226884.122026583` | `226907.760421791` | `23.63839520799229` | `2` |
| `s02` | `32` | `Coder` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `226907.760719541` | `226930.091575041` | `22.33085550001124` | `0` |
| `s02` | `33` | `Coder` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A11` | `226930.091923` | `226970.041774041` | `39.949851040990325` | `0` |
| `s02` | `34` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `226970.13770125` | `226991.603425125` | `21.465723875007825` | `0` |
| `s02` | `35` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `226991.60385275` | `227002.652184375` | `11.048331625002902` | `0` |
| `s02` | `36` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `227002.652499708` | `227017.788980291` | `15.136480582994409` | `0` |
| `s02` | `37` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `227017.789206333` | `227029.383648416` | `11.59444208300556` | `2` |
| `s02` | `38` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `227029.384013208` | `227050.385183583` | `21.00117037500604` | `0` |
| `s02` | `39` | `Coder` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `227050.403147` | `227116.23347025` | `65.83032325000386` | `0` |
| `s02` | `40` | `Coder` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `227116.233660291` | `227182.594612958` | `66.36095266698976` | `0` |
| `s02` | `41` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A10` | `227182.594915` | `227225.845413916` | `43.250498915993376` | `0` |
| `s02` | `42` | `Coder` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A10` | `227225.845809625` | `227251.899084041` | `26.053274416015483` | `2` |
| `s02` | `43` | `Coder` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `227251.899331875` | `227274.783287916` | `22.883956041012425` | `0` |
| `s02` | `44` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A11` | `227274.784561958` | `227313.379369833` | `38.594807875022525` | `2` |
| `s02` | `45` | `Coder` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A11` | `227313.39664575` | `227336.865633791` | `23.468988040986005` | `2` |
| `s02` | `46` | `Coder` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `227336.865919541` | `227401.311950125` | `64.44603058401844` | `0` |
| `s02` | `47` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `227401.465160041` | `227420.060937458` | `18.59577741700923` | `0` |
| `s02` | `48` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `227420.06126925` | `227430.391979291` | `10.33071004098747` | `0` |
| `s02` | `49` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `227430.392272083` | `227445.92136475` | `15.52909266698407` | `0` |
| `s02` | `50` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `227445.921609916` | `227456.804174208` | `10.882564291998278` | `0` |
| `s02` | `51` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A12` | `227456.804475666` | `227467.202261166` | `10.397785500012105` | `2` |
| `s02` | `52` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `227467.202592791` | `227489.207540458` | `22.00494766701013` | `0` |
| `s02` | `53` | `Planner` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `227489.219581333` | `227552.481552125` | `63.26197079202393` | `0` |
| `s02` | `54` | `Planner` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `227552.481736416` | `227615.206053791` | `62.72431737498846` | `0` |
| `s02` | `55` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A13` | `227615.206332416` | `227655.213334791` | `40.00700237500132` | `0` |
| `s02` | `56` | `Planner` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A13` | `227655.213760208` | `227678.729121375` | `23.51536116702482` | `2` |
| `s02` | `57` | `Planner` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `227678.729370208` | `227700.182636583` | `21.453266374999657` | `0` |
| `s02` | `58` | `Planner` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A14` | `227700.183010166` | `227738.500470833` | `38.317460667021805` | `0` |
| `s02` | `59` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `227738.616954708` | `227757.297993208` | `18.681038499984425` | `0` |
| `s02` | `60` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `227757.298476125` | `227767.218361583` | `9.919885458017234` | `0` |
| `s02` | `61` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `227767.218640416` | `227780.217175666` | `12.998535250022542` | `0` |
| `s02` | `62` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `227780.217388041` | `227790.728240333` | `10.510852292005438` | `0` |
| `s02` | `63` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A12` | `227790.728432958` | `227801.113831666` | `10.385398707992863` | `2` |
| `s02` | `64` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `227801.114198375` | `227821.3153005` | `20.201102124992758` | `0` |
| `s02` | `65` | `Planner` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `227821.333094125` | `227882.790031` | `61.45693687500898` | `0` |
| `s02` | `66` | `Planner` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `227882.790217083` | `227942.877389125` | `60.08717204199638` | `0` |
| `s02` | `67` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A13` | `227942.877693041` | `227979.036775083` | `36.159082041995134` | `0` |
| `s02` | `68` | `Planner` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A13` | `227979.037116958` | `228001.460340541` | `22.423223582998617` | `2` |
| `s02` | `69` | `Planner` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228001.460589333` | `228020.982522` | `19.521932667004876` | `0` |
| `s02` | `70` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A14` | `228020.982819333` | `228057.96350425` | `36.98068491698359` | `2` |
| `s02` | `71` | `Planner` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A14` | `228057.975902958` | `228080.926324458` | `22.95042150001973` | `2` |
| `s02` | `72` | `Planner` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `228080.926573708` | `228142.092362875` | `61.16578916698927` | `0` |
| `s02` | `73` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A01` | `228142.165809166` | `228160.16759775` | `18.001788583991583` | `0` |
| `s02` | `74` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A02` | `228160.167893541` | `228169.221977083` | `9.054083542025182` | `0` |
| `s02` | `75` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A03` | `228169.222194166` | `228179.2048835` | `9.982689333992312` | `0` |
| `s02` | `76` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A09` | `228179.205063041` | `228188.846651083` | `9.64158804199542` | `0` |
| `s02` | `77` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A12` | `228188.846906375` | `228198.991624583` | `10.144718208000995` | `0` |
| `s02` | `78` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A15` | `228198.991803083` | `228208.768582708` | `9.77677962501184` | `2` |
| `s02` | `79` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228208.768874041` | `228228.070684416` | `19.30181037497823` | `0` |
| `s02` | `80` | `Reviewer` | `second_malformed=False; blocked-close` | `blocked-close` | `A05` | `228228.081824458` | `228286.877512583` | `58.79568812501384` | `0` |
| `s02` | `81` | `Reviewer` | `second_malformed=False; blocked-close` | `blocked-close` | `A06` | `228286.877715541` | `228346.547489625` | `59.66977408400271` | `0` |
| `s02` | `82` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A16` | `228346.547814875` | `228382.709916583` | `36.16210170800332` | `0` |
| `s02` | `83` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A16` | `228382.710239666` | `228404.517033791` | `21.80679412500467` | `2` |
| `s02` | `84` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228404.517281916` | `228425.295913333` | `20.77863141699345` | `0` |
| `s02` | `85` | `Reviewer` | `second_malformed=False; command=planveyor_runtime_py` | `format-correction` | `A17` | `228425.296212708` | `228463.125354083` | `37.82914137499756` | `0` |
| `s02` | `86` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A18` | `228463.137306666` | `228472.547169375` | `9.409862708998844` | `0` |
| `s02` | `87` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A19` | `228472.547352333` | `228481.706494416` | `9.15914208299364` | `0` |
| `s02` | `88` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A20` | `228481.706669416` | `228490.649919208` | `8.9432497920061` | `0` |
| `s02` | `89` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A21` | `228490.650089208` | `228499.664082916` | `9.013993707980262` | `0` |
| `s02` | `90` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A22` | `228499.664243916` | `228508.657973541` | `8.993729625013657` | `0` |
| `s02` | `91` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A23` | `228508.658177125` | `228517.846518208` | `9.18834108300507` | `0` |
| `s02` | `92` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A24` | `228517.846741541` | `228527.226600041` | `9.379858500004048` | `0` |
| `s02` | `93` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A25` | `228527.226761958` | `228536.866974083` | `9.64021212499938` | `0` |
| `s02` | `94` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A26` | `228536.867186291` | `228545.836787708` | `8.969601416989462` | `0` |
| `s02` | `95` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A27` | `228545.836958916` | `228554.582136875` | `8.745177958975546` | `0` |
| `s02` | `96` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A28` | `228554.582321416` | `228563.350705708` | `8.768384291994153` | `0` |
| `s02` | `97` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A29` | `228563.350895583` | `228572.503503791` | `9.152608208009042` | `0` |
| `s02` | `98` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A30` | `228572.503762583` | `228581.812827791` | `9.309065208013635` | `0` |
| `s02` | `99` | `Reviewer` | `second_malformed=False; command=planveyor_followups_capture` | `format-correction` | `A31` | `228581.813033166` | `228591.000917833` | `9.187884667015169` | `0` |
| `s02` | `100` | `Reviewer` | `second_malformed=False; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228591.001086291` | `228610.110505833` | `19.109419541986426` | `0` |
| `s02` | `101` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A01` | `228610.181087541` | `228627.81645575` | `17.635368209012086` | `0` |
| `s02` | `102` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A02` | `228627.816777708` | `228637.262300125` | `9.445522416994208` | `0` |
| `s02` | `103` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A03` | `228637.262547375` | `228647.676043666` | `10.413496291002957` | `0` |
| `s02` | `104` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A09` | `228647.676228125` | `228657.400425333` | `9.724197208008263` | `0` |
| `s02` | `105` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A12` | `228657.400658458` | `228667.214867458` | `9.814209000003757` | `0` |
| `s02` | `106` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A15` | `228667.215040166` | `228677.207358416` | `9.992318250006065` | `2` |
| `s02` | `107` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228677.207723541` | `228697.151433` | `19.943709458981175` | `0` |
| `s02` | `108` | `Reviewer` | `second_malformed=True; blocked-close` | `blocked-close` | `A05` | `228697.163328958` | `228756.810665083` | `59.64733612499549` | `0` |
| `s02` | `109` | `Reviewer` | `second_malformed=True; blocked-close` | `blocked-close` | `A06` | `228756.810844208` | `228817.462359708` | `60.65151550000883` | `0` |
| `s02` | `110` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A16` | `228817.462664416` | `228853.445242666` | `35.98257824999746` | `0` |
| `s02` | `111` | `Reviewer` | `second_malformed=True; command=planveyor_followups_capture` | `format-correction` | `A16` | `228853.44568275` | `228876.930438541` | `23.484755790996132` | `2` |
| `s02` | `112` | `Reviewer` | `second_malformed=True; command=planveyor_docs_closeout` | `format-correction` | `A04` | `228876.930685333` | `228897.405243541` | `20.47455820799223` | `0` |
| `s02` | `113` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A17` | `228897.405576583` | `228934.686216958` | `37.28064037501463` | `2` |
| `s02` | `114` | `Reviewer` | `second_malformed=True; command=planveyor_runtime_py` | `format-correction` | `A17` | `228934.699173916` | `228956.851912958` | `22.15273904200876` | `2` |
| `s02` | `115` | `Reviewer` | `second_malformed=True; consumed-close` | `consumed-close` | `A06` | `228956.852135125` | `229016.996596666` | `60.144461541000055` | `0` |
| `s02-negative` | `1` | `Architect` | `collector-Architect` | `collector-Architect` | `A32` | `229071.070899541` | `229081.135448166` | `10.064548624999588` | `2` |

### s11: whole-command, boundary и исходные business intervals

Все строки этой секции относятся к literal `s11` ID и `role=Planner`; `clock=time.monotonic`, `units=seconds`. Для каждой axis сохранены `marker=transaction.done`, `marker=lock.release`, `release_parent=missing`; в последнем subcase первый role call даёт 126, второй 0, исходный shell result = `126:0`. Release-symlink contention и interrupted-holder branches также выполнены внутри целого method, но отдельной timing instrumentation для них этот diff не добавляет.

Whole-command — исходная область вокруг `self._run`, включая её существующий shell setup; aggregate serialization/print выполняется после end sample и до исходных rc/60 s assertions.

| Axis | Subcase | Raw whole start | Raw whole end | Raw whole elapsed | actual shell rc |
| --- | --- | --- | --- | --- | --- |
| `3.10` | `marker=transaction.done` | `225858.772799458` | `225869.914134041` | `11.141334582993295` | `126` |
| `3.10` | `marker=lock.release` | `225870.8970385` | `225882.298933541` | `11.401895040995441` | `126` |
| `3.10` | `release_parent=missing` | `225885.174469708` | `225906.03827675` | `20.863807042012922` | `0` |
| `3.12` | `marker=transaction.done` | `229017.99090975` | `229029.50913425` | `11.51822450000327` | `126` |
| `3.12` | `marker=lock.release` | `229030.558707958` | `229042.054963166` | `11.496255208010552` | `126` |
| `3.12` | `release_parent=missing` | `229045.160512458` | `229067.306383083` | `22.145870624983218` | `0` |

Boundary — raw samples отдельных writers непосредственно до и после role call. Интервал включает остаток before-writer, его diagnostic sidecar и запуск/import after-writer; он не равен внутренней стоимости самой роли.

| Axis | Subcase | Call | Raw boundary start | Raw boundary end | Raw boundary elapsed | actual role rc |
| --- | --- | --- | --- | --- | --- | --- |
| `3.10` | `marker=transaction.done` | `1` | `225860.207684458` | `225869.896277208` | `9.688592749997042` | `126` |
| `3.10` | `marker=lock.release` | `1` | `225872.424347791` | `225882.282853` | `9.85850520900567` | `126` |
| `3.10` | `release_parent=missing` | `1` | `225886.842596` | `225896.342157` | `9.499561000004178` | `126` |
| `3.10` | `release_parent=missing` | `2` | `225896.368388208` | `225906.020753333` | `9.652365124988137` | `0` |
| `3.12` | `marker=transaction.done` | `1` | `229019.471223583` | `229029.4866825` | `10.015458916983334` | `126` |
| `3.12` | `marker=lock.release` | `1` | `229032.141304291` | `229042.033117375` | `9.891813083988382` | `126` |
| `3.12` | `release_parent=missing` | `1` | `229046.81741425` | `229057.09038825` | `10.27297400002135` | `126` |
| `3.12` | `release_parent=missing` | `2` | `229057.121834666` | `229067.287684958` | `10.165850291989045` | `0` |

Business inputs ниже — исходные durable `.9f` timestamp strings, прочитанные как float; это прежние assertion inputs, не новые raw samples. Все исходные `elapsed < 5.0` и `whole_command_elapsed < 60.0` сохранены и прошли; overhead не вычитался.

| Axis | Subcase | Call | Interval | Original start | Original close | Original elapsed |
| --- | --- | --- | --- | --- | --- | --- |
| `3.10` | `marker=transaction.done` | `1` | `fault→close` | `225867.402612625` | `225869.910754791` | `2.5081421659851912` |
| `3.10` | `marker=lock.release` | `1` | `fault→close` | `225879.824920458` | `225882.295903333` | `2.470982875005575` |
| `3.10` | `release_parent=missing` | `1` | `fault→close` | `225893.713889833` | `225896.355210666` | `2.641320833005011` |
| `3.10` | `release_parent=missing` | `2` | `retry start→close` | `225903.523165708` | `225906.034999583` | `2.5118338750035036` |
| `3.12` | `marker=transaction.done` | `1` | `fault→close` | `229026.944820166` | `229029.50297` | `2.558149833988864` |
| `3.12` | `marker=lock.release` | `1` | `fault→close` | `229039.445259458` | `229042.051176541` | `2.605917082983069` |
| `3.12` | `release_parent=missing` | `1` | `fault→close` | `229054.386790833` | `229057.105911666` | `2.7191208330041263` |
| `3.12` | `release_parent=missing` | `2` | `retry start→close` | `229064.639646708` | `229067.302951125` | `2.663304416986648` |

### s11: каждый timestamp writer и предел измеренной стоимости

Точный scope каждого `writer_body_elapsed_seconds`: после прежних imports, перед `Path/open`, через timestamp write/flush/fsync и chmod. Это body cost, не whole-process cost. Raw sample сохранён отдельно от прежнего `.9f` text. Диагностические import/encoding/sidecar write идут после body end; их стоимость, Python launch/import/scheduling и clock-sampling overhead = `UNKNOWN`. Actual writer Python version совпадает с axis provenance; private executable/path остаются `<REDACTED>`.

| Axis | Subcase | Call | Point | Added boundary | Raw sample | Original .9f text | Body raw start | Body raw end | Body raw elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `3.10` | `marker=transaction.done` | `1` | `fault` | `false` | `225867.402612625` | `225867.402612625` | `225867.401989125` | `225867.402982625` | `0.0009934999980032444` |
| `3.10` | `marker=transaction.done` | `1` | `close` | `false` | `225869.910754791` | `225869.910754791` | `225869.910157708` | `225869.91086125` | `0.0007035420276224613` |
| `3.10` | `marker=transaction.done` | `1` | `role_call_before` | `true` | `225860.207684458` | `225860.207684458` | `225860.20626125` | `225860.207765625` | `0.001504375017248094` |
| `3.10` | `marker=transaction.done` | `1` | `role_call_after` | `true` | `225869.896277208` | `225869.896277208` | `225869.895684583` | `225869.896376416` | `0.0006918330036569387` |
| `3.10` | `marker=lock.release` | `1` | `fault` | `false` | `225879.824920458` | `225879.824920458` | `225879.824294791` | `225879.825344291` | `0.0010494999878574163` |
| `3.10` | `marker=lock.release` | `1` | `close` | `false` | `225882.295903333` | `225882.295903333` | `225882.295320541` | `225882.296007083` | `0.0006865420145913959` |
| `3.10` | `marker=lock.release` | `1` | `role_call_before` | `true` | `225872.424347791` | `225872.424347791` | `225872.423680041` | `225872.424444791` | `0.000764749973313883` |
| `3.10` | `marker=lock.release` | `1` | `role_call_after` | `true` | `225882.282853` | `225882.282853000` | `225882.282253458` | `225882.282970166` | `0.0007167080184444785` |
| `3.10` | `release_parent=missing` | `1` | `fault` | `false` | `225893.713889833` | `225893.713889833` | `225893.713273708` | `225893.714252958` | `0.0009792499768082052` |
| `3.10` | `release_parent=missing` | `1` | `close` | `false` | `225896.355210666` | `225896.355210666` | `225896.354593583` | `225896.355311916` | `0.0007183330017141998` |
| `3.10` | `release_parent=missing` | `2` | `start` | `false` | `225903.523165708` | `225903.523165708` | `225903.522517375` | `225903.523539166` | `0.001021790987579152` |
| `3.10` | `release_parent=missing` | `2` | `close` | `false` | `225906.034999583` | `225906.034999583` | `225906.034356916` | `225906.035089125` | `0.0007322090095840394` |
| `3.10` | `release_parent=missing` | `1` | `role_call_before` | `true` | `225886.842596` | `225886.842596000` | `225886.84200025` | `225886.842692083` | `0.0006918330036569387` |
| `3.10` | `release_parent=missing` | `1` | `role_call_after` | `true` | `225896.342157` | `225896.342157000` | `225896.3415125` | `225896.342253916` | `0.0007414160063490272` |
| `3.10` | `release_parent=missing` | `2` | `role_call_before` | `true` | `225896.368388208` | `225896.368388208` | `225896.36778975` | `225896.368478125` | `0.0006883750029373914` |
| `3.10` | `release_parent=missing` | `2` | `role_call_after` | `true` | `225906.020753333` | `225906.020753333` | `225906.020105458` | `225906.020845958` | `0.0007404999923892319` |
| `3.12` | `marker=transaction.done` | `1` | `fault` | `false` | `229026.944820166` | `229026.944820166` | `229026.944598208` | `229026.9449505` | `0.00035229200148023665` |
| `3.12` | `marker=transaction.done` | `1` | `close` | `false` | `229029.50297` | `229029.502970000` | `229029.502762833` | `229029.503067875` | `0.0003050419909413904` |
| `3.12` | `marker=transaction.done` | `1` | `role_call_before` | `true` | `229019.471223583` | `229019.471223583` | `229019.470752208` | `229019.471316375` | `0.0005641670140903443` |
| `3.12` | `marker=transaction.done` | `1` | `role_call_after` | `true` | `229029.4866825` | `229029.486682500` | `229029.48647425` | `229029.486786583` | `0.00031233299523591995` |
| `3.12` | `marker=lock.release` | `1` | `fault` | `false` | `229039.445259458` | `229039.445259458` | `229039.445055958` | `229039.44563425` | `0.0005782920052297413` |
| `3.12` | `marker=lock.release` | `1` | `close` | `false` | `229042.051176541` | `229042.051176541` | `229042.050904791` | `229042.051276083` | `0.0003712920006364584` |
| `3.12` | `marker=lock.release` | `1` | `role_call_before` | `true` | `229032.141304291` | `229032.141304291` | `229032.141110083` | `229032.141417041` | `0.000306958012515679` |
| `3.12` | `marker=lock.release` | `1` | `role_call_after` | `true` | `229042.033117375` | `229042.033117375` | `229042.032836708` | `229042.033206291` | `0.00036958299460820854` |
| `3.12` | `release_parent=missing` | `1` | `fault` | `false` | `229054.386790833` | `229054.386790833` | `229054.386550916` | `229054.386929291` | `0.0003783749998547137` |
| `3.12` | `release_parent=missing` | `1` | `close` | `false` | `229057.105911666` | `229057.105911666` | `229057.105704416` | `229057.106020458` | `0.00031604201649315655` |
| `3.12` | `release_parent=missing` | `2` | `start` | `false` | `229064.639646708` | `229064.639646708` | `229064.639407458` | `229064.640032791` | `0.0006253330211620778` |
| `3.12` | `release_parent=missing` | `2` | `close` | `false` | `229067.302951125` | `229067.302951125` | `229067.302734875` | `229067.303045208` | `0.00031033300911076367` |
| `3.12` | `release_parent=missing` | `1` | `role_call_before` | `true` | `229046.81741425` | `229046.817414250` | `229046.817133166` | `229046.817525708` | `0.00039254198782145977` |
| `3.12` | `release_parent=missing` | `1` | `role_call_after` | `true` | `229057.09038825` | `229057.090388250` | `229057.09016225` | `229057.090501083` | `0.00033883299329318106` |
| `3.12` | `release_parent=missing` | `2` | `role_call_before` | `true` | `229057.121834666` | `229057.121834666` | `229057.121607833` | `229057.121946958` | `0.00033912502112798393` |
| `3.12` | `release_parent=missing` | `2` | `role_call_after` | `true` | `229067.287684958` | `229067.287684958` | `229067.287457083` | `229067.287790583` | `0.0003335000074002892` |

### Добавленная observation activity и S2-граница

Первые три counts — **planned/spec counts**, именно так они интерпретируются в этом отчёте по `risk:R1`; их исходные field names не доказывают фактическое выполнение при incomplete run. Здесь каждый из запланированных writers имеет валидный observation sidecar; missing/parse errors=0. Counts записанных sidecars — наблюдаемый факт доступных records, не доказательство числа иных процессов или общей стоимости I/O.

| Axis | Subcase | Planned total writers | Planned added boundary writers | Planned boundary timestamp writes | Observed writer sidecars | Diagnostic sidecar records | Missing | Parse errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `3.10` | `marker=transaction.done` | `4` | `2` | `2` | `4` | `4` | `0` | `0` |
| `3.10` | `marker=lock.release` | `4` | `2` | `2` | `4` | `4` | `0` | `0` |
| `3.10` | `release_parent=missing` | `8` | `4` | `4` | `8` | `8` | `0` | `0` |
| `3.12` | `marker=transaction.done` | `4` | `2` | `2` | `4` | `4` | `0` | `0` |
| `3.12` | `marker=lock.release` | `4` | `2` | `2` | `4` | `4` | `0` | `0` |
| `3.12` | `release_parent=missing` | `8` | `4` | `4` | `8` | `8` | `0` | `0` |

В исходный fault→close попадают остаток fault-writer, его новый JSON sidecar и дополнительный after-boundary writer с sidecar перед прежним close sample. Для retry аналогично участвует start-writer. Before-boundary writer расположен до fault/start, а close-writer diagnostics после close sample входят только в whole-command. Суммирование body costs не изолирует observer overhead: исходные writers уже существовали, часть их body лежит вне business interval, diagnostic I/O и process costs не измерены. Никаких вычитаний, пересчётов бизнес-assertion или выводов о hosted cause здесь нет.

### Controlled timeout и неполное наблюдение

На обеих axes fresh Contracts `p2_controlled` из unchanged draft подтвердил terminal rc 0/2, сохранение CompletedProcess object/hash fields и `TimeoutExpired` с тем же re-raise/partial stdout+stderr/prior trace. Timeout report остаётся `public_pi_command_timeout.v1`, `state=nonterminal_timeout`, `command_terminal=false`, deadline=120; верхний terminal `actual_rc` отсутствует. Это три mocked subprocess cases на axis, не физическое исполнение 120 s deadline/cleanup и не замена шести Coder invocations.

Exact-source Risk probe incomplete s11 report сохранил `original_failure`, четыре missing observations и `UNKNOWN` для business/boundary values, но выдал planned counts 4/2/2 при нуле запущенных writers. Probe structural, без subprocess; будущие неполные observations не считать измеренными процессами. Это локальная S2 ambiguity в diagnostics, без false pass или изменения original exception.

## Команды и проверенные результаты
Все lifecycle helpers вызваны через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD"` в том же declared envelope; implementation shell files не source-ились ролью. Read-only test inventory и log parsing не являются новым test harness.

| Проверка | Результат / граница |
| --- | --- |
| Fresh native bare-login prerequisite | actual rc=0; Python 3.12/samefile/physical TMPDIR outside Git; отдельный launch proof |
| `planveyor_runtime_py review_artifact_lint.py --project-root "$PWD" --select-risk-lane --origin-plan docs/plans/261101_1252_ci_runtime_timing_diagnostics.md --json` | actual rc=0, selected current Risk run; повторён перед materialization |
| `planveyor_review_target_snapshot docs/plans/261101_1252_ci_runtime_timing_diagnostics.md --current-bundle` | actual rc=0; full v2 producer совпал с nested support; manual target hash не создавался |
| `planveyor_plan_bundle --scope-check docs/plans/261101_1252_ci_runtime_timing_diagnostics.md` | actual rc=0, scope_ok=true, шесть exact paths; planned review был только completion debt |
| Source-before / HEAD / source-after / current AST readback | actual rc=0; 38/58 original IDs, все assertion/fail/subTest AST и guard bytes сохранены |
| Шесть narrow unittest executions из plan Commands | Coder executions переиспользованы по current hashes; для каждого actual rc=0/Ran 1/OK и нулевые skipped/error/failure/expected/unexpected counts |
| Fresh declared `p2_controlled` на Python 3.10/3.12 | actual rc=0 на обеих axes; rc0/rc2/TimeoutExpired parity, не physical deadline |
| Fresh `env -u PLANVEYOR_ROOT "$p2_python" -B scripts/run_test_shard.py --check` | actual rc=0 на обеих axes; 3517 IDs, exact-once partition, suite не исполнялся |

Primary log/provenance root: `.tmp/ci_p2_proof/coder-20261101T120648Z/`. `results.tsv` SHA-256 `4d04d6414bb568a67e8026e1d328b99db4b29eff1fde3bbbe13dbc38c62e65c7`; before/after inventories SHA-256 `113d8a351ea082d061f82e91681580a36911227b4c4df10080189efa91ad0e5e` / `df968c031796623af1948987429bcf727bb4acba1ec12fe437ab13a9bd61ba1f`. Original failed probe SHA-256 `17c1cd89d2c620770aa78f76051bf3414b82ea6582433c38da3a3ce9c1540e2a` сохранён.

Fresh Contracts readbacks: `.tmp/ci_p2_proof/reviewer-contracts-001/independent-proof-readback.json` SHA-256 `675c916f385a0345a92fde217a13bf736c75780372b58c72b4077a8fd0d92404`; `native-prerequisite.json` SHA-256 `fce22358061497ea97e5f3a12cf49adb6c7f0f2f864ab9cc280aab27de337e12`; `fresh-checks.json` SHA-256 `4136f8f3dfe8ff2cdf26a092fe7d02cae90e7a59bb09151d96c29c53bd88c2a6`. Controlled logs обеих axes имеют SHA-256 `b61ed02458f88bc9505e95525f41da50e6c069ee082caa0b7d89e61a1b08a4fd`; partition logs — `5502a55f07ac07569aeefbebff8c3d8c58d24b70ce4cca9aa199e47fbdeac72f`. Counts s01…s14: `234/222/342/169/360/513/263/318/75/109/34/48/172/658`; полный suite не запускался.

## Exact bundle hygiene
- Exact bundle hygiene: `git diff HEAD --check -- scripts/test_contract_authority_shell.py scripts/test_planveyor_init_capture.py` — actual rc=0; повторяется на последних bytes перед handoff.
- Untracked files check: отдельный exact-path readback current plan, draft, review и literal Risk support через standard Python file primitives — actual rc=0; trailing whitespace, merge markers и private absolute paths отсутствуют. Четыре paths проверены явно, без directory glob или изменения index; повторяются на последних bytes.
- Completion gates: current review lint с literal `--origin-plan`, plan lint, strict `planveyor_plan_bundle --check` и обе scoped document команды по literal plan/draft/review дали actual rc=0; strict bundle содержит шесть paths, один root, zero issues. Mandatory support прошёл собственный canonical schema/hash/current-snapshot readback. Pre-handoff logs: `.tmp/ci_p2_proof/reviewer-contracts-001/review-lint-pre-handoff.log`, `plan-lint-pre-handoff.log`, `bundle-check-pre-handoff.log`, `doc-links-pre-handoff.log`, `doc-basic-pre-handoff.log`. После этой final write те же checks и exact hygiene повторяются в `*-final.log`; non-green запрещает handoff.

## Визуальные доказательства
- Visual env: N/A (why=только test diagnostics; UI/browser/visual contract не меняется, visual proof не отложен).

## Последующие gates
AC8 остаётся открытым. Перед semantic commit Architect выполняет своё review/disposition `risk:R1`, current strict bundle/index-worktree parity и отдельный standalone dictionary scanner на окончательно staged inventory; затем native local closeout. Manager владеет terminal capture/followups/PI/final docs. Публикация П2, hosted CI rerun/cancel и cause fix не разрешены. Scoped review/document proof не закрывает full-suite, release/p0 или прежний canonical debt.

## Архитектурное ревью
Вердикт: принято.

Принят текущий test-only semantic diff двух declared targets с bundle SHA-256 `4c534ea3e2de0ddb4e3f70ea19a6934c264b5ce88dc637ca3a15851a30630815`. Own current review lint/strict bundle/public snapshot прошли; source bytes точно совпали с обеими execution axes и nested immutable Risk support. Независимая проверка исходных logs и AST подтвердила шесть rc=0/Ran 1/OK без skips/errors/failures, прежние 38/58 IDs, все assertions/subcases и guards. Все 232 s02 строки отчёта совпали с raw observations; s11 сохраняет три reports, четыре role calls и 16 writers на axis, исходные интервалы и expected 126:0. Это readback ранее выполненной matrix, без нового behavioral rerun.

Disposition `risk:R1`: остаточный S2 принят, blocker=no; naming clarification явно вынесена в `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md#Follow-ups-deferred` для штатной source-bound capture family. Три counters считаются planned/spec counts. Фактическое исполнение и стоимость нельзя выводить из этих counters или отсутствующих sidecars; missing/parse errors и original failure сохраняют самостоятельное значение. Current report уже соблюдает эту границу, текущие observations полны, исходные assertions не ослаблены. Поэтому исправление названий не блокирует приёмку текущего результата; оно не разрешает cause/runtime fix или публикацию.

Observer effect принят как явное ограничение диагностики: body-only timing исключает launch/import/scheduling/sidecar I/O, boundary включает часть observer work, неизвестные составляющие остаются UNKNOWN. Ничего не вычитается из business interval; локальные числа не устанавливают hosted cause или влияние версии Python. Product/runtime/API/defaults/config и frozen runtime не меняются; дополнительного deployment pin для этого test-only diff не требуется.

Suggestions/objections и documentation impact reconciled: единственный новый residual item — `risk:R1`; synchronous canon/registry changes не нужны. Visual audit: N/A (why=no UI change). `runner_quality: row_status=not_applicable` — materialized lane metadata указывает `codex-native-collab`, external runner contribution не заявлен; unknown model/effort/profile/SID не реконструируются из имени handle.

Arch verdict закрывает semantic review. Exact local commit допускается только после simulated/final plan lint, final scoped document/review/bundle gates, canonical stage/preflight, index/worktree parity и standalone dictionary scanner на последних bytes. Обязательный Manager terminal tail подтверждается последующими helper-owned carriers; ни capture, ни full-suite/hosted/publication acceptance этим verdict не объявляются выполненными. AC8 уточнён в плане по этой существующей lifecycle границе, без отмены обязательств.
