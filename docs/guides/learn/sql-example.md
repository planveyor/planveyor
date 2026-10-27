# Running example: which products to reorder

**English** · [Русский](sql-example.ru.md)

The roles solved the task “which products to reorder” on September 28, 2026, in a [sibling](glossary.md) on SQL Server. Other chapters take separate examples from it; here it is covered in full: the rule and the data; the procedure and the tests; the records in the plan, the code draft, and the review; the live run on the dev database. The [Roles and task files](roles-artifacts.md) chapter tells who did what and how long it took.

## The task and the rule

The task needs a list of active products that are short in stock even with the delivery already on order. The `dbo.GetReorderCandidates` procedure reads the `dbo.Products` table and returns three columns: `ProductID`, `ProductName`, and the shortage `Shortage`. The procedure itself does not place orders or change stock levels.

| Column | Type in the schema | What it holds |
| --- | --- | --- |
| `ProductID` | `INT NOT NULL` | Product identifier |
| `ProductName` | `NVARCHAR(40) NOT NULL` | Name |
| `ReorderLevel` | `SMALLINT NULL` | Reorder level |
| `UnitsInStock` | `SMALLINT NULL` | In stock |
| `UnitsOnOrder` | `SMALLINT NULL` | On order, delivery expected |
| `Discontinued` | `BIT NOT NULL` | `0`: the product is active; `1`: the product is discontinued |

The rule from the Owner assignment:

- the shortage is `Shortage = ReorderLevel - (UnitsInStock + UnitsOnOrder)`;
- the result includes products with `Discontinued = 0` and `Shortage > 0`;
- `NULL` in any of the three quantities counts as zero;
- each quantity is cast to `INT` before addition and subtraction;
- the rows go in ascending order of `ProductID`.

The quantities are stored as `SMALLINT`, and the sum of two such numbers can go beyond the range of the type. That is why they are cast to `INT`.

The assignment also set limits: extend the project harness, that is, its scripts for building and running tests, minimally and without a new framework; do not extract the database schema again; keep secrets local. An operator did the live run on the dev database (see [Roles and task files](roles-artifacts.md)).

Architect carried the rule over into the plan. The first two items of the decisions section, as written in the project, in Russian:

```markdown
## Decisions (final)
- Результат только для `Discontinued = 0`; `NULL` в fake-колонке исключён равенством, не трактуется
  как active. Количественные `NULL` равны нулю; приведение к `INT` происходит до арифметики, чтобы
  сложение двух `SMALLINT` не переполнялось.
- Порядок доказывает последовательность строк прямого клиентского вывода процедуры на синтетическом
  FakeTable, а не табличный equality assertion. Контент доказывают tSQLt cases; единственный итоговый
  rc и JUnit учитывают оба вида проверки.
[…]
```

The first item repeats the rule and adds a detail: a row with `NULL` in `Discontinued` does not get into the result. In the real table, this column is `NOT NULL`, so such a row occurs only in tests. The second item says how to check the row order: with a separate call of the procedure, described below.

Coder wrote the procedure as one query. Here it is from [GetReorderCandidates.sql](examples/sql/sql/Northwind/GetReorderCandidates.sql), without the `CREATE PROCEDURE` wrapper:

```sql
SELECT
    [Products].[ProductID],
    [Products].[ProductName],
    [Calculated].[Shortage]
FROM [dbo].[Products] AS [Products]
CROSS APPLY (
    VALUES (
        CAST(COALESCE([Products].[ReorderLevel], 0) AS INT)
        - (
            CAST(COALESCE([Products].[UnitsInStock], 0) AS INT)
            + CAST(COALESCE([Products].[UnitsOnOrder], 0) AS INT)
        )
    )
) AS [Calculated] ([Shortage])
WHERE
    [Products].[Discontinued] = 0
    AND [Calculated].[Shortage] > 0
ORDER BY [Products].[ProductID];
```

Each quantity first goes through `COALESCE(..., 0)`, then through `CAST(... AS INT)`, and only then does the arithmetic start. The shortage is computed once in `CROSS APPLY`, and `WHERE` filters the ready column. A row with `NULL` in `Discontinued` does not pass the `= 0` condition and is filtered out.

![The path of a row through the procedure: `NULL` in the quantities becomes zero, the quantities are cast to `INT` and give the shortage, active products with a shortage above zero remain, and the rows are sorted by `ProductID`](assets/sql-example-1.svg)

