"""Author a local Tableau workbook draft; native rendering must be checked separately.

Workbook XML uses the legacy 18.1 format found in Tableau Public 2026.2's own
bundled examples. The 26.1 ManifestByVersion route failed native loading even
though it passed the published baseline schema. No sample data is copied.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import zipfile

import duckdb
from lxml import etree as E

from acquire_bts import ROOT, sha256, write_json

WORKBOOK_VERSION = "18.1"


def child(parent, tag, text=None, **attributes):
    result = E.SubElement(parent, tag, {name.replace("_", "-"): str(value) for name, value in attributes.items()})
    if text is not None:
        result.text = str(text)
    return result


def title(parent, text):
    run = child(child(child(parent, "layout-options"), "title"), "formatted-text")
    child(run, "run", text, fontname="Arial", fontsize="14", bold="true")


def source(parent, name, csv_path, schema, columns):
    datasource = child(parent, "datasource", name=name, caption=name.replace("_", " ").title(), inline="true", version=WORKBOOK_VERSION)
    connection = child(datasource, "connection", class_="federated")
    connection.attrib["class"] = connection.attrib.pop("class-")
    named = child(child(connection, "named-connections"), "named-connection", name=f"textscan.{name}", caption=name)
    csv_connection = child(named, "connection", directory=str(csv_path.parent), filename=csv_path.name, password="", server="")
    csv_connection.set("class", "textscan")
    relation = child(connection, "relation", connection=f"textscan.{name}", name=csv_path.name,
                     table=f"[{csv_path.stem}#csv]", type="table")
    physical = child(relation, "columns", character_set="UTF-8", header="yes", locale="en_US", separator=",")
    for ordinal, (field, kind) in enumerate(schema.items()):
        datatype = {"VARCHAR": "string", "TIME": "string", "DATE": "date", "BOOLEAN": "boolean",
                    "INTEGER": "integer", "BIGINT": "integer", "HUGEINT": "integer", "DOUBLE": "real"}.get(kind)
        if datatype is None:
            raise ValueError(f"Unsupported Tableau source type: {field}: {kind}")
        child(physical, "column", datatype=datatype, name=field, ordinal=ordinal)
        measure = kind in {"INTEGER", "BIGINT", "HUGEINT", "DOUBLE"} and field != "scheduled_departure_hour"
        column = child(datasource, "column", name=f"[{field}]", caption=field.replace("_", " ").title(),
                       datatype=datatype, role="measure" if measure else "dimension",
                       type="quantitative" if measure else "ordinal" if datatype == "date" or field == "scheduled_departure_hour" else "nominal")
        if "rate" in field or "share" in field:
            column.set("default-format", "p0.00%")
        elif measure:
            column.set("default-format", "n#,##0")
        columns[(name, field)] = column
    return datasource


def calculated(datasource, columns, field, formula, datatype="real", dimension=False):
    name = datasource.get("name")
    column = child(datasource, "column", name=f"[{field}]", caption=field,
                   datatype=datatype, role="dimension" if dimension else "measure",
                   type="ordinal" if dimension else "quantitative")
    if not dimension:
        column.set("default-format", "p0.00%")
    calc = child(column, "calculation", formula=formula)
    calc.set("class", "tableau")
    columns[(name, field)] = column


def worksheet(parent, columns, name, datasource, row=None, col=None, text=None,
              color=None, mark="Bar", tooltip=None):
    sheet = child(parent, "worksheet", name=name)
    title(sheet, name)
    table = child(sheet, "table")
    view = child(table, "view")
    child(child(view, "datasources"), "datasource", name=datasource, caption=datasource.replace("_", " ").title())
    dependencies = child(view, "datasource-dependencies", datasource=datasource)
    # Include calculated-field inputs as well as direct shelf/encoding fields.
    for (source_name, _), column in columns.items():
        if source_name == datasource:
            dependencies.append(deepcopy(column))
    references = {}
    for specification in [row, col, text, color, tooltip]:
        if specification is None or specification in references:
            continue
        field, derivation, field_type = specification
        prefix = {"None": "none", "Sum": "sum", "Avg": "avg", "User": "usr"}[derivation]
        suffix = {"nominal": "nk", "ordinal": "ok", "quantitative": "qk"}[field_type]
        instance = f"[{prefix}:{field}:{suffix}]"
        child(dependencies, "column-instance", column=f"[{field}]", derivation=derivation,
              name=instance, pivot="key", type=field_type)
        references[specification] = f"[{datasource}].{instance}"
    child(view, "aggregation", value="true")
    style = child(table, "style")
    rule = child(style, "style-rule", element="worksheet")
    child(rule, "format", attr="font-family", value="Arial")
    pane = child(child(table, "panes"), "pane", selection_relaxation_option="selection-relaxation-allow")
    child(child(pane, "view"), "breakdown", value="auto")
    marking = child(pane, "mark")
    marking.set("class", mark)
    encodings = child(pane, "encodings")
    for role, specification in [("text", text), ("color", color), ("tooltip", tooltip)]:
        if specification:
            child(encodings, role, column=references[specification])
    pane_style = child(pane, "style")
    mark_rule = child(pane_style, "style-rule", element="mark")
    child(mark_rule, "format", attr="mark-color", value="#246a91")
    if text:
        child(mark_rule, "format", attr="mark-labels-show", value="true")
    child(table, "rows", references.get(row, ""))
    child(table, "cols", references.get(col, ""))


def dashboard(parent, name, placements, note):
    dash = child(parent, "dashboard", name=name)
    title(dash, name)
    child(dash, "style")
    child(dash, "size", minwidth="1200", maxwidth="1200", minheight="900", maxheight="900", sizing_mode="fixed")
    links = child(dash, "datasources")
    root = parent.getparent()
    sheet_sources = {sheet.get("name"): sheet.find("table/view/datasources/datasource").get("name")
                     for sheet in root.findall("worksheets/worksheet")}
    for source_name in sorted({sheet_sources[item[0]] for item in placements}):
        child(links, "datasource", name=source_name, caption=source_name.replace("_", " ").title())
    zones = child(child(dash, "zones"), "zone", id="0", x="0", y="0", w="100000", h="100000", type="layout-basic")
    for index, (sheet_name, x, y, width, height) in enumerate(placements, 1):
        zone = child(zones, "zone", id=index, name=sheet_name, x=x, y=y, w=width, h=height,
                     show_title="true")
        zone_style = child(zone, "zone-style")
        child(zone_style, "format", attr="margin", value="10")
    zone = child(zones, "zone", id=len(placements) + 1, x=2000, y=93000, w=96000, h=6500, type="text")
    child(child(zone, "formatted-text"), "run", note, fontsize="10", fontname="Arial")


def validate_xml(root):
    validate_legacy_compatibility(root)
    E.fromstring(E.tostring(root))
    sheet_names = [sheet.get("name") for sheet in root.findall("worksheets/worksheet")]
    if len(sheet_names) != len(set(sheet_names)):
        raise ValueError("Duplicate worksheet names")
    for zone in root.findall("dashboards/dashboard/zones//zone[@name]"):
        if zone.get("name") not in sheet_names:
            raise ValueError("Dashboard references a missing sheet")
    for datasource in root.findall("datasources/datasource"):
        available = {column.get("name") for column in datasource.findall("column")}
        for calc in datasource.findall("column/calculation"):
            for field in re.findall(r"\[[^\]]+\]", calc.get("formula")):
                if field not in available:
                    raise ValueError(f"Calculated field references unknown source field: {field}")
    for dependency in root.findall("worksheets/worksheet/table/view/datasource-dependencies"):
        available = {column.get("name") for column in dependency.findall("column")}
        for instance in dependency.findall("column-instance"):
            if instance.get("column") not in available:
                raise ValueError("Worksheet instance references an undefined field")


def validate_legacy_compatibility(root):
    """Keep the entire document on the bundled-sample legacy upgrade path."""
    if root.get("version") != WORKBOOK_VERSION:
        raise ValueError("Workbook version differs from the legacy compatibility target")
    if root.find("document-format-change-manifest/ManifestByVersion") is not None:
        raise ValueError("ManifestByVersion must not select the failing native format")
    if root.findall(".//simple-id") or root.find("explain-data") is not None:
        raise ValueError("Modern simple-id/explain-data elements are incompatible with this legacy format")
    for datasource in root.findall("datasources/datasource"):
        if datasource.get("version") != WORKBOOK_VERSION:
            raise ValueError("Mixed workbook and datasource format versions")


def build():
    period = "2025-01"
    processed = ROOT / "data/processed" / period
    quality = json.loads((ROOT / "data/metadata/bts_2025_01_quality.json").read_text())
    csv_path = processed / "tableau_flights.csv"
    expected = next(item for item in quality["output_files"] if item["path"].endswith("tableau_flights.csv"))
    if sha256(csv_path) != expected["sha256"]:
        raise ValueError("Tableau source differs from validated export")
    database = processed / "airline_operations.duckdb"
    expected_database = next(item for item in quality["output_files"] if item["path"].endswith(".duckdb"))
    if sha256(database) != expected_database["sha256"]:
        raise ValueError("Schema database differs from validated preparation output")
    analysis = json.loads((ROOT / "data/metadata/bts_2025_01_analysis.json").read_text())
    expected_causes = next(item for item in analysis["exports"] if item["path"].endswith("delay_causes.csv"))
    if sha256(ROOT / expected_causes["path"]) != expected_causes["sha256"]:
        raise ValueError("Reported-cause table differs from validated SQL output")
    connection = duckdb.connect(str(processed / "airline_operations.duckdb"), read_only=True)
    try:
        fields = dict((row[0], row[1]) for row in connection.execute("DESCRIBE analytics.tableau_flights").fetchall())
    finally:
        connection.close()
    root = E.Element("workbook", version=WORKBOOK_VERSION, **{
        "source-build": "0.0.0 (0000.0.0.0)", "source-platform": "mac", "locale": "en_US",
    })
    child(root, "preferences")
    child(root, "style")
    sources = child(root, "datasources")
    columns = {}
    datasource = source(sources, "airline_flights", Path("../data/processed/2025-01/tableau_flights.csv"), fields, columns)
    for field, numerator, denominator in [
        ("Arrival on-time rate", "on_time_arrival_count", "eligible_arrival_count"),
        ("Cancellation rate", "cancelled_flight_count", "scheduled_flight_count"),
        ("Diversion rate", "diverted_flight_count", "scheduled_flight_count"),
    ]:
        calculated(datasource, columns, field,
                   f"IF SUM([{denominator}]) > 0 THEN SUM([{numerator}]) / SUM([{denominator}]) END")
    calculated(datasource, columns, "Weekday", "DATEPART('weekday', [flight_date], 'monday')", datatype="integer", dimension=True)
    calculated(datasource, columns, "Window on-time rate (n >= 100)",
               "IF SUM([eligible_arrival_count]) >= 100 THEN SUM([on_time_arrival_count]) / SUM([eligible_arrival_count]) END")
    cause_path = processed / "analysis/delay_causes.csv"
    cause_schema = {"category": "VARCHAR", "reported_delay_minutes": "BIGINT",
                    "flights_with_complete_cause_reporting": "BIGINT",
                    "flights_with_positive_category_minutes": "BIGINT", "share_of_reported_minutes": "DOUBLE"}
    source(sources, "reported_causes", Path("../data/processed/2025-01/analysis/delay_causes.csv"), cause_schema, columns)
    sheets = child(root, "worksheets")
    dimension = lambda name: (name, "None", "nominal")
    measure = lambda name: (name, "Sum", "quantitative")
    calculation = lambda name: (name, "User", "quantitative")
    for name, specification in [
        ("Scheduled flights", measure("scheduled_flight_count")),
        ("Arrival on-time rate", calculation("Arrival on-time rate")),
        ("Cancellation rate", calculation("Cancellation rate")),
        ("Diversion rate", calculation("Diversion rate")),
    ]:
        worksheet(sheets, columns, name, "airline_flights", text=specification, mark="Text")
    dates = ("flight_date", "None", "quantitative")
    worksheet(sheets, columns, "Daily arrival reliability", "airline_flights", row=calculation("Arrival on-time rate"), col=dates, mark="Line",
              tooltip=measure("eligible_arrival_count"))
    worksheet(sheets, columns, "Daily cancellations", "airline_flights", row=calculation("Cancellation rate"), col=dates, mark="Bar",
              tooltip=measure("cancelled_flight_count"))
    worksheet(sheets, columns, "Airline on-time rates (unadjusted)", "airline_flights", row=dimension("reporting_airline"),
              col=calculation("Arrival on-time rate"), tooltip=measure("eligible_arrival_count"))
    worksheet(sheets, columns, "Airline flight volumes", "airline_flights", row=dimension("reporting_airline"),
              col=measure("scheduled_flight_count"), tooltip=measure("cancelled_flight_count"))
    worksheet(sheets, columns, "Departure window reliability", "airline_flights",
              row=("Weekday", "User", "ordinal"), col=("scheduled_departure_hour", "None", "ordinal"),
              color=calculation("Window on-time rate (n >= 100)"), tooltip=measure("eligible_arrival_count"), mark="Square")
    worksheet(sheets, columns, "Reported delay minutes (full January)", "reported_causes", row=dimension("category"),
              col=("share_of_reported_minutes", "Avg", "quantitative"), tooltip=measure("reported_delay_minutes"))
    dashboards = child(root, "dashboards")
    dashboard(dashboards, "01 Operations overview | January 2025", [
        ("Scheduled flights", 1000, 6000, 24000, 13000),
        ("Arrival on-time rate", 26000, 6000, 24000, 13000),
        ("Cancellation rate", 51000, 6000, 24000, 13000),
        ("Diversion rate", 76000, 6000, 23000, 13000),
        ("Daily arrival reliability", 1000, 21000, 49000, 33000),
        ("Daily cancellations", 51000, 21000, 48000, 33000),
        ("Airline on-time rates (unadjusted)", 1000, 56000, 49000, 35000),
        ("Airline flight volumes", 51000, 56000, 48000, 35000),
    ], "BTS reporting-carrier records, January 2025. On time: arrival delay <15 min among eligible arrivals. Cancellations/diversions use scheduled flights. Airline comparisons are unadjusted.")
    dashboard(dashboards, "02 Delay diagnostics | January 2025", [
        ("Departure window reliability", 1000, 7000, 98000, 47000),
        ("Reported delay minutes (full January)", 1000, 56000, 98000, 34000),
    ], "Weekday: Monday=1 to Sunday=7. Low-volume cells (<100 eligible arrivals) are unavailable. Reported category shares cover the full month and use a separate aggregate source; they do not follow flight-source filters.")
    windows = child(root, "windows", source_height="900")
    for index, dash in enumerate(dashboards):
        window = child(windows, "window", name=dash.get("name"), maximized="true" if index == 0 else "false")
        window.set("class", "dashboard")
        viewpoints = child(window, "viewpoints")
        for zone in dash.findall("zones//zone[@name]"):
            child(child(viewpoints, "viewpoint", name=zone.get("name")), "zoom", type="entire-view")
        child(window, "active", id="-1")
    directory = ROOT / "tableau"
    directory.mkdir(exist_ok=True)
    validate_xml(root)
    workbook = directory / "airline_operations_2025_01_DRAFT.twb"
    E.ElementTree(root).write(str(workbook), encoding="utf-8", xml_declaration=True, pretty_print=True)
    packaged = directory / "airline_operations_2025_01_DRAFT_v3.twbx"
    packaged_root = deepcopy(root)
    for node in packaged_root.findall(".//connection[@class='textscan']"):
        node.set("directory", "Data")
    temporary_package = packaged.with_suffix(".twbx.part")
    with zipfile.ZipFile(temporary_package, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(workbook.name, E.tostring(packaged_root, encoding="utf-8", xml_declaration=True))
        zipped.write(csv_path, "Data/tableau_flights.csv")
        zipped.write(cause_path, "Data/delay_causes.csv")
    with zipfile.ZipFile(temporary_package) as zipped:
        if zipped.testzip() is not None:
            raise ValueError("Packaged workbook integrity check failed")
        validate_xml(E.fromstring(zipped.read(workbook.name)))
    temporary_package.replace(packaged)
    report = {
        "status": "draft_native_verification_pending", "worksheets": len(root.findall("worksheets/worksheet")),
        "dashboards": len(root.findall("dashboards/dashboard")),
        "xml_well_formed_and_references": "passed", "dashboard_sheet_references": "passed",
        "package_integrity": "passed", "native_open_and_visual_check": "revision 3 awaiting native check; revisions 1 and 2 failed with D2E8DA72",
        "compatibility": {"format_version": WORKBOOK_VERSION,
                          "reference": "Tableau Public 2026.2 bundled PerformanceRecording_new.twb",
                          "change": "Remove modern simple-id/explain-data nodes; use legacy dashboard containers and windows",
                          "revision_1_native_errors": ["Missing worksheet number attribute", "Missing mark type attribute", "Missing worksheet-number element", "Sort-G/ShelfSorts-G schema-group errors"],
                          "revision_2_native_errors": ["simple-id elements/uuid attributes not declared in legacy schema", "explain-data not allowed in legacy workbook"]},
        "published_xsd_validation": "Not used for legacy compatibility; previous published-schema passes did not predict native loading",
        "workbook": {"path": str(workbook.relative_to(ROOT)), "sha256": sha256(workbook)},
        "package": {"path": str(packaged.relative_to(ROOT)), "sha256": sha256(packaged), "bytes": packaged.stat().st_size},
        "source_csv_sha256": sha256(csv_path), "cause_csv_sha256": sha256(cause_path),
        "build_script_sha256": sha256(Path(__file__)),
        "pending": ["Open revision 3 in Tableau Public", "Check rendering, field formats and data connections", "Reconcile KPI values with SQL", "Add and verify shared filters/actions", "Build the route/origin hotspot page", "Capture native screenshots"],
    }
    write_json(ROOT / "data/metadata/bts_2025_01_tableau_draft.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build()
