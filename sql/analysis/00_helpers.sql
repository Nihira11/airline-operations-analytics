CREATE OR REPLACE TEMP MACRO safe_rate(numerator, denominator) AS
    CAST(numerator AS DOUBLE) / NULLIF(denominator, 0);