## Data and tests

The tests are written in tSQLt, a unit testing library for SQL Server. In tSQLt, each test is a stored procedure, and the tests of one class live in a separate database schema. A marker makes a schema a class: the `tSQLt.TestClass` extended property. Each of the seven tests of the procedure starts with a call of `tSQLt.FakeTable`: for the duration of the test, `dbo.Products` is replaced with an empty copy without constraints. The test works only with the rows it put there itself and does not read the real data.

The first test, `test_positive_shortage_and_units_on_order`, puts in two rows. `One` and `Two` are the names of synthetic products:

| `ProductID` | `ProductName` | `ReorderLevel` | `UnitsInStock` | `UnitsOnOrder` | `Discontinued` |
| --- | --- | --- | --- | --- | --- |
| 1 | `One` | 12 | 3 | 4 | 0 |
| 2 | `Two` | 9 | 1 | 2 | 0 |

`One` has 3 in stock and 4 on order: 7 of 12 are covered, and the shortage is 12 − (3 + 4) = 5. For `Two`, the shortage is 9 − (1 + 2) = 6. The end of the test:

```sql
INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
INSERT INTO #Expected VALUES (1, N'One', 5), (2, N'Two', 6);
EXEC [tSQLt].[AssertEqualsTable]
    @Expected = N'#Expected', @Actual = N'#Actual';
```

The test calls the procedure and puts its rows into the temporary table `#Actual`, and `tSQLt.AssertEqualsTable` compares them with the expected rows from `#Expected`.

All seven tests of the `GetReorderCandidatesTests` class are in [GetReorderCandidatesTests.sql](examples/sql/sql/tests/GetReorderCandidatesTests.sql). The input is written with slashes: `ReorderLevel / UnitsInStock / UnitsOnOrder / Discontinued`.

| Test | Input | Expected result |
| --- | --- | --- |
| `test_positive_shortage_and_units_on_order` | `One`: `12 / 3 / 4 / 0`; `Two`: `9 / 1 / 2 / 0` | `(1, One, 5)`, `(2, Two, 6)` |
| `test_equality_and_excess_excluded` | `Equal`: `10 / 5 / 5 / 0`; `Excess`: `10 / 8 / 5 / 0` | Empty: the shortage is 0 and −3 |
| `test_discontinued_and_null_excluded` | `Active`, `Discontinued`, `Unknown`: `10 / 2 / 1`, with `0`, `1`, and `NULL` in `Discontinued` respectively | Only `(1, Active, 7)` |
| `test_null_quantities_zero` | `NullReorder`: `NULL / 0 / 0 / 0`; `NullStock`: `7 / NULL / 2 / 0`; `NullOrder`: `7 / 3 / NULL / 0`; `AllNull`: `NULL / NULL / NULL / 0` | `(2, NullStock, 5)`, `(3, NullOrder, 4)` |
| `test_empty_products` | No rows | Empty |
| `test_productid_order_rows` | `Order30`, `Order10`, `Order20` with IDs 30, 10, 20: `5 / 0 / 0 / 0` | `(10, Order10, 5)`, `(20, Order20, 5)`, `(30, Order30, 5)`; the set of rows is checked |
| `test_smallint_boundary_int_arithmetic` | `UnderflowWithoutInt`: `32767 / -32768 / -32768 / 0`; `OverflowWithoutInt`: `32767 / 32767 / 32767 / 0` | Only `(1, UnderflowWithoutInt, 98303)`; the second row has a shortage of −32767 |

The negative stock values in the last test are artificial: in the real table, the quantities have a “not less than zero” constraint, and the fake table does not inherit it. The test is there for the arithmetic: without the cast to `INT`, the sum of stock and order, −65,536 in the first row and 65,534 in the second, would not fit into `SMALLINT`.

A table comparison does not see the order of rows: `tSQLt.AssertEqualsTable` compares only the set of rows. So `test_productid_order_rows` checks which rows came back, and a direct call of the procedure in [run-tests.sql](examples/sql/sql/tests/run-tests.sql) is responsible for the order. This script runs the two test classes and prints their results after each one. Then it opens a transaction, replaces the table with a fake, puts in products with IDs 30, 10, 20, prints the `PV_ORDER_BEGIN` marker, calls the procedure, prints `PV_ORDER_END`, and rolls back the transaction. The harness takes the rows between the markers and requires exactly these: `(10, Order10, 5)`, `(20, Order20, 5)`, `(30, Order30, 5)`. The names `Order10`, `Order20`, `Order30` go in the same alphabetical order as the IDs, so this check cannot tell sorting by name from sorting by `ProductID`.

