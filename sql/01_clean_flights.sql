-- One row per reported flight. Source clock strings are retained for audit.
-- TIME values describe local clock time only; no UTC/date arithmetic is implied.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE MACRO local_clock(hhmm) AS (
    CASE WHEN hhmm = '2400' THEN TIME '00:00:00'
         ELSE CAST(substr(hhmm, 1, 2) || ':' || substr(hhmm, 3, 2) || ':00' AS TIME)
    END
);

CREATE OR REPLACE TABLE analytics.flights AS
WITH typed AS (
    SELECT
        sha256(concat_ws('|', CAST(FlightDate AS VARCHAR), Reporting_Airline,
            Flight_Number_Reporting_Airline, CAST(OriginAirportID AS VARCHAR),
            CAST(DestAirportID AS VARCHAR), CRSDepTime)) AS flight_id,
        source_record_number,
        source_file,
        source_record_number IN (SELECT source_record_number FROM staging.source_quality_issues)
            AS has_source_quality_issue,
        FlightDate AS flight_date,
        Year AS flight_year,
        Quarter AS flight_quarter,
        Month AS flight_month,
        DayofMonth AS day_of_month,
        DayOfWeek AS day_of_week,
        Reporting_Airline AS reporting_airline,
        DOT_ID_Reporting_Airline AS airline_id,
        Flight_Number_Reporting_Airline AS flight_number,
        Tail_Number AS tail_number,
        OriginAirportID AS origin_airport_id,
        DestAirportID AS destination_airport_id,
        Origin AS origin_airport,
        Dest AS destination_airport,
        Origin || '-' || Dest AS route,
        CRSDepTime AS scheduled_departure_hhmm,
        CRSArrTime AS scheduled_arrival_hhmm,
        DepTime AS actual_departure_hhmm,
        ArrTime AS actual_arrival_hhmm,
        local_clock(CRSDepTime) AS scheduled_departure_local,
        local_clock(CRSArrTime) AS scheduled_arrival_local,
        local_clock(DepTime) AS actual_departure_local,
        local_clock(ArrTime) AS actual_arrival_local,
        CRSDepTime = '2400' AS scheduled_departure_is_2400,
        CRSArrTime = '2400' AS scheduled_arrival_is_2400,
        CAST(date_part('hour', local_clock(CRSDepTime)) AS INTEGER) AS scheduled_departure_hour,
        CRSElapsedTime AS scheduled_elapsed_minutes,
        ActualElapsedTime AS actual_elapsed_minutes,
        AirTime AS air_time_minutes,
        Distance AS distance_miles,
        DepDelay AS departure_delay_minutes,
        ArrDelay AS arrival_delay_minutes,
        Cancelled AS is_cancelled,
        CancellationCode AS cancellation_code,
        Diverted AS is_diverted,
        CarrierDelay AS carrier_delay_minutes,
        WeatherDelay AS weather_delay_minutes,
        NASDelay AS nas_delay_minutes,
        SecurityDelay AS security_delay_minutes,
        LateAircraftDelay AS late_aircraft_delay_minutes,
        CASE WHEN Cancelled THEN 'Cancelled'
             WHEN Diverted THEN 'Diverted'
             ELSE 'Completed' END AS operation_status,
        NOT Cancelled AND NOT Diverted AND ArrDelay IS NOT NULL AS is_arrival_eligible
    FROM staging.source_flights
)
SELECT *,
    -- Unknown/ineligible outcomes stay NULL; they are never labelled on time.
    CASE WHEN is_arrival_eligible THEN arrival_delay_minutes >= 15 END AS arrival_delayed_15,
    CASE WHEN is_arrival_eligible THEN greatest(arrival_delay_minutes, 0) END
        AS positive_arrival_delay_minutes,
    carrier_delay_minutes IS NOT NULL AND weather_delay_minutes IS NOT NULL
        AND nas_delay_minutes IS NOT NULL AND security_delay_minutes IS NOT NULL
        AND late_aircraft_delay_minutes IS NOT NULL AS has_reported_delay_causes,
    1 AS scheduled_flight_count,
    CAST(is_cancelled AS INTEGER) AS cancelled_flight_count,
    CAST(is_diverted AS INTEGER) AS diverted_flight_count,
    CAST(is_arrival_eligible AS INTEGER) AS eligible_arrival_count,
    CAST(is_arrival_eligible AND arrival_delay_minutes < 15 AS INTEGER) AS on_time_arrival_count,
    CAST(is_arrival_eligible AND arrival_delay_minutes >= 15 AS INTEGER) AS delayed_arrival_count
FROM typed;
