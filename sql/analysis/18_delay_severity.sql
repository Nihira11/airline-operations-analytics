-- Mutually exclusive bands over eligible arrivals; signed early arrivals are retained.
WITH banded AS (
    SELECT CASE WHEN arrival_delay_minutes < 0 THEN 1
                WHEN arrival_delay_minutes < 15 THEN 2
                WHEN arrival_delay_minutes < 30 THEN 3
                WHEN arrival_delay_minutes < 60 THEN 4
                WHEN arrival_delay_minutes < 120 THEN 5 ELSE 6 END AS band_order,
        delayed_arrival_count
    FROM analytics.flights WHERE is_arrival_eligible
), counts AS (
    SELECT band_order, count(*)::BIGINT AS eligible_arrivals,
        sum(delayed_arrival_count)::BIGINT AS delayed_arrivals
    FROM banded GROUP BY band_order
)
SELECT band_order,
    CASE band_order WHEN 1 THEN 'Early (<0 min)' WHEN 2 THEN '0-14 min'
        WHEN 3 THEN '15-29 min' WHEN 4 THEN '30-59 min'
        WHEN 5 THEN '60-119 min' WHEN 6 THEN '120+ min' END AS arrival_delay_band,
    eligible_arrivals, delayed_arrivals,
    safe_rate(eligible_arrivals, sum(eligible_arrivals) OVER ()) AS share_of_eligible_arrivals,
    safe_rate(delayed_arrivals, sum(delayed_arrivals) OVER ()) AS share_of_delayed_arrivals
FROM counts ORDER BY band_order;
