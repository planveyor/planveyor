# Черновой playbook: reference-driven UI по image/video-референсам

Это cross-role playbook для задач вида:
- `сделать как на приложенной картинке`;
- `повторить форму/таймлайн/модалку по видео`;
- `довести shipped UI до literal reference`, а не просто `сделать лучше`.

Главное правило:
- reference image/video = **literal target on disputed points**, а не moodboard и не `примерно такое направление`.
- Owner не должен быть первым, кто руками раскладывает очевидные визуальные факты из reference; это обязанность Architect/Planner.

Когда использовать
- Owner приложил image/video/reference bundle и ожидает visual parity.
- В plan/review есть формулировки `как на картинке`, `как в видео`, `как в референсе`.
- Спорные точки лежат в layout/geometry/states/content density, а не только в наличии полей.

Когда `N/A`
- reference приложен только как moodboard/brand direction и literal parity не требуется;
- задача про backend/data without runtime UI effect;
- reference не authoritative и Owner явно разрешил свободную интерпретацию.

Связанные carriers
- Plan template: `docs/plans/_template.md`
- Review artifacts: `docs/code_reviews/*`, `docs/doc_reviews/*`
- Visual evidence/gates: выбранный project/profile contract называет source,
  harness и proof carrier для этой surface.

## Обязательное различие

Разделяй два разных типа задач:
1. `relative improvement`
- acceptance = стало лучше, чище, компактнее, без регрессий;
- reviewer может закрывать coarse verdict'ом.

2. `reference parity`
- acceptance = спорные точки совпадают с reference literally;
- reviewer обязан закрывать disputed points поимённо.

Если это второй тип, слова `tighter`, `cleaner`, `closer to reference`, `more compact` **недостаточны**.

## Поток работы

### 1) Architect/Planner: материализовать reference в контракт

Если reference есть, plan обязан содержать отдельный block `Reference decomposition`.

Минимум, что должно быть materialized в plan:
- repo-local reference assets:
  - картинки/кадры должны лежать в repo, а не только в `Downloads`;
  - video-driven задача должна иметь named frames, если спор идёт о конкретных состояниях.
- authoritative target surface(s):
  - opening state;
  - selected/populated state;
  - empty state;
  - toggle states;
  - contextual entry variant, если он есть.
- literal geometry facts:
  - shell width/height expectation;
  - equal-width/equal-height rows;
  - media rail width/height;
  - relative position of labels/controls/previews;
  - footer geometry.
- content rules:
  - what text must appear;
  - what text must **not** be duplicated;
  - what fields must be prefilled/populated in accepted proof.
- state matrix:
  - off/on;
  - collapsed/expanded;
  - empty/selected;
  - before/after create;
  - mode-specific variants.
- behavioral semantics, если UI toggle/state влияет на domain meaning:
  - какие данные/фильтры реально покрываются;
  - какие поля участвуют в runtime logic when visible/hidden.

### 2) Coder: реализовать literal carrier, а не “общее улучшение”

Coder обязан смотреть не только на plan prose, но и на reference asset.

Что нельзя делать:
- неявно заменять literal geometry на generic UI composition;
- принимать populated reference как empty-state implementation proof;
- превращать `small preview cell` в `secondary info card`;
- разносить toggle state semantics в UI и runtime по разным truth sources.

Что обязательно:
- если disputed point можно прибить class/data-carrier'ом — прибить;
- если toggle/state меняет domain semantics — добавить test guard не только на template, но и на runtime carrier;
- accepted screenshot должен показывать **тот же state**, что reference, а не `примерно рядом`.

### 3) Reviewer: absolute parity по disputed points

Reviewer не закрывает такую задачу общими словами.

Review artifact обязан содержать literal checklist disputed points, например:
- `left rows same width`: `yes/no`
- `preview rail unified`: `yes/no`
- `duplicated empty-state labels removed`: `yes/no`
- `accepted proof shows populated key fields`: `yes/no`
- `toggle off hides secondary fields`: `yes/no`
- `toggle on keeps declared layout around primary block`: `yes/no`
- `toggle semantics reflected in runtime data`: `yes/no`

Если review этого не доказывает, значит parity не доказана.

### 4) Helpers/automation: проверять carriers, а не vibes

