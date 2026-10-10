# Playbook: post-merge visual review (merge-range)

Это не отдельная роль и по умолчанию не отдельный tracker-step. Это дополнение
к `docs/playbooks/review_merge_range.md`, когда точный range и выбранный
project/profile contract требуют визуального доказательства runtime-сценария.
Общий playbook не предполагает web-стек, browser launcher или путь к smoke
документу: они берутся только из materialized plan, Context links либо
repo-local profile canon.

Если дополнение идёт через Manager merge pipeline, Manager не пингует
Reviewer/Architect во время прогона и не прерывает running step; tracker
двигается только после completion текущего visual sanity pass.

## Когда применять

Добавляй это дополнение, если хотя бы одно из условий подтверждено текущими
bytes:

- changed-path/harness классифицирует затронутую поверхность как runtime UI;
- plan или profile canon обещает visual acceptance для этой поверхности;
- reference-driven contract требует screenshots для конкретных состояний.

Не создавай visual lane по инерции. Для non-UI range оставь в review artifact
`## Visual evidence` с `N/A (why=...)`, привязанным к exact target. `N/A` не
подменяет отсутствующий или сломанный обязательный harness.

## Вход

- exact `BASE..HEAD` и current review artifact;
- selected repo profile и source Context links;
- declared runtime/UI harness, команда запуска и expected scenarios;
- current-bundle или range snapshot, если он требуется review flow;
- затронутые dev-plan'ы и review artifacts в диапазоне;
- reference assets и source scenarios, если они объявлены.

Исторические screenshots, старые review assets, широкий string search и
placeholder-данные не являются proof для current target. Если сценарий зависит
от live object/user/state, сначала materialize repo-backed discovery или
deterministic seed step.

## Результат

Раздел visual evidence находится в текущем review artifact и содержит evidence
только для его basename. Screenshots и machine outputs лежат в
`docs/code_reviews/assets/<REVIEW_BASENAME>/`, имеют понятное имя состояния и
строку `Proves:`. Они immutable для завершённого review: baseline-update,
историческая папка или `.tmp/**` могут быть только diagnostic context.

Отчёт фиксирует:

- exact target, bundle/snapshot и changed runtime paths;
- selected profile, declared harness и literal command, которая дала proof;
- modes/states, expected result, actual result и ссылки на assets;
- command/runner receipt, если его требует выбранный harness;
- различение `harness drift`, `product regression` и отсутствующего proof;
- `N/A (why=...)` только для действительно не применимой lane.

Evidence снимается только на merged code из текущего `main`/exact range, не на
исходной feature branch.

## Как собрать checklist

1. Прочитай plan, Context links и selected profile до запуска. Не выводи
   framework, port, credentials, data fixtures или command из имени файла.
2. Сверь changed paths с declared harness и выпиши только затронутые
   user-visible scenarios. Для reference parity назови disputed points и
   states буквально.
3. Зафиксируй expected data/state: что должно быть populated, empty, selected,
   enabled/disabled или hidden. Не выдавай empty state за доказательство
   populated scenario.
4. Выбери primary lane, уже объявленный project/profile contract. Ad-hoc
   automation, inline run-code и temporary script не становятся закрывающим
   proof. Если primary lane недостаточно воспроизводим, это reviewability gap
   с next owner, а не повод тихо подменить команду.
5. Для выбранного compatibility profile применяй только его явно declared smoke scenarios,
   commands и receipts. Такой contract не задаёт default для другого проекта;
   current-host result без declared success criterion не является closing proof.
6. Собери `Source scenarios:` из visual claims затронутых dev-plan'ов/reviews
   и declared smoke corpus. Не прогоняй весь corpus ради галочки: нужны
   затронутые sections и обещанные must-not-regress claims. Если promised
   scenario отсутствует в smoke corpus, не пропускай его: добавь scenario в
   checklist и зафиксируй process gap/finding в current review artifact.
   Каждый checklist/source scenario нужно реально прогнать и дать ему строку
   `scenario -> mode -> asset -> verdict` в `Post-merge visual sanity` либо
   current finding/S1 blocker с причиной. Сводка только по mode не может
   молча закрыть обещанный, но непрогнанный scenario.

## Как проверять

1. Подними только declared harness и выполни materialized primary command.
   Сохрани её exit/result и required runner/version receipt рядом с current
   evidence.
2. Проверь каждый declared mode на live surface. DOM/subtree/anchor-scoped
   observation допустима как технический carrier, но не заменяет screenshot,
   когда acceptance требует изображение.
3. Сравни proof с current spec/reference и exact source scenario. Отсутствие
   asset, wrong state, stale source или неясный target — blocker, а не green.
4. Если helper красный, а live path зелёный, сначала классифицируй причину.
   Нельзя закрывать результатом одного зелёного helper'а, когда обещанная
   contextual lane осталась красной или не доказана.
5. Не записывай секреты, cookies, токены или личные данные в screenshots,
   commands и receipts. Используй masked/seeded data, если это предусмотрено
   harness.

Mechanical comparator и human visual inspection — независимые proof lanes.
Выполни exact comparator command и exact human index command для каждого
mandatory mode из materialized `## Review visual lane contract`. Comparator
`pass` не закрывает lane без human verdict, а screenshots не закрывают lane
без comparator `pass`; baseline-update команда никогда не считается closing
comparator proof. Closing assets должны быть non-empty regular non-symlink
files только под current `docs/code_reviews/assets/<REVIEW_BASENAME>/`;
`.tmp/**`, historical/другой basename, traversal и symlink остаются только
diagnostics/context.

## Что писать в review report

Минимальный формат для каждой mode:

```md
## Visual evidence
- Target: `RANGE=<BASE>..<HEAD>` / `BUNDLE=<...>`
- Profile and harness: `<declared source + command>`
- Runtime UI visual evidence state: `<available|not_applicable|missing|...>`
- Comparator command: `<exact declared command>`
- Comparator claim: mechanical
- Comparator result: `<pass|fail|...>`
- Capture status: `<complete|partial|...>`
- Complete index inspected: `<yes|no + evidence>`
- Design verdict: `<verdict>`
- Finding dispositions: `<current finding ids/outcomes>`
- Source scenarios: `<plan/review/profile anchors>`
- Post-merge visual sanity: `<scenario -> mode -> asset -> verdict>`
- Mode: `<state>`
  - Expected: `<observable condition>`
  - Actual: `<result>`
  - Human index (<mode>): `<exact index command/result>`
  - Durable asset (<mode>): `docs/code_reviews/assets/<REVIEW_BASENAME>/<state>.png`
  - Proves: `<exact condition>`
- Runner receipt: `<required receipt | N/A (why=...)>`
```

Если lane обязательна и proof отсутствует, тот же review-file получает
`❌ S1 blocker(ы)` с причиной и next owner. Не создавай второй side-file со
статусом `BLOCKED`, `PARTIAL`, `FROZEN` или `PAUSED`; до закрытия допустим
только interim status `Черновик`.

## Architect / audit handoff

Architect проверяет coverage declared scenarios, freshness target и пригодность
assets к readback, а не только наличие картинок. Post-merge audit обычно не
переснимает UI: он проверяет, что required visual sanity и его receipts
связаны с exact review/audit evidence. Visual success не заменяет code review,
range review, packetization или terminal closeout proof.
