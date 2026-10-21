-- Quantify the coverage of the category chart separately from its minute shares.
SELECT sum(eligible_arrival_count)::BIGINT AS eligible_arrivals,
    sum(delayed_arrival_count)::BIGINT AS delayed_arrivals,
    count(*) FILTER (WHERE is_arrival_eligible AND arrival_delayed_15
        AND has_reported_delay_causes)::BIGINT AS delayed_arrivals_with_complete_causes,
    count(*) FILTER (WHERE is_arrival_eligible AND arrival_delayed_15
        AND NOT has_reported_delay_causes)::BIGINT AS delayed_arrivals_without_complete_causes,
    safe_rate(count(*) FILTER (WHERE is_arrival_eligible AND arrival_delayed_15
        AND has_reported_delay_causes), sum(delayed_arrival_count)) AS complete_cause_reporting_rate,
    sum(carrier_delay_minutes + weather_delay_minutes + nas_delay_minutes
        + security_delay_minutes + late_aircraft_delay_minutes)
        FILTER (WHERE is_arrival_eligible AND arrival_delayed_15
            AND has_reported_delay_causes)::BIGINT AS reported_category_minutes,
    sum(positive_arrival_delay_minutes) FILTER (WHERE arrival_delayed_15)::BIGINT
        AS total_delayed_arrival_minutes
FROM analytics.flights;
