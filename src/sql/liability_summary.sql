WITH ranked AS (
  SELECT
    asset,
    CAST(balance AS DECIMAL(38, 12)) AS balance,
    customer_id,
    NTILE(100) OVER (PARTITION BY asset ORDER BY CAST(balance AS DECIMAL(38, 12)) DESC) AS percentile_rank
  FROM ledger
)
SELECT
  asset,
  SUM(balance) AS total_balance,
  COUNT(DISTINCT customer_id) AS customer_count,
  SUM(CASE WHEN percentile_rank = 1 THEN balance ELSE 0 END) / NULLIF(SUM(balance), 0) AS top_1pct_share
FROM ranked
GROUP BY asset
ORDER BY asset;

