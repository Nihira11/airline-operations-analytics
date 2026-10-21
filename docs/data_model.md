# January analytics data model

The project stores one record per reported flight, then derives additive counts for analysis. All sources and outputs refer to January 2025. The [machine-readable schema](../data/metadata/bts_2025_01_curated_schema.json) contains the complete field/type inventory; the [publisher dictionary](../data/metadata/bts_2025_01_dictionary.json) defines the original 109 named fields.

## Tables and keys

| Relation | Grain and key | Purpose |
| --- | --- | --- |
| `staging.source_flights` | One original record; source file and record number | All 109 typed source fields plus lineage |
| `staging.source_quality_issues` | Source record and measurement | Preserved anomalies, including one negative diverted elapsed-time measurement |
| `analytics.flights` | One flight; `flight_id` | Descriptive names, status, local clocks, delay labels, and additive counts |
| `analytics.dim_airports` | One airport; `airport_id` | Source-observed code, city, and state mappings |
| `analytics.dim_airlines` | One reporting carrier; `airline_id` | Source-observed reporting and IATA carrier codes |
| `analytics.tableau_flights` | One flight; `flight_id` | 39 dashboard fields, with origin and destination city/state labels |
| `analytics.daily_operations` | Flight date and reporting carrier | Small overview export with summed counts |

`flight_id` hashes date, reporting carrier, flight number, origin/destination IDs, and scheduled departure HHMM. The source candidate key and exact duplicate records are checked before publishing data. Airport/carrier dimensions are checked for unique keys and complete joins. They are observed mappings for this month, not enriched external master tables. Joining the two airport roles must not multiply flight records.

## Dashboard fields

| Fields | Meaning and Tableau handling |
| --- | --- |
| `flight_id`, `flight_number` | String identifiers. Do not sum them. |
| `flight_date` | Date; use exact daily dates for January trends. |
| `reporting_airline` | Reporting-carrier code, distinct from marketing brand. |
| `origin_airport`, `destination_airport`, `route` | Codes and directional origin–destination route; strings/dimensions. |
| `origin_city`, `origin_state`, `destination_city`, `destination_state` | Labels from the corresponding observed airport mappings. |
| `scheduled_departure_local`, `scheduled_arrival_local` | Local clock values. A CSV may read these as strings; do not infer time zones or flight durations from them. |
| `scheduled_departure_hour` | Integer 0–23; use as a discrete dimension in a heatmap. |
| `scheduled_departure_is_2400`, `scheduled_arrival_is_2400` | Boolean markers preserving the original midnight convention. |
| `scheduled_elapsed_minutes`, `distance_miles` | Published scheduled duration and distance. |
| `departure_delay_minutes`, `arrival_delay_minutes` | Signed observed delays; early values remain negative. |
| `positive_arrival_delay_minutes` | Arrival delay clipped at zero for eligible arrivals; NULL for ineligible records. |
| `operation_status` | Completed, Cancelled, or Diverted. Filtering to Completed changes scheduled-flight metrics. |
| `is_cancelled`, `is_diverted`, `is_arrival_eligible` | Boolean outcome/denominator flags. |
| `arrival_delayed_15` | Boolean delay label for eligible arrivals; otherwise NULL. |
| `has_reported_delay_causes` | All five category fields are populated; use with arrival eligibility and the delay label. |
| `carrier_delay_minutes`, `weather_delay_minutes`, `nas_delay_minutes`, `security_delay_minutes`, `late_aircraft_delay_minutes` | Reported category minutes; retain missing values and distinguish minutes from flight counts. |
| `has_source_quality_issue` | Source measurement warning; no flight is removed. |
| `scheduled_flight_count` | One for every flight. Sum gives scheduled flights. |
| `eligible_arrival_count`, `on_time_arrival_count`, `delayed_arrival_count` | Additive counts for the arrival population and its two outcomes. |
| `cancelled_flight_count`, `diverted_flight_count` | Additive counts with scheduled flights as denominator. |

There are no missing arrival delays among completed, non-diverted January flights. The 17,478 ineligible arrivals equal 16,312 cancellations plus 1,166 diversions. This observed partition is checked; it is not a general instruction to force future missing data into an outcome class.

## Analysis exports

All files below are generated in `data/processed/2025-01/analysis/`. Read them as separate analytical tables, not as joins onto the flight table: joining a route summary or five category rows to every flight would duplicate measures.

| File | Grain and interpretation |
| --- | --- |
| `overview.csv` | One monthly row with counts, ratios, and delay quantiles |
| `daily.csv` | One flight date; daily counts and ratios |
| `airlines.csv` | One reporting carrier; unadjusted performance |
| `origins.csv` | One origin airport; rates, volumes, and threshold flags |
| `routes.csv` | One directional route; rates, volumes, and threshold flags |
| `departure_windows.csv` | Weekday and scheduled departure hour; Monday=1 |
| `delay_causes.csv` | One category; full-month minute sums and minute shares |
| `common_route_comparisons.csv` | One carrier pair; pair-specific shared-route/time population |
| `delay_severity.csv` | One of six mutually exclusive eligible-arrival delay bands |
| `cause_coverage.csv` | One row quantifying complete/missing category coverage |

Every export is read back with explicit types and compared with its SQL relation in both directions, including duplicate multiplicities. The [analysis manifest](../data/metadata/bts_2025_01_analysis.json) records file hashes and the queries used.

## Aggregation rules

Compute arrival on-time rate as summed on-time counts divided by summed eligible counts. Cancellation/diversion rates use summed scheduled counts. Never average subgroup percentages or add rate columns. Median and percentile values are not additive; calculate them from flight records when filtering.

The cause export and pairwise comparison export are fixed full-month summaries. Flight-source filters cannot recompute them. A shared filter or ordinary join does not recreate pairwise pooled weights. Use clear full-month labels or omit these supplementary sources from a filtered dashboard.
