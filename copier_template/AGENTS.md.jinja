# Правила для агентов

Этот репозиторий — независимый sibling Planveyor. План, review, код и правила стека живут здесь; движок находится во внешнем доверенном checkout.

Используйте public executable `planveyor` из trusted launch PATH. Явный `PLANVEYOR_RUNTIME_ROOT` остаётся поддержанным выбором: тогда facade — его `bin/planveyor`. Проверяйте физический regular executable через существующий facade; не ищите другой runtime по диску и не переключайте его при ошибке. Если оба способа отсутствуют, спросите Owner, какой trusted checkout использовать. Не изменяйте shell config, PATH установки, home или зависимости автоматически.

Обычный human path — `planveyor sibling plan`, `architect`, `answer`, `run` или `tui`, затем `close`, `close --commit`, `ready`; init и upgrade используют тот же facade. `sibling` определяет физический project root по текущему каталогу; при двух checkout задайте `--project` перед `sibling`. Для низкоуровневых helper вызовов выберите корень sibling явно: `planveyor --project "$PWD" planveyor_runtime_py <approved-helper.py> [args...]`. Facade сохраняет проверенный runtime pin и Python окружения; собственные `scripts/` этого проекта остаются локальными.

Сначала прочитайте `docs/README.md`, текущий план, `docs/roles/` и нужные `docs/playbooks/`. Новый initial draft создаётся доставленным `planveyor-plan-draft`; если Owner просит сделать его текущим, выберите фактически созданный путь через `sibling plan`. Не создавайте executable code draft до его штатного этапа. Текущий pointer не заменяет Oracle, review, authority и admission.

Пишите только фактические ответы Owner, append-only в существующий Q&A формат. Не фабрикуйте подтверждения и не закрывайте machine-authority вопросы обычным «OK».

Выберите режим явно. `planveyor sibling architect` и разовый `planveyor sibling run` используют `COMMIT_POLICY=human_explicit`: `close` — preview без status/index/live effects, а `close --commit` требует явного разрешения человека на конкретный показанный набор. `planveyor sibling tui` открывает существующий native Manager TUI с `COMMIT_POLICY=native_existing` для выбранного plan, без queue/merge inference. В нём Architect закрывает только exact bundle штатными preview/preflight helpers: simulated Done lint, pre-Done stage/preflight, provisional `Done`, final ordinary lint, restage/preflight и один local exact commit. Failed final gate требует rollback к owning non-Done bytes до stop; Coder и Planner не становятся commit/Done writers.

Если конкретная команда требует разрешения на запись в `.git`, запрашивайте только это узкое разрешение после проверки полного запроса. Не просите blanket grants, отключение sandbox или постоянную запись в home; native policy не отменяет конкретные permission gates. Семантический commit и последующее закрытие документов — отдельные gates; docs `no_op` допустим только по fresh canonical readback. Не отправляйте issue и не публикуйте скрыто; push/publication требуют отдельного явного поручения.

Правила стека и разрешённые локальные изменения процесса находятся в локальных секциях восьми файлов из матрицы `docs/README.md`. Не меняйте статус, authority и порядок lifecycle через локальный override. Не записывайте secrets, адреса серверов и private machine paths в планы, Local rules или evidence. Значения credentials принадлежат локальной обвязке; роли их не читают.