The report of the live run has eight tests. Seven of them are the `GetReorderCandidatesTests` class. The eighth, `SqlHarnessSmoke.test_schema_present`, remains from the first task of the project, the adaptation to SQL Server, and checks that the `dbo.Products` table exists. The order check is not one of these eight; it is a separate condition of the same run. The harness writes a green report only when both the tests and the order check have passed.

## What the plan and the code draft say

Architect and Planner wrote down the rule and the checks before the code. The excerpts are quoted as written in the project, in Russian, and in their final form, after acceptance: the `[x]` marks and the record of the red run appeared later. Long lines in the excerpts are wrapped, omissions are marked with `[…]`, and an internal run step number is replaced with the words “прошлой задачи” (of the previous task).

The plan has six acceptance criteria. Below are the first five; the sixth is about the commit of the plan's exact bundle.

```markdown
## Acceptance criteria / DoD
- [x] Для синтетических `Products` возвращаются только active rows с `Shortage > 0`; поля и тип строго
  `ProductID`, `ProductName`, `Shortage INT`, сортировка `ProductID`.
- [x] `NULL` во всех количественных колонках эквивалентен нулю; `Discontinued NULL` не active; каждое
  количество приведено к `INT` до арифметики; smallint-boundary case выполняется без overflow.
- [x] Семь содержательных tSQLt/FakeTable cases и сохранённый smoke выполняются exact runner; прямой
  клиентский order observer реально видит `10,20,30` при seed `30,10,20`; при неверном порядке итоговый
  rc/JUnit не green.
- [x] Публикация/запуск ограничены выделенной dev-базой и двумя authored classes; никаких `RunAll`,
  `NewTestClass`, чужого удаления, SQL/credential leak.
- [x] Offline build, полный SQLFluff lint authored files, safe Python fakes и свежий успешный live
  `make db-proof` имеют фактические rc; current JUnit соответствует ровно 8 tests, каждому
  имени/результату и дополнительному order gate. Первый live attempt был RED до Publish/Run; оба факта
  сохранены в Evidence.
[…]
```

The first two criteria repeat the rule, and the other three are about the run: a wrong row order must give a red result, publishing is allowed only to the dedicated dev database, only the project's own two test classes may be run, and each check records the exit code of a real run. The last criterion also notes that the first live run was red.

The plan names the tests one by one:

```markdown
### Что написать / поправить
- `sql/tests/GetReorderCandidatesTests.sql`: семь именованных tSQLt tests —
  `test_positive_shortage_and_units_on_order`, `test_equality_and_excess_excluded`,
  `test_discontinued_and_null_excluded`, `test_null_quantities_zero`, `test_empty_products`,
  `test_productid_order_rows`, `test_smallint_boundary_int_arithmetic`. Каждый изолирует `dbo.Products`
  через FakeTable и проверяет содержимое/точные значения; order rows test сверяет состав, прямой
  observer ниже — последовательность.
- `sql/tests/run-tests.sql`: explicit `tSQLt.Run` только для `SqlHarnessSmoke` и
  `GetReorderCandidatesTests`; exact result projection для 8 names. Затем под контролируемой
  транзакцией FakeTable со seed 30/10/20, прямой вывод `EXEC dbo.GetReorderCandidates` и rollback даже
  при ошибке; output можно отличить от result markers без чтения real rows.
- `scripts/test_sql.py`: safe fake checks missing/duplicate/extra/failed test, обе class collisions,
  order missing/duplicate/wrong order, JUnit 8 cases/failure, current code draft paths и byte drift.
  Никаких подключений к серверу в unit tests.
```

Coder later wrote the same eight names into the harness, and the harness will not accept a run with a different set of tests.

Planner wrote the code draft. It has 16 target files. Coder changes six of them, including the README and the two new SQL files; the other ten are existing files that the check depends on. All of them except the README are the 15 code and configuration files: the harness and Reviewer later compare their contents. There are four steps:

1. Coder replaces the stubs of the two new SQL files, changes only the six files, and runs the harness tests without a database.
2. Coder checks the offline build, the linter, and that the files contain no secrets.
3. The operator checks the harness commands and runs `make db-proof` once on the dedicated dev database.
4. Reviewer verifies the 16 target files, the exit code, the row order, and the JUnit report.

