-- Pair-specific standardisation; scores from different pairs are not a league table.
-- Compare shared directional routes and four-hour local departure windows.
WITH strata AS (
    SELECT reporting_airline, route, floor(scheduled_departure_hour / 4)::INTEGER AS departure_block,
        sum(eligible_arrival_count)::BIGINT AS eligible_arrivals,
        sum(on_time_arrival_count)::BIGINT AS on_time_arrivals
    FROM analytics.flights GROUP BY reporting_airline, route, departure_block
    HAVING sum(eligible_arrival_count) >= getvariable('minimum_common_stratum_flights')
), pairs AS (
    SELECT a.reporting_airline AS airline_a, b.reporting_airline AS airline_b,
        a.route, a.departure_block, a.eligible_arrivals AS arrivals_a, b.eligible_arrivals AS arrivals_b,
        a.eligible_arrivals + b.eligible_arrivals AS pooled_weight,
        safe_rate(a.on_time_arrivals, a.eligible_arrivals) AS rate_a,
        safe_rate(b.on_time_arrivals, b.eligible_arrivals) AS rate_b
    FROM strata a JOIN strata b USING (route, departure_block)
    WHERE a.reporting_airline < b.reporting_airline
), scores AS (
    SELECT airline_a, airline_b, count(*) AS matched_strata, count(DISTINCT route) AS matched_routes,
        sum(arrivals_a)::BIGINT AS matched_arrivals_a, sum(arrivals_b)::BIGINT AS matched_arrivals_b,
        safe_rate(sum(pooled_weight * rate_a), sum(pooled_weight)) AS standardised_on_time_rate_a,
        safe_rate(sum(pooled_weight * rate_b), sum(pooled_weight)) AS standardised_on_time_rate_b
    FROM pairs GROUP BY airline_a, airline_b
), totals AS (
    SELECT reporting_airline, sum(eligible_arrival_count) AS eligible_arrivals,
        safe_rate(sum(on_time_arrival_count), sum(eligible_arrival_count)) AS raw_on_time_rate
    FROM analytics.flights GROUP BY reporting_airline
)
SELECT scores.*, a.raw_on_time_rate AS raw_on_time_rate_a, b.raw_on_time_rate AS raw_on_time_rate_b,
    safe_rate(matched_arrivals_a, a.eligible_arrivals) AS coverage_a,
    safe_rate(matched_arrivals_b, b.eligible_arrivals) AS coverage_b,
    standardised_on_time_rate_a - standardised_on_time_rate_b AS standardised_gap_a_minus_b,
    a.raw_on_time_rate - b.raw_on_time_rate AS raw_gap_a_minus_b,
    matched_strata >= getvariable('minimum_matched_strata')
        AND least(matched_arrivals_a, matched_arrivals_b) >= getvariable('minimum_matched_arrivals')
        AS meets_comparison_threshold
FROM scores JOIN totals a ON scores.airline_a = a.reporting_airline
JOIN totals b ON scores.airline_b = b.reporting_airline
ORDER BY matched_arrivals_a + matched_arrivals_b DESC, airline_a, airline_b;
