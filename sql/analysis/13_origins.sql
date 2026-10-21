WITH grouped AS (
    SELECT origin_airport AS airport, origin_airport_id AS airport_id,
        sum(scheduled_flight_count)::BIGINT AS scheduled_flights,
        sum(cancelled_flight_count)::BIGINT AS cancelled_flights,
        sum(eligible_arrival_count)::BIGINT AS eligible_arrivals,
        sum(on_time_arrival_count)::BIGINT AS on_time_arrivals,
        sum(delayed_arrival_count)::BIGINT AS delayed_arrivals,
        safe_rate(sum(on_time_arrival_count), sum(eligible_arrival_count)) AS arrival_on_time_rate,
        safe_rate(sum(cancelled_flight_count), sum(scheduled_flight_count)) AS cancellation_rate
    FROM analytics.flights GROUP BY origin_airport, origin_airport_id
)
SELECT grouped.*, dim.city_name,
    eligible_arrivals >= getvariable('minimum_origin_flights') AS meets_arrival_volume_threshold,
    scheduled_flights >= getvariable('minimum_origin_flights') AS meets_cancellation_volume_threshold
FROM grouped JOIN analytics.dim_airports dim USING (airport_id)
ORDER BY scheduled_flights DESC, airport;
