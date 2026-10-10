CREATE SCHEMA [SqlHarnessSmoke] AUTHORIZATION [dbo];
GO
CREATE PROCEDURE [SqlHarnessSmoke].[test_schema_present]
AS
BEGIN
    EXEC [tSQLt].[AssertObjectExists] @ObjectName = N'dbo.Products';
END;
GO
