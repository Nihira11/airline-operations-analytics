SELECT reporting_airline, sum(scheduled_flight_count)::BIGINT AS scheduled_flights,
    sum(cancelled_flight_count)::BIGINT AS cancelled_flights,
    sum(eligible_arrival_count)::BIGINT AS eligible_arrivals,
    sum(on_time_arrival_count)::BIGINT AS on_time_arrivals,
    sum(delayed_arrival_count)::BIGINT AS delayed_arrivals,
    safe_rate(sum(on_time_arrival_count), sum(eligible_arrival_count)) AS arrival_on_time_rate,
    safe_rate(sum(cancelled_flight_count), sum(scheduled_flight_count)) AS cancellation_rate,
    avg(positive_arrival_delay_minutes) AS average_positive_arrival_delay_minutes,
    quantile_cont(arrival_delay_minutes, 0.9) FILTER (WHERE arrival_delayed_15) AS p90_delayed_arrival_minutes
FROM analytics.flights
GROUP BY reporting_airline ORDER BY scheduled_flights DESC, reporting_airline;
