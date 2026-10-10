# Роли: индекс

Этот файл навигирует по public shared role docs. Root corpus определяет process core; выбранный project и explicit plan определяют application-specific context.

## Роли

- [Architect](architect.md) — архитектурные решения и plan; не пишет продуктовый код.
- [Planner](planner.md) — превращает требования и решения в plan + code draft; не пишет продуктовый код.
- [Coder](coder.md) — реализует authorized plan scope и пишет current validation evidence.
- [Reviewer](reviewer.md) — review current range и visual acceptance, когда она требуется; не правит продуктовый код.
- [Manager](manager.md) — invariant/source-of-truth layer для роутинга «кто следующий и что запускать».

## Prompts и modes

- Shared role/pipeline prompts: `docs/tools/prompts/`.
- Sibling launch, mode and lifecycle preconditions: `docs/README.md`. Этот файл
  доставляется вместе с sibling и содержит внешний facade, init/doctor/upgrade
  и границу live role calls.
- Source-owned lifecycle/packet reference: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/lifecycle-and-packets.md"`.
  Это reference движка, а не путь в sibling; открывай его только когда выбран
  source-owned lifecycle/packet маршрут.
- Source-owned Golden Path reference: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`.
  Для target-local carrier используй literal path, объявленный текущим project
  contract, а не несуществующую копию guide в sibling.
- Mode-specific Manager algorithms: `manager_collab_pipeline.md`, `manager_custom_pipeline.md` и `manager_collab_merge_pipeline.md` в `docs/tools/prompts/`.
- Direct ZCode Manager overlay: `docs/tools/prompts/zcode/manager_pipeline.md`. В первой версии маршрут работает только в корне Planveyor (Self-Planveyor): bootstrap-файлы `.zcode/commands/manager-init.md` и `.zcode/agents/planveyor-role-agent.md` лежат только там и в sibling не доставляются. В sibling ZCode-маршрут Manager не поддержан; Manager в sibling запускается через facade.

## Шаблон

- [role_template.md](role_template.md) — каркас новой роли с pointers вместо дублирования operational process.

## Shared core и target-local input

Root role docs и prompts не назначают product/runtime defaults. Data model, interface, UI harness, repository tests и integration policy принадлежат выбранному project и должны быть literal input текущего plan.

Public `default` и `planveyor` identities читают root process corpus. `target-local` identity принадлежит consumer repository: его prompt sources, credentials и project anchors должны быть declared and validated там. При отсутствии такого contract dispatch останавливается с blocker; root corpus не создаёт profile substitute.

Если роль или prompt велит открыть другой Markdown carrier, canonical form = literal repo path `docs/...`; эти paths не являются implicit shell-execution instruction.
