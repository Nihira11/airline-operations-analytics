# Tableau progress — 22 October 2026

The current user-authored Tableau Public workbook is `tableau/Airline Operations January 2025 - lilac.twb`, replacing the earlier January workbook. It contains 14 worksheets and three dashboards:

- 01 Operations Overview
- 02 Disruption Hotspots
- 03 Delay Diagnostics

The lilac workbook XML parses successfully. It references the local January flight CSV, a Tableau temporary Hyper extract, and image files in the user's Downloads folder; a portable data package and a reopen check are still pending. Raw and processed data remain excluded from Git.

## Checks completed during authoring

These checks were recorded during the earlier January workbook's authoring on 21 October. Recheck them against the current lilac workbook before claiming final verification.

Screenshots showed the full-month overview values: 539,747 scheduled flights, 81.21% arrival on-time rate, 3.02% cancellation rate, and 0.22% diversion rate. The six severity bands totalled 522,269 eligible arrivals. Reported category minutes totalled 6,943,994. The delayed-flight median and P90 cards showed 40 and 145 minutes with shared filters cleared.

The heatmap uses weekday names from `DATENAME('weekday', [Flight Date])`. Sunday at 20:00 was checked against SQL: 3,262 eligible arrivals, 2,208 on-time arrivals, and 67.69%. A worksheet-only table calculation filter, `LOOKUP(SUM([Eligible Arrival Count]), 0) >= 100`, hides low-volume marks; Show Empty Columns retains all 24 hour headers. The red–blue colour range adjusts with filters, as explained in the footer.

The causes chart displays summed minutes using Measure Names and Measure Values. Its category order is manual and does not automatically rerank when filters change. These final manual choices supersede the original guide's sequential heatmap and category-share chart instructions.

## Resume next session

1. Confirm the causes axis is labelled Reported Delay Minutes rather than Value.
2. Test airline, date, origin, destination, and combined filters across all three dashboards. Keep chart-specific eligibility, volume, band, and rank filters local.
3. Reset shared dropdowns to All and dates to 1–31 January 2025. Recheck overview totals and the 40/145 minute cards, then save.
4. Verify the saved lilac workbook reopens with durable data and image connections; create a portable package through Tableau if needed.
5. Capture clean dashboard screenshots, finish workbook/publication documentation, and perform the final release review. Publication has not been verified.

Annual 2025 analysis and prediction modelling remain deferred. The user requested stopping for the night and continuing the remaining work tomorrow. Use plain one-line commit messages without type prefixes; push only when authorized.
