CREATE PROCEDURE [dbo].[GetReorderCandidates]
AS
BEGIN
    SET NOCOUNT ON;

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
END;
GO
