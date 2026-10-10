-- Run only the two authored classes; print each result before the next Run.
SET NOCOUNT ON;
EXEC [tSQLt].[Run] @TestName = N'SqlHarnessSmoke';
SELECT N'PV_TEST_RESULT|' + [Class] + N'.' + [TestCase] + N'|' + [Result]
FROM [tSQLt].[TestResult]
WHERE [Class] = N'SqlHarnessSmoke'
ORDER BY [TestCase];

EXEC [tSQLt].[Run] @TestName = N'GetReorderCandidatesTests';
SELECT N'PV_TEST_RESULT|' + [Class] + N'.' + [TestCase] + N'|' + [Result]
FROM [tSQLt].[TestResult]
WHERE [Class] = N'GetReorderCandidatesTests'
ORDER BY [TestCase];

-- Observe the procedure's row order inside a rollback-only fixture.
BEGIN TRY
    BEGIN TRANSACTION;
    EXEC [tSQLt].[FakeTable] @TableName = N'dbo.Products';
    INSERT INTO [dbo].[Products]
    (
        [ProductID],
        [ProductName],
        [ReorderLevel],
        [UnitsInStock],
        [UnitsOnOrder],
        [Discontinued]
    )
    VALUES (30, N'Order30', 5, 0, 0, 0),
    (10, N'Order10', 5, 0, 0, 0),
    (20, N'Order20', 5, 0, 0, 0);

    SELECT N'PV_ORDER_BEGIN';
    EXEC [dbo].[GetReorderCandidates];
    SELECT N'PV_ORDER_END';
    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
