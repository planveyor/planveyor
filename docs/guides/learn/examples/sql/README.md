# SQL example code snapshot

**English** · [Русский](README.ru.md)

This directory holds the procedure, the tests, and the harness of the historical SQL sibling in which the task from the [Running example: which products to reorder](../../sql-example.md) chapter was done. The files are attached so that you can read them next to the chapter. They do not run outside the sibling: they need the whole project, its local contract, a dedicated dev database, and access to it. The Planveyor tests do not run these files either. The live run of these files on the dev database took place on September 28, 2026, and the chapter describes it.

Project commit: `f4f707b1c5e3bb303f24d641c451db8b5cec9cab`.

The four SQL files and [scripts/sql.py](scripts/sql.py) are copied without changes. [test_sql_excerpt.py](test_sql_excerpt.py) holds only two methods from the project's `test_sql.py`, with their original line numbers; the imports, the class, and the test helper functions are left out. The plans, receipts, connection settings, and local settings of the project are not carried over here.
