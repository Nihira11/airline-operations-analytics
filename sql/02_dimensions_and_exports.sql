-- Dimensions are observed mappings from this source month, not external master data.
CREATE OR REPLACE TABLE analytics.dim_airports AS
SELECT DISTINCT OriginAirportID AS airport_id, Origin AS airport_code,
    OriginCityName AS city_name, OriginState AS state_code, OriginStateName AS state_name
FROM staging.source_flights
UNION
SELECT DISTINCT DestAirportID, Dest, DestCityName, DestState, DestStateName
FROM staging.source_flights;

CREATE OR REPLACE TABLE analytics.dim_airlines AS
SELECT DISTINCT DOT_ID_Reporting_Airline AS airline_id,
    Reporting_Airline AS reporting_airline, IATA_CODE_Reporting_Airline AS iata_code
FROM staging.source_flights;

CREATE OR REPLACE VIEW analytics.tableau_flights AS
-- Keep lineage and duplicate clock/calendar representations in the database,
-- so the dashboard export has a focused field list and a smaller file size.
SELECT f.flight_id, f.flight_date, f.reporting_airline, f.flight_number,
    f.origin_airport, f.destination_airport, f.route,
    f.scheduled_departure_local, f.scheduled_departure_hour, f.scheduled_arrival_local,
    f.scheduled_departure_is_2400, f.scheduled_arrival_is_2400,
    f.scheduled_elapsed_minutes, f.distance_miles,
    f.departure_delay_minutes, f.arrival_delay_minutes, f.positive_arrival_delay_minutes,
    f.operation_status, f.is_cancelled, f.is_diverted, f.is_arrival_eligible,
    f.arrival_delayed_15, f.has_reported_delay_causes,
    f.carrier_delay_minutes, f.weather_delay_minutes, f.nas_delay_minutes,
    f.security_delay_minutes, f.late_aircraft_delay_minutes, f.has_source_quality_issue,
    f.scheduled_flight_count, f.cancelled_flight_count, f.diverted_flight_count,
    f.eligible_arrival_count, f.on_time_arrival_count, f.delayed_arrival_count,
    origin.city_name AS origin_city, origin.state_code AS origin_state,
    destination.city_name AS destination_city, destination.state_code AS destination_state
FROM analytics.flights f
LEFT JOIN analytics.dim_airports origin ON f.origin_airport_id = origin.airport_id
LEFT JOIN analytics.dim_airports destination ON f.destination_airport_id = destination.airport_id;

-- Additive counts let Tableau calculate weighted rates correctly after filtering.
CREATE OR REPLACE VIEW analytics.daily_operations AS
SELECT flight_date, reporting_airline,
    sum(scheduled_flight_count) AS scheduled_flights,
    sum(cancelled_flight_count) AS cancelled_flights,
    sum(diverted_flight_count) AS diverted_flights,
    sum(eligible_arrival_count) AS eligible_arrivals,
    sum(on_time_arrival_count) AS on_time_arrivals,
    sum(delayed_arrival_count) AS delayed_arrivals,
    sum(positive_arrival_delay_minutes) AS positive_arrival_delay_minutes
FROM analytics.flights
GROUP BY flight_date, reporting_airline;
