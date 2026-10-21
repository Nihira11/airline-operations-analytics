-- Every query returns a count of violations. All must be zero before export.
SELECT 'missing_required_identity_or_schedule' AS check_name, count(*) AS violations
FROM analytics.flights WHERE flight_date IS NULL OR reporting_airline IS NULL
    OR airline_id IS NULL OR flight_number IS NULL OR origin_airport_id IS NULL
    OR destination_airport_id IS NULL OR origin_airport IS NULL OR destination_airport IS NULL
    OR scheduled_departure_hhmm IS NULL OR scheduled_arrival_hhmm IS NULL
    OR scheduled_elapsed_minutes IS NULL OR distance_miles IS NULL
    OR is_cancelled IS NULL OR is_diverted IS NULL
UNION ALL
SELECT 'calendar_mismatch', count(*) FROM analytics.flights
WHERE flight_year IS DISTINCT FROM year(flight_date)
    OR flight_quarter IS DISTINCT FROM quarter(flight_date)
    OR flight_month IS DISTINCT FROM month(flight_date)
    OR day_of_month IS DISTINCT FROM day(flight_date)
    OR day_of_week IS DISTINCT FROM isodow(flight_date)
UNION ALL
SELECT 'invalid_core_codes_or_identifiers', count(*) FROM analytics.flights
WHERE NOT regexp_full_match(origin_airport, '[A-Z]{3}')
    OR NOT regexp_full_match(destination_airport, '[A-Z]{3}')
    OR NOT regexp_full_match(flight_number, '[0-9]{1,4}')
    OR airline_id <= 0 OR origin_airport_id <= 0 OR destination_airport_id <= 0
UNION ALL
SELECT 'invalid_cancel_code', count(*) FROM analytics.flights
WHERE (is_cancelled AND (cancellation_code IS NULL OR cancellation_code NOT IN ('A', 'B', 'C', 'D')))
    OR (NOT is_cancelled AND cancellation_code IS NOT NULL)
UNION ALL
SELECT 'overlapping_cancelled_and_diverted', count(*) FROM analytics.flights
WHERE is_cancelled AND is_diverted
UNION ALL
SELECT 'completed_missing_arrival_outcome', count(*) FROM analytics.flights
WHERE NOT is_cancelled AND NOT is_diverted AND arrival_delay_minutes IS NULL
UNION ALL
SELECT 'ineligible_has_prediction_label', count(*) FROM analytics.flights
WHERE NOT is_arrival_eligible AND arrival_delayed_15 IS NOT NULL
UNION ALL
SELECT 'eligible_missing_or_wrong_prediction_label', count(*) FROM analytics.flights
WHERE is_arrival_eligible AND arrival_delayed_15 IS DISTINCT FROM (arrival_delay_minutes >= 15)
UNION ALL
SELECT 'arrival_count_partition', count(*) FROM analytics.flights
WHERE eligible_arrival_count != on_time_arrival_count + delayed_arrival_count
    OR on_time_arrival_count IS NULL OR delayed_arrival_count IS NULL
UNION ALL
SELECT 'duplicate_flight_id', count(*) - count(DISTINCT flight_id) FROM analytics.flights
UNION ALL
SELECT 'airport_dimension_key_conflicts', count(*) FROM (
    SELECT airport_id FROM analytics.dim_airports GROUP BY airport_id HAVING count(*) > 1
)
UNION ALL
SELECT 'airline_dimension_key_conflicts', count(*) FROM (
    SELECT airline_id FROM analytics.dim_airlines GROUP BY airline_id HAVING count(*) > 1
)
UNION ALL
SELECT 'missing_airline_dimension_join', count(*) FROM analytics.flights f
LEFT JOIN analytics.dim_airlines a USING (airline_id)
WHERE a.airline_id IS NULL OR f.reporting_airline IS DISTINCT FROM a.reporting_airline
UNION ALL
SELECT 'missing_airport_dimension_join', count(*) FROM analytics.tableau_flights
WHERE origin_city IS NULL OR destination_city IS NULL OR origin_state IS NULL OR destination_state IS NULL
UNION ALL
SELECT 'source_delay_indicator_mismatch', count(*) FROM staging.source_flights
WHERE (NOT Cancelled AND NOT Diverted AND ArrDelay IS NOT NULL
       AND ArrDel15 IS DISTINCT FROM (ArrDelay >= 15))
    OR (DepDelay IS NOT NULL AND DepDel15 IS DISTINCT FROM (DepDelay >= 15))
UNION ALL
SELECT 'source_clipped_delay_mismatch', count(*) FROM staging.source_flights
WHERE (ArrDelay IS NOT NULL AND ArrDelayMinutes IS DISTINCT FROM greatest(ArrDelay, 0))
    OR (DepDelay IS NOT NULL AND DepDelayMinutes IS DISTINCT FROM greatest(DepDelay, 0))
UNION ALL
SELECT 'invalid_source_flight_count', count(*) FROM staging.source_flights
WHERE Flights IS DISTINCT FROM 1
UNION ALL
SELECT 'negative_core_measure', count(*) FROM analytics.flights
WHERE scheduled_elapsed_minutes < 0 OR actual_elapsed_minutes < 0 OR air_time_minutes < 0
    OR distance_miles < 0 OR carrier_delay_minutes < 0 OR weather_delay_minutes < 0
    OR nas_delay_minutes < 0 OR security_delay_minutes < 0 OR late_aircraft_delay_minutes < 0;