A separate section of the draft lists traps, that is, cases where a check turns green without proving anything:

```markdown
## Critical invariants / traps / bypass paths
- `Invariant`: content cases не заменяют order proof. `Trap`: `AssertEqualsTable` или `INSERT ... EXEC`
  green при неверной последовательности. `Bypass path`: прямой sqlcmd output/markers и outer rc/JUnit.
- `Invariant`: tSQLt execution ограничен двумя marked classes. `Trap`: тесты в БД с теми же именами или
  `RunAll`. `Bypass path`: preflight class inventory и source test set против фактического JUnit.
- `Invariant`: proof относится к текущим bytes и designated dev DB. `Trap`: reuse JUnit прошлой задачи
  или success text после source drift. `Bypass path`: source commit, 16 target paths, two-class
  inventory, current asset и actual rc.
```

For each trap, the draft records what closes it: the direct output of the procedure between the markers, the check of the classes in the database before the run, and the comparison of the commit and the files. The class check is what stopped the first live run.

## The harness and the live run

The tSQLt tests run in the database itself. The project harness runs them: the [sql.py](examples/sql/scripts/sql.py) script, which the `make` targets call. The `make db-proof` command, in order:

1. Reads the connection settings from `.env.local` and checks the test sources and the run script: the tests have exactly the eight expected names, and the script calls only the two classes and the order check.
2. Remembers the contents of the 15 code and configuration files, rebuilds both database projects, the schema and the tests, runs the SQLFluff linter, and remembers the commit.
3. Queries the dev database about the two test classes. A missing class appears with the publication, a class with the marker passes on, and a class without the marker stops the run before the publication. An extraneous procedure in the schema of a class also stops it: the schema must hold exactly the expected tests.
4. Publishes the built schema package with the tests (DACPAC) to the dev database with two settings: do not drop objects, and do not drop extended properties that are not in the sources. The second setting was added after the first live run; more on it below. Puts the marker on the new classes and checks both classes again.
5. Runs `run-tests.sql` and accepts the result only if all eight tests succeed and the rows come in the order 10, 20, 30.
6. At the end, writes a green JUnit report, reads it back, and compares the commit, the files, and the set of tests with those remembered in step 2. If a comparison detects a mismatch, it replaces the report with a red one. A readback error can leave the earlier green report in place; the command still exits with a nonzero code on any error. Check the exit code and the current files together with the report.

Before the live run, Coder ran the checks that need no database, and all of them passed: 40 of 40 harness tests in `test_sql.py`, the offline build, the linter, and the secrets check. Instead of SQL Server answers, the harness tests substitute prepared text: for example, that both classes are in place and marked, and that the rows came in the wrong order 10, 30, 30. This way the tests make sure that the harness parses the answers correctly and refuses when it should.

The operator started the first live `make db-proof` after the handoff from Coder, and the run stopped after 5 seconds. The build and the linter passed, but the harness refused at the class check:

```text
db-proof: dev test class state is ambiguous
make: *** [db-proof] Error 1
```

The harness script exited with code 1, hence `Error 1`, and `make` itself returned 2. The JUnit report had no tests and one error. There was no publication, and none of the eight tests ran. The operator inspected the database without changing anything in it. The `SqlHarnessSmoke` class was in place and turned out to be the project's own: it had exactly one test, `test_schema_present`, and its text matched the source except for whitespace. Only the marker was missing.

The offline tests could not catch this. They did check the refusal on a class without the marker, and in the database the harness refused in exactly the same way. But a test without a database does not know whether the class in the real database has the marker: in such a test, the test itself sets the state of the class. The harness puts the marker on after publication; the sources do not have it. Probably one of the earlier publications removed it: in DacFx, the schema publication tool, the `DropExtendedPropertiesNotInSource` setting is on by default.

Coder added `/p:DropExtendedPropertiesNotInSource=false` to the publication, and now the harness tests require this flag to appear exactly once and with the value `false`. The operator restored the marker only on the `SqlHarnessSmoke` class and started the run again: under the plan, a red result is fixed in the usual way, and then the run is repeated. The second run passed in 13 seconds. The operator recorded it in the receipt `operator-validation.md`: the command, the time, the exit code, the file checksums, and the output. The output ends with the line:

