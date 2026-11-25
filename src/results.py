"""Extract annual IdealLoads metrics from EnergyPlus SQLite, read-only.

Supply-air total loads include sensible and latent conditioning. These are
thermal quantities, not purchased electricity or fuel consumption.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re
import sqlite3
from pathlib import Path

HEAT = "Zone Ideal Loads Supply Air Total Heating Energy"
COOL = "Zone Ideal Loads Supply Air Total Cooling Energy"
J_PER_KWH = 3_600_000.0
METRICS = ("heating_kWh_per_m2_a", "cooling_kWh_per_m2_a", "ideal_total_kWh_per_m2_a")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def annual_metrics(monthly: list[dict], area: float) -> dict:
    if not math.isfinite(area) or area <= 0 or not monthly:
        raise ValueError("A positive conditioned floor area and monthly data are required")
    energy = {}
    for name in ("heating_J", "cooling_J"):
        values = [float(row[name]) for row in monthly]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError(f"Invalid energy in {name}")
        energy[name] = math.fsum(values)
    h, c = (energy[name] / J_PER_KWH / area for name in ("heating_J", "cooling_J"))
    return {"annual_heating_J": energy["heating_J"], "annual_cooling_J": energy["cooling_J"],
            METRICS[0]: h, METRICS[1]: c, METRICS[2]: h + c}


def extract_sql(path: Path) -> tuple[float, list[dict]]:
    """Return actual conditioned area and 12 monthly rows per conditioned zone.

    Reject incomplete, duplicated, nonannual or mismatched-zone series. The
    naming convention belongs to the supplied models, not arbitrary IDFs.
    """
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        # This archive's SQL flags remain the strings FALSE/FALSE even when
        # EnergyPlus completes. Use both final engine records, not bool('FALSE').
        err = path.with_suffix('.err').read_text(encoding='utf-8', errors='replace')
        end = path.with_suffix('.end').read_text(encoding='utf-8', errors='replace')
        completed = re.search(r"EnergyPlus Completed Successfully--\s*\d+ Warning;\s*0 Severe Errors", err)
        if not completed or "EnergyPlus Completed Successfully" not in end or "**  Fatal" in err:
            raise ValueError(f"Simulation not successfully complete: {path}")
        zones = con.execute("SELECT ZoneName, FloorArea, Multiplier, ListMultiplier FROM Zones").fetchall()
        areas = {name: area for name, area, _, _ in zones if "_CONDITIONED_" in name}
        if not areas or any(mult != 1 or lm != 1 for name, _, mult, lm in zones if name in areas):
            raise ValueError("Unexpected zone multipliers or missing conditioned zones")
        if any(not math.isfinite(a) or a <= 0 for a in areas.values()):
            raise ValueError("Invalid conditioned floor area")
        raw = con.execute(
            "SELECT d.KeyValue,d.Name,d.Units,t.Month,r.Value FROM ReportData r "
            "JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) "
            "JOIN Time t USING(TimeIndex) "
            "JOIN EnvironmentPeriods e USING(EnvironmentPeriodIndex) "
            "WHERE d.Name IN (?,?) AND d.ReportingFrequency='Monthly' "
            "AND t.WarmupFlag=0 AND e.EnvironmentType=3 ORDER BY d.KeyValue,t.Month,d.Name",
            (HEAT, COOL),
        ).fetchall()
        values = {}
        for key, name, units, month, value in raw:
            zone = key.removeprefix("IDEAL_")
            if zone not in areas or units != "J":
                raise ValueError(f"Unexpected output key/unit: {key}/{units}")
            index = (zone, month, name)
            if index in values:
                raise ValueError(f"Duplicate monthly output: {index}")
            values[index] = value
        expected = {(zone, month, metric) for zone in areas for month in range(1, 13) for metric in (HEAT, COOL)}
        if set(values) != expected:
            raise ValueError(f"Expected 12 months for every conditioned zone and metric: {path}")
        monthly = [{"zone": zone, "month": month, "heating_J": values[zone, month, HEAT],
                    "cooling_J": values[zone, month, COOL]}
                   for zone in sorted(areas) for month in range(1, 13)]
        area = math.fsum(areas.values())
        annual_metrics(monthly, area)  # validate finite, nonnegative energies
        return area, monthly
    finally:
        con.close()