Automation/helper не заменяет глаз, но должен ловить очевидные регрессии.

Если спорные точки повторяемые, helper должен по возможности проверять:
- explicit class/data-carrier for aligned rows;
- unified media shape carrier;
- no duplicated text markers in preview cells;
- named toggle states;
- populated-value requirement in accepted screenshot flow;
- runtime helper/service that uses the same semantics as the UI.

Если helper проверяет только `modal exists` / `fields exist`, это coarse-structure guard, а не reference-proof.

## Обязательный блок для plan (copy-paste)

Если задача reference-driven, Architect/Planner должен вставить в plan micro-block такого класса:

```md
### Reference-driven UI contract (required)
- Reference assets (repo-local):
  - `docs/code_reviews/assets/<PLAN_OR_REVIEW_BASENAME>/reference_*.jpg`
- Authoritative surfaces/states:
  - `opening`
  - `empty`
  - `selected`
  - `toggle off`
  - `toggle on`
  - `contextual variant` | `N/A`
- Geometry invariants:
  - `<literal row/rail/height/width facts>`
- Content invariants:
  - `<what text must appear>`
  - `<what text must not be duplicated>`
  - `<what must be populated in accepted proof>`
- State/behavior invariants:
  - `<what hidden state removes visually>`
  - `<what the same state changes in runtime semantics>`
- Screenshot proof matrix:
  - `<screenshot name> -> <state> -> <what it proves>`
```

Если этот блок не materialized, Owner почти гарантированно будет первым человеком, который потом руками объяснит очевидное из картинки. Это bad process smell.

## Правила screenshot-proof

Для reference-driven UI acceptance screenshots обязаны быть:
- repo-local;
- state-equivalent to reference;
- named by state, а не абстрактно `modal_1`, `modal_2`;
- linked from review artifact с полем `Proves:`.

Минимальный screenshot matrix:
- opening/reference-equivalent state;
- каждый спорный toggle state;
- populated state, если reference populated;
- contextual/shared variant, если он был обещан в plan.

Нельзя принимать:
- пустой screenshot вместо populated reference;
- screenshot с другим toggle state;
- screenshot после ручной докрутки, если пользовательский путь в helper/review не воспроизводим.

## Правила closeout

### Правило false-green
Если после `Done` приходит замечание вида `literal mismatch against reference`, это по умолчанию:
- `stale closeout / false-green review`, а не `ещё мелкий polish`.

Правильная реакция:
- либо reopen same contract через bounded follow-up;
- либо честно пометить, что предыдущий plan/review закрывали другой acceptance type (`relative improvement`, не `reference parity`).

### Правило ownership
- Architect/Planner отвечают за decomposition.
- Coder отвечает за truthful carrier.
- Reviewer отвечает за absolute proof on disputed points.
- Owner не должен вручную выполнять работу decomposition вместо конвейера.

## Практический чек-лист

Перед handoff на coder/reviewer проверь:
- [ ] reference assets лежат в repo-local path;
- [ ] plan содержит `Reference-driven UI contract`;
- [ ] disputed points materialized literally, без слов `compact/tighter` как единственного acceptance;
- [ ] screenshot matrix перечисляет exact states;
- [ ] если toggle/state влияет на runtime meaning, это записано в plan explicitly;
- [ ] review artifact template/expectation требует `yes/no` closure по disputed points;
- [ ] helper/test guard проверяет хотя бы repeatable carriers, а не только presence-based structure.

## Smells / anti-patterns

Красные флаги:
- `closer to reference` без literal geometry facts;
- acceptance screenshots в других состояниях, чем reference;
- review verdict `стало компактнее` без disputed-point checklist;
- `Done`, после которого Owner всё ещё описывает базовые факты с картинки;
- visual toggle, который красиво скрывает блок, но runtime продолжает считать скрытые поля.

## Куда встраивать в обычный flow

Для UI plan'ов этот playbook не заменяет объявленные visual gates, а усиливает
их.

Правило-подсказка:
- Объявленные visual gates отвечают на вопрос `есть ли visual evidence и must-not-regress gate`.
- Этот playbook отвечает на вопрос `доказали ли мы literal parity against reference, а не просто coarse improvement`.