```text
db-proof: source_commit=60332b46eba26a9c09cf199184c45afe10e61f1b; current classes/results/order verified; actual_rc=0
```

The exit code was 0, the JUnit report had 8 tests of 8 without errors, and the rows came in the order 10, 20, 30. The class checks before and after publication passed, and the files did not change during the run. `60332b4` in the output is the commit the project was at before the task.

## What Reviewer recorded

Reviewer checked the result in two lanes and had no findings. Reviewer did not run SQL itself but compared the checksums of the 15 code and configuration files with the operator receipt, and all of them matched. The risk lane record is examined in the [Review and acceptance](review-acceptance.md#how-it-went-the-getreordercandidates-review) chapter.

## Code snapshot in `examples/sql/`

The code of the task is attached to the learning section. The snapshot is taken from commit `f4f707b`, the last one in the history of the same sibling. Five of the six files of the snapshot are copies of project files: they match the task commit `70526ee` byte for byte, and their checksums match the ones recorded in the receipt of the green run.

- [GetReorderCandidates.sql](examples/sql/sql/Northwind/GetReorderCandidates.sql): the procedure.
- [GetReorderCandidatesTests.sql](examples/sql/sql/tests/GetReorderCandidatesTests.sql): seven tests.
- [SqlHarnessSmoke.sql](examples/sql/sql/tests/SqlHarnessSmoke.sql): the eighth test, which checks that the `dbo.Products` table exists.
- [run-tests.sql](examples/sql/sql/tests/run-tests.sql): runs the two classes and checks the order.
- [sql.py](examples/sql/scripts/sql.py): the harness, with the `make` targets from `setup` to `db-proof`.
- [test_sql_excerpt.py](examples/sql/test_sql_excerpt.py): two of the 40 harness tests, on parsing the results and the row order and on a red report for a wrong order. This is an excerpt; it does not run on its own.

The snapshot contains no plans, receipts, connection settings, or local configuration. Its origin is recorded in the [snapshot README](examples/sql/README.md).

## What Owner does

Today Owner runs such a task with the `planveyor sibling` commands. During the sibling adaptation, Owner agrees on who runs the live commands of the project, in the “Кто запускает живые цели” (who runs the live targets) section of the [stack brief](../../_template_stack_brief.md) (in Russian), the file with the decisions about the stack. There are two variants: the roles run such commands themselves from a sandbox with network access, or only a person runs them. In the second case:

1. Run the plan. By the role rules, Coder then stops at `In progress` with the exact command, in this example `make db-proof`. In TUI mode, such a stop is meant to reach you in the Manager window; in manual console mode, `planveyor sibling run` drives the task up to it.
2. Run this command yourself. The harness reads the connection settings itself from `.env.local` with mode 0600. You fill in this file in a local editor; secrets do not go into the agent harness chat, the plan, or the reports.
3. Return to the role the exit code, the path to the report, and the error text without secrets: in TUI mode, as an answer in the Manager window; in manual console mode, through `planveyor sibling answer`. For details, see the [Run the plan](../stack-sibling.md#run-the-plan) section of the stack sibling guide.
4. On a red result, the work returns to Coder. After the fix, a new run is needed: the earlier result does not apply to the changed files.

An administrator prepares the dev database. The stack brief requires the harness to check a positive marker of the designated dev database before the first write. The harness of this example checks less: it only blocks publication to the system databases and to `Northwind` itself.

## Common mistakes

- Treating a table comparison as an order check. `tSQLt.AssertEqualsTable` sees only the set of rows.
- Treating 40 green harness tests as evidence that the procedure works on SQL Server. They check the harness itself on substituted database answers.
- Counting a green run after the files were edited. It is tied to the commit and to the contents of the 15 code and configuration files.
- Working around a harness stop by weakening the check or by editing the database without analysis. In the example, the check stayed strict, and the marker was restored only on the project's own class, after it was compared with the source.

## This task in other chapters

- [The plan and its statuses](plan-lifecycle.md): how the status of this plan passed from role to role.
- [Review and acceptance](review-acceptance.md): the two Reviewer lanes and Architect acceptance.
- [Task closeout](closeout.md): what happened after acceptance, the commit and the docs closeout.
- [Tests and evidence](testing-evidence.md): what you can trust at each level, from the harness tests to the live run.

The functions and tests discussed here are in the [code map](code-map.md#running-example-which-products-to-reorder).

Next: [The plan and its statuses](plan-lifecycle.md).
