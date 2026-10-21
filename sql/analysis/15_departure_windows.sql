SELECT day_of_week, scheduled_departure_hour,
    sum(scheduled_flight_count)::BIGINT AS scheduled_flights,
    sum(cancelled_flight_count)::BIGINT AS cancelled_flights,
    sum(eligible_arrival_count)::BIGINT AS eligible_arrivals,
    sum(on_time_arrival_count)::BIGINT AS on_time_arrivals,
    sum(delayed_arrival_count)::BIGINT AS delayed_arrivals,
    safe_rate(sum(on_time_arrival_count), sum(eligible_arrival_count)) AS arrival_on_time_rate,
    safe_rate(sum(cancelled_flight_count), sum(scheduled_flight_count)) AS cancellation_rate,
    sum(eligible_arrival_count) >= getvariable('minimum_window_flights') AS meets_arrival_volume_threshold
FROM analytics.flights
GROUP BY day_of_week, scheduled_departure_hour
ORDER BY day_of_week, scheduled_departure_hour;
