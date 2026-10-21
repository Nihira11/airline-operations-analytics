# Build the January Tableau dashboard

Build a new workbook yourself from the validated flight-level CSV. Complete one checkpoint at a time. A worksheet is one chart or number; a dashboard arranges several worksheets on one page. The finished workbook will have three dashboards: Overview, Hotspots, and Delay Diagnostics.

## 1 Connect the data

1. Open Tableau Public and start a new workbook.
2. Choose **Text file** and open `data/processed/2025-01/tableau_flights.csv` from this project.
3. Name the data source **January Flights**. Use this one source for all core worksheets. Do not join the analysis summary CSVs onto the flight rows.
4. On the Data Source page choose an extract, retain all rows without aggregation, and create/save it when prompted. Depending on the version, creation starts when you open a worksheet. This is the step required by the earlier extract error.
5. Open **Sheet 1**.

Checkpoint: the source has 39 fields. A preview may show only a limited sample; use the first KPI below to verify the full 539,747 rows. Tableau's [extract guide](https://help.tableau.com/current/pro/desktop/en-us/extracting_data.htm) describes the controls for current versions.

## 2 Check field types

Keep `flight_date` as a Date. Carrier, airport, route, flight number, and flight ID are dimensions/strings. Count and delay-minute fields are numeric. Treat `scheduled_departure_hour` as a discrete dimension. Status/eligibility fields are booleans. Leave the local clock strings alone; the heatmap uses the numeric hour field.

Use the exact field names below. If Tableau displays a cleaned-up caption, insert the matching field from the calculation editor's autocomplete rather than guessing its name. The [data model](data_model.md) explains the fields.

## 3 Create the calculated fields

In the Data pane, use **Create Calculated Field**. Create each named field separately.

**Arrival On Time Rate**

```text
IF SUM([eligible_arrival_count]) > 0 THEN
    SUM([on_time_arrival_count]) / SUM([eligible_arrival_count])
END
```

**Cancellation Rate**

```text
IF SUM([scheduled_flight_count]) > 0 THEN
    SUM([cancelled_flight_count]) / SUM([scheduled_flight_count])
END
```

**Diversion Rate**

```text
IF SUM([scheduled_flight_count]) > 0 THEN
    SUM([diverted_flight_count]) / SUM([scheduled_flight_count])
END
```

Set these three fields' default number format to Percentage with two decimal places. Keep them as aggregate calculations; do not average the rates from summary exports.

**Weekday Number**

```text
DATEPART('weekday', [flight_date], 'monday')
```

**Weekday Label**

```text
CASE [Weekday Number]
WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri' WHEN 6 THEN 'Sat'
WHEN 7 THEN 'Sun' END
```

**Eligible Window Rate**

```text
IF SUM([eligible_arrival_count]) >= 100 THEN
    SUM([on_time_arrival_count]) / SUM([eligible_arrival_count])
END
```

**Delay Band**

```text
IF NOT [is_arrival_eligible] THEN NULL
ELSEIF [arrival_delay_minutes] < 0 THEN '1 Early (<0 min)'
ELSEIF [arrival_delay_minutes] < 15 THEN '2 0-14 min'
ELSEIF [arrival_delay_minutes] < 30 THEN '3 15-29 min'
ELSEIF [arrival_delay_minutes] < 60 THEN '4 30-59 min'
ELSEIF [arrival_delay_minutes] < 120 THEN '5 60-119 min'
ELSE '6 120+ min' END
```

**Delayed Arrival Minutes**

```text
IF [is_arrival_eligible] AND [arrival_delayed_15] THEN
    [arrival_delay_minutes]
END
```

## 4 Build and verify the KPI worksheets

Create four separate worksheets. For the first, rename Sheet 1 to **KPI Scheduled Flights**, set Marks to Text, and drag `scheduled_flight_count` onto Text. Confirm aggregation is SUM, then format as a whole number with thousands separators.

