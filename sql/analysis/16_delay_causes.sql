-- Denominator is reported category minutes, not flight count or all delay time.
WITH cause_rows AS (
    SELECT category, minutes
    FROM analytics.flights
    CROSS JOIN LATERAL (VALUES
        ('Air carrier', carrier_delay_minutes), ('Weather', weather_delay_minutes),
        ('National aviation system', nas_delay_minutes), ('Security', security_delay_minutes),
        ('Late aircraft', late_aircraft_delay_minutes)
    ) AS causes(category, minutes)
    WHERE is_arrival_eligible AND arrival_delayed_15 AND has_reported_delay_causes
), grouped AS (
    SELECT category, sum(minutes)::BIGINT AS reported_delay_minutes,
        count(*) AS flights_with_complete_cause_reporting,
        count(*) FILTER (WHERE minutes > 0) AS flights_with_positive_category_minutes
    FROM cause_rows GROUP BY category
)
SELECT *, safe_rate(reported_delay_minutes, sum(reported_delay_minutes) OVER ()) AS share_of_reported_minutes
FROM grouped ORDER BY reported_delay_minutes DESC, category;
