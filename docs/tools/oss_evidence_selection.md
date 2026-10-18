# Политика отбора OSS evidence

Этот документ описывает структурный workflow для отбора public-safe evidence перед переносом открытой копии. Он не заменяет ручную или model-assisted смысловую очистку выбранных документов.

## Цель
- Показать сильные стороны plan/review процесса без публикации всего исторического корпуса.
- Подготовить выбранный набор из `30-50` артефактов; рабочая цель по умолчанию: `40`.
- Держать private mapping в `.tmp/oss_release/`, а public manifest выпускать без `source_path`.

## Категории и квоты
| Категория | Цель | Минимум | Что доказывает |
| --- | ---: | ---: | --- |
| `plans` | 10 | 6 | Постановка задачи, scope, DoD, evidence |
| `code_drafts` | 6 | 3 | Планирование implementation surface |
| `code_reviews` | 8 | 4 | Проверка blocker-free handoff |
| `doc_reviews` | 4 | 2 | Документальные проверки и audits |
| `followups` | 4 | 2 | Управление deferred work |
| `canon_notes` | 8 | 4 | Долгоживущие policy/runbook/ADR записи |

Квоты можно корректировать внутри диапазона `30-50`, если выбранный набор сохраняет разнообразие механизмов и понятную историю результата.

## Критерии включения
- Артефакт показывает повторяемый механизм, а не разовую переписку.
- Есть понятный outcome: закрыто, отклонено, deferred с причиной, или принято как policy.
- Документ можно очистить без потери смысла.
- Есть связь с соседними артефактами: plan, draft, review, policy, follow-up.
- Документ полезен внешнему читателю без знания private context.

## Критерии отклонения
- Нужна глубокая смысловая перепись, чтобы удалить private context.
- Документ держит raw external prompt text, полные transcript fragments или неочищенные локальные пути.
- Есть секреты, account identifiers, private hostnames, private repo names или source-only operational details.
- Evidence дублирует более сильный артефакт без новой механики.
- Документ не проходит staged public safety scan после copy step.

## Scoring
Оценивайте каждый кандидат по шкале `0-2`.

| Поле | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `mechanism_score` | Не показывает механизм | Механизм виден частично | Механизм понятен и reusable |
| `outcome_score` | Нет результата | Результат частичный | Результат закрыт и проверяем |
| `cleanup_cost_score` | Дорого очищать | Средняя очистка | Дёшево очищать |
| `diversity_score` | Дубликат | Частично дополняет | Закрывает отдельный тип evidence |
| `linkage_score` | Изолирован | Есть одна ссылка | Есть план/draft/review/policy chain |
| `external_usefulness_score` | Нужен private context | Понятен с пояснением | Понятен сам по себе |

Рекомендуемый порог для попадания в selected TSV: `8+` из `12`, при этом `cleanup_cost_score` не должен быть `0`.

## Selected TSV
Файл selection живёт в `.tmp/oss_release/` и не коммитится.

Формат без header:

```text
source_path<TAB>category<TAB>public_filename<TAB>why_included
```

Правила:
- `source_path` - repo-relative markdown file из настроенного evidence corpus;
- `category` - одно из `plans`, `code_drafts`, `code_reviews`, `doc_reviews`, `followups`, `canon_notes`;
- `public_filename` - только filename, только `*.md`, без slash и traversal;
- `why_included` - краткая причина для public reviewer;
- production validation использует диапазон `30-50`; fixture/smoke может явно передавать `--min-count` и `--max-count`.

## Workflow
```bash
PYBIN="${PYBIN:-python3}"
"$PYBIN" -B scripts/oss_evidence_prepare.py inventory --out .tmp/oss_release/evidence_candidates.tsv
"$PYBIN" -B scripts/oss_evidence_prepare.py score-template --inventory .tmp/oss_release/evidence_candidates.tsv --out .tmp/oss_release/evidence_score_template.tsv
```

После human/model selection создайте `.tmp/oss_release/evidence_selected.tsv`, затем проверьте структуру:

```bash
"$PYBIN" -B scripts/oss_evidence_prepare.py validate-selected --selected .tmp/oss_release/evidence_selected.tsv
"$PYBIN" -B scripts/oss_evidence_prepare.py copy-selected --selected .tmp/oss_release/evidence_selected.tsv --dest .tmp/oss_release/staged_evidence/docs/evidence
"$PYBIN" -B scripts/oss_evidence_prepare.py manifest --selected .tmp/oss_release/evidence_selected.tsv --out .tmp/oss_release/manifest.json
"$PYBIN" -B scripts/oss_release_scan.py --root .tmp/oss_release/staged_evidence --archive-manifest .tmp/oss_release/manifest.json --scope public-copy --format text --fail-on blocker
```

