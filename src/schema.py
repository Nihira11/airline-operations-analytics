"""Explicit types for the 109 BTS reporting-carrier source fields."""

TEXT_FIELDS = set("""
Reporting_Airline IATA_CODE_Reporting_Airline Tail_Number
Flight_Number_Reporting_Airline Origin OriginCityName OriginState OriginStateFips
OriginStateName Dest DestCityName DestState DestStateFips DestStateName
DepTimeBlk ArrTimeBlk CancellationCode
""".split())

CLOCK_FIELDS = set("""
CRSDepTime DepTime WheelsOff WheelsOn CRSArrTime ArrTime FirstDepTime
""".split())

BOOLEAN_FIELDS = {"DepDel15", "ArrDel15", "Cancelled", "Diverted", "DivReachedDest"}

INTEGER_FIELDS = set("""
Year Quarter Month DayofMonth DayOfWeek DOT_ID_Reporting_Airline
OriginAirportID OriginAirportSeqID OriginCityMarketID OriginWac
DestAirportID DestAirportSeqID DestCityMarketID DestWac
DepDelay DepDelayMinutes DepartureDelayGroups TaxiOut TaxiIn
ArrDelay ArrDelayMinutes ArrivalDelayGroups CRSElapsedTime ActualElapsedTime
AirTime Flights Distance DistanceGroup CarrierDelay WeatherDelay NASDelay
SecurityDelay LateAircraftDelay TotalAddGTime LongestAddGTime DivAirportLandings
DivActualElapsedTime DivArrDelay DivDistance
""".split())

for number in range(1, 6):
    TEXT_FIELDS.update({f"Div{number}Airport", f"Div{number}TailNum"})
    CLOCK_FIELDS.update({f"Div{number}WheelsOn", f"Div{number}WheelsOff"})
    INTEGER_FIELDS.update({
        f"Div{number}AirportID", f"Div{number}AirportSeqID",
        f"Div{number}TotalGTime", f"Div{number}LongestGTime",
    })

SIGNED_INTEGER_FIELDS = {
    "DepDelay", "ArrDelay", "DepartureDelayGroups", "ArrivalDelayGroups", "DivArrDelay",
}


def source_types(fields):
    expected = TEXT_FIELDS | CLOCK_FIELDS | BOOLEAN_FIELDS | INTEGER_FIELDS | {"FlightDate"}
    if set(fields) != expected or len(fields) != len(expected):
        raise ValueError(
            f"Unexpected source schema. Missing: {sorted(expected - set(fields))}; "
            f"extra: {sorted(set(fields) - expected)}"
        )
    return {name: (
        "DATE" if name == "FlightDate" else
        "BOOLEAN" if name in BOOLEAN_FIELDS else
        "INTEGER" if name in INTEGER_FIELDS else "VARCHAR"
    ) for name in fields}


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def token(name):
    return f"NULLIF(TRIM({identifier(name)}), '')"


def invalid_token(name, data_type):
    """Reject malformed values before casting; never round fractional minutes."""
    value = token(name)
    if data_type in {"INTEGER", "BOOLEAN"}:
        valid = (
            f"regexp_full_match({value}, '[+-]?[0-9]+([.]0+)?') "
            f"AND TRY_CAST({value} AS INTEGER) IS NOT NULL"
        )
        if data_type == "BOOLEAN":
            valid += f" AND TRY_CAST({value} AS INTEGER) IN (0, 1)"
    elif data_type == "DATE":
        valid = (
            f"regexp_full_match({value}, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}') "
            f"AND TRY_CAST({value} AS DATE) IS NOT NULL"
        )
    elif name in CLOCK_FIELDS:
        valid = (
            f"(regexp_full_match({value}, '([01][0-9]|2[0-3])[0-5][0-9]') "
            f"OR {value} = '2400')"
        )
    else:
        return "FALSE"
    return f"({value} IS NOT NULL AND NOT COALESCE(({valid}), FALSE))"


def typed_expression(name, data_type):
    value = token(name)
    if data_type == "BOOLEAN":
        return f"CAST(CAST({value} AS INTEGER) AS BOOLEAN)"
    return f"CAST({value} AS {data_type})"
