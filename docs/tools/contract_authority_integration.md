# Привязка runtime и контрактных источников

Этот документ определяет публичную границу между Planveyor runtime, shared
lifecycle и target-local content. Он не описывает персональные loader’ы,
домашние каталоги или implementation-specific transport.

## Вход runtime

Единственный документированный вход — public facade из physical Planveyor root:

~~~bash
./bin/planveyor <planveyor_function> [args…]
~~~

Facade сам определяет runtime по своему physical path. Не подключай shell
implementation через source и не подменяй root переменной окружения. Для
consumer project передай его явно до функции:

~~~bash
./bin/planveyor --project /absolute/path/to/consumer <planveyor_function> [args…]
~~~

Один вызов не меняет cwd, session state или consumer configuration
после завершения. Если facade, функция или declared runtime unavailable,
это blocker с literal diagnostic, а не повод угадать fallback path.

## Иерархия authority

| Вопрос | Authority |
| --- | --- |
| Доступная публичная функция и runtime boundary | facade/readback |
| Статус и routing plan | selected plan + oracle/readback |
| Shared process contract | canonical role, prompt, playbook или template |
| Target stack, test harness, UI и credentials | selected consumer canon/plan |
| Delivery между repositories | source-local rollout packet + target adoption outcome |
| Execution/result proof | current receipt, review artifact и declared gate |

Chat memory, local shell aliases, stale generated copies и historical snapshots
не заменяют ни один из этих источников.

## Content selection

Shared content IDs default и planveyor используют общий public corpus.
target-local принадлежит consumer и materialize-ится только при реальном
consumer contract. Неизвестный content profile останавливает selection:
нельзя молча выбрать default, profile tree или historical sibling.

Shared default можно переопределить только materialized target-local carrier с
явным owner. Отсутствующий override возвращает shared default; не создавай
пустые profile directories «на вырост».

## Runtime и content evidence

Runtime readback подтверждает только то, что именно он сообщает для текущего
вызова. Он не доказывает semantic acceptance, provider availability или
delivery consumer content.

Для каждого execution/review claim отделяй:

1. command/readback identity;
2. current artifact и scope;
3. semantic verdict от owning role;
4. target-local acceptance, если она требуется;
5. packet/adoption outcome для cross-repository delivery.

Receipt должен содержать только portable paths, placeholders и declared
identities. Secret-shaped values заменяй на <REDACTED>. Local derived state
остаётся external/disposable и не становится checked-in authority.

## Изменение shared contract

Когда меняется shared role, prompt, playbook, template, guide или ADR:

1. Определи source owner и точный changed bundle.
2. Запусти scoped lint/readback, объявленный этим bundle.
3. Если delivery membership требуется, создай source-local rollout packet.
4. Target owner проверяет packet и сам materialize-ит target-local adoption.
5. Сохрани current receipt или review evidence, но не копируй files вручную.

Mirror/readback — диагностический и proof surface. Он не даёт права менять
consumer, queue, runtime configuration, commit или push.

## Session boundary

Runtime может выдавать session handle, init record или role receipt. Они
invocation-specific: current handle не заменяет plan status, а previous green
receipt не authorizes новый child run. Manager читает exact current readback,
останавливается на mismatch/missing evidence и не выбирает fallback runner,
model или target.

## Проверка

Перед публикацией или closeout:

- проверь public docs на private paths, old local loader commands и
  secret-shaped values;
- убедись, что command запускается через facade;
- проверь declared target-local conditions отдельно от shared lifecycle;
- запусти relevant public verify/lint command;
- не заявляй runtime readiness или adoption без current evidence.

См. docs/guides/launch-and-role-modes.md для запуска и
docs/playbooks/portability_substitution_rules.md для portable output.