For each remaining worksheet, add the corresponding calculated rate to Text. Set large readable labels, remove gridlines, and use simple titles.

| Worksheet | Text field | Expected with no filters |
| --- | --- | --- |
| KPI Scheduled Flights | SUM scheduled count | 539,747 |
| KPI Arrival On Time | Arrival On Time Rate | 81.21% |
| KPI Cancellations | Cancellation Rate | 3.02% |
| KPI Diversions | Diversion Rate | 0.22% |

Stop here if a value differs. Check that the full source is loaded, filters are cleared, and the rates use the correct numerator/denominator. Avoid a global Completed-only filter: it removes cancellations from scheduled metrics.

## 5 Build daily trends and airline comparison

For **Daily Arrival Reliability**, place `flight_date` on Columns and Arrival On Time Rate on Rows. Use an exact daily date rather than a month or year grouping, and choose Line marks. Add SUM eligible count and SUM on-time count to Tooltip. A percentage axis from 0% to 100% makes the scale explicit.

For **Daily Cancellations**, duplicate that worksheet, replace the rate with Cancellation Rate, and choose Bar marks. Use scheduled and cancelled counts in Tooltip. January 10 should show 15.98%, with 2,856 cancellations and 17,873 scheduled flights.

For **Airline Arrival Reliability**, use `reporting_airline` on Rows and Arrival On Time Rate on Columns. Add eligible arrivals and delayed arrivals to Tooltip, and sort by the rate. Title it **Arrival reliability by reporting carrier — unadjusted**. A raw carrier rate reflects its operating mix; it is not a causal service-quality score.

## 6 Build origin and route hotspot charts

For **Origin Arrival Reliability**, place `origin_airport` on Rows and Arrival On Time Rate on Columns. Add SUM eligible count to Filters and retain values of at least 1,000. Apply this threshold only to this worksheet. Sort the rate ascending and add city, eligible arrivals, and delayed arrivals to Tooltip. GRR should be lowest at 73.93% with 1,312 eligible arrivals; DEN should show 75.06% and 6,074 delayed arrivals.

For **Route Delay Volume**, place `route` on Rows and SUM delayed count on Columns. Sort descending. Add a worksheet-only filter requiring SUM eligible count of at least 500 and include both counts and the arrival on-time rate in Tooltip. ORD–LGA should lead the delayed count with 200 delayed / 905 eligible arrivals. If you later display a Top 10, verify it updates after airline/date filters; table-calculation ranking is applied after ordinary dimension filters. A full sorted list with scrolling is sufficient for the first build.

Do not propagate the origin or route minimum-volume filters to KPI worksheets. Thresholds apply to the chart groups remaining after the user's filters; low-volume groups should disappear rather than become zero-rate bars.

## 7 Build the weekday and hour heatmap

Place `scheduled_departure_hour` on Columns as a discrete value and Weekday Label on Rows. Sort labels Monday–Sunday using Weekday Number. Use Square marks, put Eligible Window Rate on Color, and add eligible and on-time counts to Tooltip. Format the colour value as a percentage and use a single sequential palette with a fixed 0–100% scale. Null means fewer than 100 eligible arrivals, not 0% reliability; show null cells in light grey and explain that rule in the title or subtitle.

The unfiltered Sunday 20:00 cell has 3,262 eligible arrivals and a 67.69% on-time rate. Hours are local to each departure airport; this is a descriptive comparison, not one shared time zone.

## 8 Build the severity chart and delay quantiles

On **Arrival Delay Distribution**, add a worksheet-only `is_arrival_eligible = True` filter. Place Delay Band on Rows and SUM eligible count on Columns; sort bands 1–6. Show the count on each bar. The six expected counts are 341,773; 82,366; 35,325; 29,560; 19,728; and 13,517. They sum to 522,269 eligible arrivals.

Create two small Text worksheets from Delayed Arrival Minutes: set its aggregation to MEDIAN on one (40 minutes) and use `PERCENTILE([Delayed Arrival Minutes], 0.9)` on the other (145 minutes). These calculations exclude ineligible and sub-15-minute arrivals by construction. [Tableau aggregate-function reference](https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_aggregate_create.htm).

