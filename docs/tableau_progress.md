# Tableau progress — 22 October 2026

The January portfolio workbook is `tableau/Airline Operations January 2025.twbx`. One downloadable package contains 14 worksheets and three dashboards:

- 01 Operations Overview
- 02 Disruption Hotspots
- 03 Delay Diagnostics

The user-authored source remains locally at `tableau/Airline Operations January 2025.twb`. The packaged workbook replaces the earlier `- lilac.twb` source file in GitHub. Its archive passes CRC verification and includes one Hyper extract and ten images; all extract and dashboard bitmap references resolve within the package. These structural checks do not replace reopening it in Tableau or testing interactions.

## Dashboard screenshots

The user captured the three complete, unfiltered dashboards. They are stored in [dashboard_screenshots](../reports/2025-01/dashboard_screenshots/) and displayed in the README:

- `01-operations-overview.png`: 539,747 scheduled flights, 81.21% on-time arrivals, 3.02% cancellations, and 0.22% diversions.
- `02-disruption-hotspots.png`: origin and route comparisons with their minimum volumes, and the weekday/hour heatmap.
- `03-delay-diagnostics.png`: 40-minute median and 145-minute P90 among eligible delayed arrivals, severity counts, and reported delay-category minutes.

The diagnostics screenshot confirms the causes axis is labelled Reported Delay Minutes. Screenshots document appearance and the displayed values; they do not verify filter behaviour.

## Authoring notes

The heatmap uses weekday names from `DATENAME('weekday', [Flight Date])`. Sunday at 20:00 was checked against SQL: 3,262 eligible arrivals, 2,208 on-time arrivals, and 67.69%. A worksheet-only table calculation filter, `LOOKUP(SUM([Eligible Arrival Count]), 0) >= 100`, hides low-volume marks; Show Empty Columns retains all 24 hour headers. The heatmap uses rose for lower rates and violet for higher rates, with a colour range that adjusts with filters as explained in the footer.

The causes chart displays summed minutes using Measure Names and Measure Values. Its category order is manual and does not automatically rerank when filters change. These final manual choices supersede the original guide's sequential heatmap and category-share chart instructions.

## Remaining manual checks

1. Reopen the packaged workbook in Tableau and verify the extract and dashboard images load.
2. Test airline, date, origin, destination, and combined filters across all three dashboards. Keep chart-specific eligibility, volume, band, and rank filters local.
3. Reset shared dropdowns to All and dates to 1–31 January 2025. Recheck the overview totals and the 40/145 minute cards, then save.
4. If publishing to Tableau Public, verify the live view and add its actual link to the README and case study. GitHub hosts the package and screenshots; no live Tableau Public publication is claimed.

Use plain one-line commit messages without type prefixes; push only when authorized.
