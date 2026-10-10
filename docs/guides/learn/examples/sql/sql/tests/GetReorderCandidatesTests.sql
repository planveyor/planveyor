CREATE SCHEMA [GetReorderCandidatesTests] AUTHORIZATION [dbo];
GO

CREATE PROCEDURE
[GetReorderCandidatesTests].[test_positive_shortage_and_units_on_order]
AS
BEGIN
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
    VALUES (1, N'One', 12, 3, 4, 0), (2, N'Two', 9, 1, 2, 0);

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    INSERT INTO #Expected VALUES (1, N'One', 5), (2, N'Two', 6);
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE [GetReorderCandidatesTests].[test_equality_and_excess_excluded]
AS
BEGIN
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
    VALUES (1, N'Equal', 10, 5, 5, 0), (2, N'Excess', 10, 8, 5, 0);

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE
[GetReorderCandidatesTests].[test_discontinued_and_null_excluded]
AS
BEGIN
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
    VALUES (1, N'Active', 10, 2, 1, 0),
    (2, N'Discontinued', 10, 2, 1, 1),
    (3, N'Unknown', 10, 2, 1, NULL);

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    INSERT INTO #Expected VALUES (1, N'Active', 7);
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE [GetReorderCandidatesTests].[test_null_quantities_zero]
AS
BEGIN
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
    VALUES (1, N'NullReorder', NULL, 0, 0, 0),
    (2, N'NullStock', 7, NULL, 2, 0),
    (3, N'NullOrder', 7, 3, NULL, 0),
    (4, N'AllNull', NULL, NULL, NULL, 0);

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    INSERT INTO #Expected VALUES (2, N'NullStock', 5), (3, N'NullOrder', 4);
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE [GetReorderCandidatesTests].[test_empty_products]
AS
BEGIN
    EXEC [tSQLt].[FakeTable] @TableName = N'dbo.Products';

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE [GetReorderCandidatesTests].[test_productid_order_rows]
AS
BEGIN
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

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    INSERT INTO #Expected VALUES (10, N'Order10', 5),
    (20, N'Order20', 5),
    (30, N'Order30', 5);
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO

CREATE PROCEDURE
[GetReorderCandidatesTests].[test_smallint_boundary_int_arithmetic]
AS
BEGIN
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
    VALUES (1, N'UnderflowWithoutInt', 32767, -32768, -32768, 0),
    (2, N'OverflowWithoutInt', 32767, 32767, 32767, 0);

    CREATE TABLE #Actual (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    CREATE TABLE #Expected (
        [ProductID] INT, [ProductName] NVARCHAR(40), [Shortage] INT
    );
    INSERT INTO #Actual EXEC [dbo].[GetReorderCandidates];
    INSERT INTO #Expected VALUES (1, N'UnderflowWithoutInt', 98303);
    EXEC [tSQLt].[AssertEqualsTable]
        @Expected = N'#Expected', @Actual = N'#Actual';
END;
GO