## 9 Build an interactive category-share chart

Keep the same flight-level source so date/carrier/airport filters can recompute this chart. On this worksheet only, filter `is_arrival_eligible`, `arrival_delayed_15`, and `has_reported_delay_causes` to True.

Create **Reported Category Minutes**:

```text
SUM([carrier_delay_minutes]) + SUM([weather_delay_minutes])
+ SUM([nas_delay_minutes]) + SUM([security_delay_minutes])
+ SUM([late_aircraft_delay_minutes])
```

Create **Air Carrier Share**:

```text
IF [Reported Category Minutes] > 0 THEN
    SUM([carrier_delay_minutes]) / [Reported Category Minutes]
END
```

Make four equivalent share fields using the other category-minute columns, named Weather Share, NAS Share, Security Share, and Late Aircraft Share. Format all five as percentages. Put Measure Names on Rows and Measure Values on Columns, then retain only these five share calculations in the view. Use Bar marks and percentage labels. Include Reported Category Minutes in Tooltip. Do not use a percent-of-total calculation independently on each raw measure; the common denominator is the sum of all five categories.

With no global filters, expected shares are Air Carrier 36.16%, Late Aircraft 34.72%, NAS 19.90%, Weather 9.07%, and Security 0.15%, over 6,943,994 reported minutes. They describe reported attribution. The SQL `delay_causes.csv` is an independent full-month reference, not an extra table to join to flights.

## 10 Arrange the three dashboards

Use tiled containers and a fixed desktop canvas around 1200 × 900 pixels. Use a white background, one blue for reliability, orange for cancellations/severity, and clear labels. Avoid relying only on red/green distinctions.

| Dashboard | Layout |
| --- | --- |
| Overview | Title/filters; four KPI cards; two daily trends; airline comparison |
| Hotspots | Title/filters; origin and route charts; weekday/hour heatmap |
| Delay Diagnostics | Title/filters; median and P90 cards; severity and category-share charts |

Add a source/metric footer: **US DOT/BTS Reporting Carrier On-Time Performance, January 2025. On time = arrival delay under 15 minutes among eligible arrivals. Cancellation/diversion rates use scheduled flights.** Add chart-specific volume thresholds. Use tooltips with numerator and denominator counts, not percentages alone.

The common-route carrier comparisons are an optional supplementary full-month view. Do not connect them to flight filters or imply that ordinary filtering recalculates the pooled weights. Explain coverage if you use the UA/WN comparison from the case study.

## 11 Add shared filters and check interactions

Expose flight date, reporting airline, origin airport, and destination airport. For each, use **Apply to Worksheets → All Using This Data Source**. Keep the eligibility, category, and minimum-volume filters local to their own worksheets. [Tableau shared-filter instructions](https://help.tableau.com/current/pro/desktop/en-gb/filtering_global.htm).

Test one airline first, then clear it. Test an origin and clear it. Combine filters and confirm all relevant charts update. For an airline-selection dashboard action, configure a filter action with the airline chart as source, the intended flight charts as targets, and clearing the selection restoring all values. Then test both selecting and clearing the mark.

## 12 Final checks and screenshots

Clear all filters and restore every unfiltered checkpoint above. Check a second population: UA has 60,668 eligible arrivals and an 82.37% on-time rate. Empty filter combinations must show unavailable/blank ratios rather than invented zero percentages. Check that category shares still sum to 100% when reported minutes exist, and that severity counts equal eligible arrivals in the same selected population.

Save your workbook locally in `tableau/` and keep its extract with it, preferably as a packaged workbook for portability. Capture the three completed dashboards and one filtered view in `reports/2025-01/`. After you choose to publish, check the live Tableau Public view and add its actual link to the README and case study. Publication and screenshots are the remaining portfolio steps; none are claimed by the analytics verification script.