Для implementation smoke допустим один safe row на этот policy file и явный count override:

```bash
printf 'docs/tools/oss_evidence_selection.md\tcanon_notes\toss_evidence_selection_policy.md\tSmoke row for structural helper verification.\n' > .tmp/oss_release/evidence_selected_sample.tsv
"$PYBIN" -B scripts/oss_evidence_prepare.py validate-selected --selected .tmp/oss_release/evidence_selected_sample.tsv --min-count 1 --max-count 50
```

## Boundary
- Helper не выбирает final evidence set сам.
- Helper не переписывает содержимое выбранных документов.
- Public manifest содержит только `public_path`, `category`, `why_included`, `sanitization_status`.
- Staged archive проверяется только через явный `--archive-manifest`: scanner сверяет safe unique `public_path` с точным набором regular files и не использует Git или directory-walk fallback в этом режиме.
- Private mapping остаётся в `.tmp/oss_release/`.

## Ограниченная нормализация private markers

Scanner и private lane F62 используют один `scripts/oss_release_scan.py::marker_findings` с внешними rules из `PLANVEYOR_OSS_SCAN_MARKERS`. Значение переменной должно указывать на regular file вне scan root; явный invalid/inside-root/symlink dictionary даёт `ScanInputError`. В public CI переменная может отсутствовать: scanner сохраняет generic-only правила, а private matcher получает пустой набор. Реальный приватный словарь не входит в fixtures или public artifacts.

Для dictionary-backed matching сохраняется raw view и добавляются конечные представления: NFKC, удаление только U+200B/U+200C/U+200D/U+2060/U+FEFF, затем свёртка только ASCII case-pairs `[Xx]`/`[xX]`. Другие format characters, homoglyph transliteration, regex classes/ranges/groups/quantifiers не раскрываются. Plain/path/author dictionary payload получает NFKC и тот же finite removal; `re:` остаётся скомпилированным regex без переписывания. Plain names длины 1–4 Unicode word characters требуют обе word boundaries; длинные literals и explicit namespaces сохраняют прежнее separator/substring matching.

В content и metadata распознаются только Python-style ordinary/u/r STRING tokens с single/double/triple quotes, строковый `+`, balanced parentheses и допустимая implicit adjacency. Переход physical line допускается внутри тех же parentheses или через explicit continuation. Scalar `ast.literal_eval` применяется только к уже распознанному одиночному STRING token с результатом `str`; scanned code, expressions, calls/imports не исполняются. Names, attributes/subscripts, f/b strings, formatting, multiplication и `.join` не вычисляются; независимый constant argument может быть отдельным fragment. Statement/comment/dynamic boundary запрещает склейку; incomplete token/fragment и unsupported escape оставляют raw-only detection. Overflow/internal parser error fail-closed как `ScanInputError`.

Mapped characters сохраняют physical source spans, в том числе при NFKC composition через static concat. Finding указывает на строку первого contributing source character фактического match, включая поздний token после safe prefix и исходный escape. Один origin/category не дублируется между views, разные occurrences одной строки сохраняются. Path получает только текстовую normalization, без STRING inference; path/metadata findings имеют line0. Нормализованный private path маскируется по исходным spans либо целиком как `<masked>`; token всегда masked. `author:` legal allowance остаётся проверкой исходной exact bare identity в LICENSE/NOTICE с прежними guards, normalized/decoded-only совпадение allowance не получает.

Generic raw rules, security/version exceptions, Git/manifest inventory, `Finding`/JSON/category/severity и CLI exits 0/1/2 сохраняются. Исторические исключения не освобождают current tree, Genesis/refs/history не переписываются.

F62 отдельно сохраняет always-on case-sensitive raw public model policy: GLM/Grok/bare Sol/Astra на word boundaries обнаруживаются; exact `GPT-6.1 Sol`, MinIO и word-internal/case near-misses разрешены. Этот public lane не зависит от dictionary и не получает private normalization; private matching выполняет только общий scanner helper. Addressed synthetic public/private consumer checks и public generic CLI не заменяют полную hosted-CI или внешнюю private reachable-history release qualification.
