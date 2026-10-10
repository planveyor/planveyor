# Учебный фрагмент исходника для чтения; не самостоятельный исполняемый тест.
# Source: scripts/test_sql.py
# Exact revision: f4f707b1c5e3bb303f24d641c451db8b5cec9cab
# Импорты, class и fixture helpers намеренно опущены.
# Тела методов сохранены; снят общий отступ class в четыре пробела.
# Этот снимок sibling не входит в core suite Planveyor.

# Original class: HarnessContractTests
# Original lines: 529–547
def test_exact_result_and_direct_client_order_parsers(self):
    output = fake_test_output()
    self.assertEqual(set(sql.parse_test_results(output)), set(sql.TEST_NAMES))
    self.assertEqual(sql.parse_order_rows(output), (10, 20, 30))
    marker = f"PV_TEST_RESULT|{sql.TEST_NAME}|Success"
    for changed in (output.replace(marker + "\n", "", 1),
                    output + marker + "\n",
                    output + "PV_TEST_RESULT|Other.test_extra|Success\n"):
        with self.assertRaises(sql.SqlHarnessError):
            sql.parse_test_results(changed)
    with self.assertRaisesRegex(sql.SqlHarnessError, "test_failure"):
        sql.parse_test_results(output.replace(marker, marker.replace("Success", "Failure")))
    for changed in (output.replace("PV_ORDER_BEGIN\n", ""),
                    output + "PV_ORDER_BEGIN\n",
                    output.replace("20|Order20|5", "30|Order20|5"),
                    output.replace("20|Order20|5\n", ""),
                    output.replace("20|Order20|5", "bad order row")):
        with self.assertRaises(sql.SqlHarnessError):
            sql.parse_order_rows(changed)

# Original class: HarnessContractTests
# Original lines: 660–689
def test_wrong_client_order_writes_red_junit_and_no_green_proof(self):
    captured = []
    class_queries = 0

    def fake_run(argv, **_kwargs):
        nonlocal class_queries
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return "a" * 40
        if argv[0] == "sqlcmd" and "-Q" in argv and "PV_CLASS|" in argv[-1]:
            class_queries += 1
            return fake_class_output("marked", "marked")
        if argv[0] == "sqlcmd" and "-i" in argv:
            return fake_test_output().replace("20|Order20|5", "30|Order20|5")
        return ""

    with patch.object(sql, "load_connection", return_value=FAKE), \
         patch.object(sql, "validate_schema"), \
         patch.object(sql.shutil, "which", return_value="/fake/sqlcmd"), \
         patch.object(sql, "current_proof_bytes", return_value={"fake": b"same"}), \
         patch.object(sql, "db_build"), patch.object(sql, "lint"), \
         patch.object(sql, "unique_file", return_value=Path("Northwind.Tests.dacpac")), \
         patch.object(sql, "local_environment", return_value={}), \
         patch.object(sql, "run_command", side_effect=fake_run), \
         patch.object(sql, "write_junit", side_effect=captured.append):
        with self.assertRaisesRegex(sql.SqlHarnessError, "order observer sequence mismatch"):
            sql.db_proof()
    self.assertEqual(class_queries, 3)
    self.assertEqual(len(captured), 1)
    self.assertFalse(sql.junit_matches(captured[0]))
    self.assertEqual(ET.fromstring(captured[0]).get("errors"), "1")
