"""Geometry-to-IDF implementation adapted from build_exploratory_idfs.py.

The geometry and object-generation algorithms are retained. Local-only paths,
archive gates and the original CLI were replaced by repository-relative inputs.
See PROVENANCE.md for source hashes and adaptation details.
"""
from __future__ import annotations
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
import shapely
from shapely.geometry import Point, Polygon, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data/geometry/floor_categories_m.geojson"
AREA_QA = ROOT / "reference/geometry/floor_geometry_qa.csv"
PROTOTYPES = ("horizontal", "vertical", "hybrid", "north_south")
LEVELS = ("B1", "F1", "F2", "F3")
EPS_AREA = 1e-5
EPS_LINE = 1e-4
MIN_EP_EDGE = 0.01
PRECISION_GRID_M = 0.001
SOLAR_DISTRIBUTION_OVERRIDE = "FullExterior"

def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > EPS_AREA else []
    if hasattr(geometry, "geoms"):
        out = []
        for item in geometry.geoms:
            out.extend(polygons(item))
        return out
    return []


def segments(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type in {"LineString", "LinearRing"}:
        coords = list(geometry.coords)
        return [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)
                if Point(coords[i]).distance(Point(coords[i + 1])) > EPS_LINE]
    if hasattr(geometry, "geoms"):
        out = []
        for item in geometry.geoms:
            out.extend(segments(item))
        return out
    return []


def triangles(geometry):
    out = []
    rejected = []
    for poly in polygons(geometry):
        for triangle in shapely.constrained_delaunay_triangles(poly).geoms:
            if triangle.area > EPS_AREA:
                vertices = list(triangle.exterior.coords)[:-1]
                shortest = min(math.dist(vertices[i], vertices[(i + 1) % 3]) for i in range(3))
                (rejected if shortest < MIN_EP_EDGE else out).append(orient(triangle, sign=1.0))
    area = sum(p.area for p in out)
    assert abs(area + sum(p.area for p in rejected) - geometry.area) < max(0.01, 1e-7 * geometry.area), "triangulation error"
    assert sum(p.area for p in rejected) < 0.05, "sliver removal area too large"
    return out, rejected


def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) < 0.0000005:
            value = 0.0
        return f"{value:.6f}".rstrip("0").rstrip(".") if value else "0"
    return str(value)


def obj(kind: str, *fields) -> str:
    assert all(";" not in fmt(f) and "\n" not in fmt(f) for f in fields)
    return kind + ",\n  " + ",\n  ".join(fmt(f) for f in fields) + ";\n"


def xyz(poly: Polygon, z: float, upwards: bool):
    ring = list(orient(poly, sign=1.0).exterior.coords)[:-1]
    if not upwards:
        ring.reverse()
    return [(x, y, z) for x, y in ring]


def outward_segment(poly: Polygon, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    assert length > EPS_LINE
    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    step = min(0.001, length / 1000)
    right = Point(midpoint[0] + dy / length * step,
                  midpoint[1] - dx / length * step)
    if poly.contains(right):
        return b, a
    return a, b


def wall_vertices(a, b, z0, height):
    return [(a[0], a[1], z0), (b[0], b[1], z0),
            (b[0], b[1], z0 + height), (a[0], a[1], z0 + height)]


def bearing(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    nx, ny = dy, -dx
    if abs(ny) >= abs(nx):
        return "N" if ny >= 0 else "S"
    return "E" if nx >= 0 else "W"


@dataclass(frozen=True)
class Zone:
    name: str
    prototype: str
    level: str
    category: str
    poly: Polygon

    @property
    def conditioned(self):
        return self.category == "CONDITIONED_VIRTUAL"


def load_zones():
    raw = json.loads(GEO.read_text(encoding="utf-8"))
    by_prototype = {p: [] for p in PROTOTYPES}
    area_delta = {p: 0.0 for p in PROTOTYPES}
    for feature in raw["features"]:
        props = feature["properties"]
        if props["category"] == "OUTDOOR_ROOF_CORRIDOR_OR_VOID":
            continue
        p, level = props["prototype_id"], props["level"]
        source = shape(feature["geometry"])
        snapped = shapely.set_precision(source, grid_size=PRECISION_GRID_M, mode="valid_output")
        area_delta[p] += snapped.area - source.area
        for index, poly in enumerate(polygons(snapped), 1):
            assert poly.is_valid and poly.area > EPS_AREA
            name = f"Z_{p.upper()}_{level}_{props['category'].split('_')[0]}_{index}"
            by_prototype[p].append(Zone(name, p, level, props["category"], orient(poly, sign=1.0)))
    assert all(by_prototype.values())
    return by_prototype, area_delta


def expected_areas():
    with AREA_QA.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 16
    return {(r["prototype_id"], r["level"]): float(r["conditioned_virtual_m2"]) for r in rows}


class Model:
    def __init__(self, prototype, zones, params):
        self.prototype, self.zones, self.params = prototype, zones, params
        self.surfaces = []
        self.windows = []
        self.next_id = 0
        self.floor_area = {z.name: 0.0 for z in zones}
        self.top_area = {z.name: 0.0 for z in zones}
        self.wall_length = {z.name: 0.0 for z in zones}
        self.wwr = {d: {"wall_m2": 0.0, "window_m2": 0.0} for d in "NESW"}
        self.foundation_floors = []
        self.skipped_sliver_count = 0
        self.skipped_sliver_area_m2 = 0.0

    def triangulate(self, geometry):
        accepted, rejected = triangles(geometry)
        self.skipped_sliver_count += len(rejected)
        self.skipped_sliver_area_m2 += sum(p.area for p in rejected)
        return accepted

    def name(self, prefix="S"):
        self.next_id += 1
        return f"{prefix}{self.next_id:06d}"

    def add_surface(self, zone, surface_type, construction, bc, mate, vertices,
                    sun="NoSun", wind="NoWind", area=None):
        name = self.name()
        record = dict(name=name, zone=zone.name, type=surface_type, construction=construction,
                      bc=bc, mate=mate or "", vertices=vertices, sun=sun, wind=wind,
                      area_m2=area)
        self.surfaces.append(record)
        if surface_type == "Floor":
            self.floor_area[zone.name] += area
        elif surface_type in {"Roof", "Ceiling"}:
            self.top_area[zone.name] += area
        else:
            self.wall_length[zone.name] += area / self.params["geometry"]["story_height_m"]
        return record

    def pair(self, zone_a, zone_b, kind_a, kind_b, vertices_a, vertices_b, area):
        name_a, name_b = self.name(), self.name()
        for name, zone, kind, verts, mate in ((name_a, zone_a, kind_a, vertices_a, name_b),
                                              (name_b, zone_b, kind_b, vertices_b, name_a)):
            self.surfaces.append(dict(name=name, zone=zone.name, type=kind,
                                      construction="C_INTER_SLAB" if kind != "Wall" else "C_INTER_WALL",
                                      bc="Surface", mate=mate, vertices=verts,
                                      sun="NoSun", wind="NoWind", area_m2=area))
            if kind == "Floor":
                self.floor_area[zone.name] += area
            elif kind in {"Roof", "Ceiling"}:
                self.top_area[zone.name] += area
            else:
                self.wall_length[zone.name] += area / self.params["geometry"]["story_height_m"]

    def build_horizontal(self):
        heights = self.params["geometry"]["story_bottom_elevation_m"]
        h = self.params["geometry"]["story_height_m"]
        for index, level in enumerate(LEVELS):
            lower = [z for z in self.zones if z.level == level]
            if not lower:
                continue
            upper = [z for z in self.zones if index < 3 and z.level == LEVELS[index + 1]]
            used_lower = {z.name: [] for z in lower}
            used_upper = {z.name: [] for z in upper}
            for zlo in lower:
                for zup in upper:
                    overlap = zlo.poly.intersection(zup.poly)
                    if overlap.area <= EPS_AREA:
                        continue
                    used_lower[zlo.name].append(overlap)
                    used_upper[zup.name].append(overlap)
                    for tri in self.triangulate(overlap):
                        self.pair(zlo, zup, "Ceiling", "Floor",
                                  xyz(tri, heights[level] + h, True),
                                  xyz(tri, heights[level] + h, False), tri.area)
            for zlo in lower:
                covered = unary_union(used_lower[zlo.name]) if used_lower[zlo.name] else Polygon()
                exposed = zlo.poly.difference(covered)
                for tri in self.triangulate(exposed):
                    self.add_surface(zlo, "Roof", "C_ROOF", "Outdoors", "",
                                     xyz(tri, heights[level] + h, True),
                                     "SunExposed", "WindExposed", tri.area)
            for zup in upper:
                covered = unary_union(used_upper[zup.name]) if used_upper[zup.name] else Polygon()
                exposed = zup.poly.difference(covered)
                for tri in self.triangulate(exposed):
                    self.add_surface(zup, "Floor", "C_EXPOSED_FLOOR", "Outdoors", "",
                                     xyz(tri, heights[LEVELS[index + 1]], False),
                                     "NoSun", "WindExposed", tri.area)
        for zone in (z for z in self.zones if z.level == "B1"):
            assert not zone.poly.interiors, "Kiva basement floor cannot have holes"
            assert len(list(zone.poly.exterior.coords)) == 5, "Kiva pilot requires quadrilateral B1"
            foundation_name = "FND_" + zone.name
            record = self.add_surface(zone, "Floor", "C_BASEMENT_SLAB", "Foundation",
                                      foundation_name, xyz(zone.poly, heights["B1"], False),
                                      area=zone.poly.area)
            self.foundation_floors.append((record["name"], foundation_name))

    def build_walls(self):
        heights = self.params["geometry"]["story_bottom_elevation_m"]
        h = self.params["geometry"]["story_height_m"]
        target = self.params["fenestration_analyst_assumptions"]["wwr_target"]
        for level in LEVELS:
            zones = [z for z in self.zones if z.level == level]
            shared = {z.name: [] for z in zones}
            for i, za in enumerate(zones):
                for zb in zones[i + 1:]:
                    assert za.poly.intersection(zb.poly).area < EPS_AREA, "same-floor zone overlap"
                    common = za.poly.boundary.intersection(zb.poly.boundary)
                    if common.length <= EPS_LINE:
                        continue
                    shared[za.name].append(common)
                    shared[zb.name].append(common)
                    for a, b in segments(common):
                        aa, bb = outward_segment(za.poly, a, b)
                        area = math.dist(aa, bb) * h
                        self.pair(za, zb, "Wall", "Wall",
                                  wall_vertices(aa, bb, heights[level], h),
                                  wall_vertices(bb, aa, heights[level], h), area)
            for zone in zones:
                internal = unary_union(shared[zone.name]) if shared[zone.name] else None
                boundary = zone.poly.boundary.difference(internal) if internal is not None else zone.poly.boundary
                for a, b in segments(boundary):
                    aa, bb = outward_segment(zone.poly, a, b)
                    length = math.dist(aa, bb)
                    bc = "Foundation" if level == "B1" else "Outdoors"
                    mate = "FND_" + zone.name if bc == "Foundation" else ""
                    surface = self.add_surface(zone, "Wall",
                                               "C_BASEMENT_WALL" if bc == "Foundation" else "C_EXT_WALL",
                                               bc, mate, wall_vertices(aa, bb, heights[level], h),
                                               "NoSun" if bc == "Foundation" else "SunExposed",
                                               "NoWind" if bc == "Foundation" else "WindExposed",
                                               length * h)
                    if bc == "Outdoors" and zone.conditioned:
                        direction = bearing(aa, bb)
                        self.wwr[direction]["wall_m2"] += length * h
                        if target > 0:
                            assert length > 0.2, f"eligible window wall too short: {zone.name} {length}"
                            left = (aa[0] + 0.1 * (bb[0] - aa[0]), aa[1] + 0.1 * (bb[1] - aa[1]))
                            right = (aa[0] + 0.9 * (bb[0] - aa[0]), aa[1] + 0.9 * (bb[1] - aa[1]))
                            win_h = target * h / 0.8
                            sill = 1.2
                            assert sill + win_h < h - 0.2
                            vertices = wall_vertices(left, right, heights[level] + sill, win_h)
                            self.windows.append(dict(name=self.name("W"), base=surface["name"],
                                                     vertices=vertices, area_m2=target * length * h))
                            self.wwr[direction]["window_m2"] += target * length * h

    def validate(self, expected):
        h = self.params["geometry"]["story_height_m"]
        for zone in self.zones:
            tolerance = max(0.1, zone.poly.area * 0.001)
            assert abs(self.floor_area[zone.name] - zone.poly.area) <= tolerance, f"floor area mismatch {zone.name}"
            assert abs(self.top_area[zone.name] - zone.poly.area) <= tolerance, f"roof area mismatch {zone.name}"
            assert abs(self.wall_length[zone.name] - zone.poly.length) <= 0.01, f"wall perimeter mismatch {zone.name}"
            assert zone.poly.area * h > 0
        for level in LEVELS:
            actual = sum(z.poly.area for z in self.zones if z.level == level and z.conditioned)
            target = expected[(self.prototype, level)]
            assert abs(actual - target) <= max(0.1, target * 0.001), f"QA area mismatch {self.prototype}/{level}"
        names = {s["name"] for s in self.surfaces}
        assert len(names) == len(self.surfaces)
        by_name = {s["name"]: s for s in self.surfaces}
        for surface in self.surfaces:
            if surface["bc"] == "Surface":
                mate = by_name[surface["mate"]]
                assert mate["mate"] == surface["name"] and mate["bc"] == "Surface"
                assert abs(mate["area_m2"] - surface["area_m2"]) < EPS_AREA
            assert surface["area_m2"] > EPS_AREA
        for direction, values in self.wwr.items():
            if values["wall_m2"]:
                ratio = values["window_m2"] / values["wall_m2"]
                assert abs(ratio - self.params["fenestration_analyst_assumptions"]["wwr_target"]) <= 0.02, direction
        assert len(self.foundation_floors) == len([z for z in self.zones if z.level == "B1"])
        assert self.skipped_sliver_area_m2 < 0.05

    def idf(self, input_hashes):
        p = self.params
        height = p["geometry"]["story_height_m"]
        air = p["air_and_operation_analyst_assumptions"]
        glass = p["fenestration_analyst_assumptions"]
        mat = p["materials_analyst_assumptions"]
        soil = p["foundation_analyst_assumptions"]
        lines = ["! EXPLORATORY ANALYST SCENARIO ONLY. Not an as-built energy-station model.\n",
                 f"! geometry_sha256={input_hashes['CONDITIONAL_GEOMETRY']}\n",
                 f"! parameter_sha256={input_hashes['COMMON_PARAMETERS']}\n",
                 f"! weather_sha256={input_hashes['COMMON_WEATHER']}\n",
                 f"! solar_distribution_override={SOLAR_DISTRIBUTION_OVERRIDE}; frozen M02 base={p['simulation']['solar_distribution']}\n"]
        add = lambda kind, *fields: lines.append(obj(kind, *fields))
        add("Version", "26.1")
        add("SimulationControl", "No", "No", "No", "No", "Yes")
        add("Building", "ICCESB_" + self.prototype, 0, "Suburbs", 0.04, 0.4,
            SOLAR_DISTRIBUTION_OVERRIDE, 25, 6)
        add("Timestep", p["simulation"]["timestep_per_hour"])
        add("Site:Location", "Taiyuan_CSWD", 37.78, 112.55, 8, 778.3)
        add("RunPeriod", "Annual", 1, 1, "", 12, 31, "")
        add("GlobalGeometryRules", "UpperLeftCorner", "CounterClockWise", "World")
        add("ScheduleTypeLimits", "Fraction", 0, 1, "Continuous")
        add("ScheduleTypeLimits", "Temperature", -60, 80, "Continuous", "Temperature")
        add("ScheduleTypeLimits", "ThermostatControl", 0, 4, "Discrete")
        add("Schedule:Constant", "AlwaysOne", "Fraction", 1)
        add("Schedule:Constant", "Heat20", "Temperature", air["heating_setpoint_C"])
        add("Schedule:Constant", "Cool26", "Temperature", air["cooling_setpoint_C"])
        add("Schedule:Constant", "DualControl", "ThermostatControl", 4)
        add("ThermostatSetpoint:DualSetpoint", "DualSetpoint", "Heat20", "Cool26")
        add("DesignSpecification:OutdoorAir", "OA_PerArea", "Flow/Area", 0,
            air["conditioned_outdoor_air_L_s_m2"] / 1000, 0, 0, "AlwaysOne")

        def material(name, thickness, properties):
            add("Material", name, "Rough", thickness, properties["conductivity_W_mK"],
                properties["density_kg_m3"], properties["specific_heat_J_kgK"],
                mat["exterior_thermal_absorptance"], mat["exterior_solar_absorptance"],
                mat["exterior_solar_absorptance"])

        material("CONCRETE_20", 0.2, mat["concrete"])
        material("CONCRETE_30", 0.3, mat["concrete"])
        for cm in (5, 8, 10):
            material(f"XPS_{cm:02d}", cm / 100, mat["xps"])
        for name, layers in (
            ("C_EXT_WALL", ("XPS_08", "CONCRETE_20")),
            ("C_ROOF", ("XPS_10", "CONCRETE_20")),
            ("C_EXPOSED_FLOOR", ("XPS_08", "CONCRETE_20")),
            ("C_BASEMENT_WALL", ("XPS_08", "CONCRETE_20")),
            ("C_BASEMENT_SLAB", ("XPS_05", "CONCRETE_30")),
            ("C_INTER_WALL", ("CONCRETE_20",)),
            ("C_INTER_SLAB", ("CONCRETE_20",)),
        ):
            add("Construction", name, *layers)
        add("WindowMaterial:SimpleGlazingSystem", "GLAZING_VIRTUAL",
            glass["u_factor_W_m2K"], glass["shgc"], glass["visible_transmittance"])
        add("Construction", "C_WINDOW", "GLAZING_VIRTUAL")
        add("Foundation:Kiva:Settings", soil["soil_conductivity_W_mK"],
            soil["soil_density_kg_m3"], soil["soil_specific_heat_J_kgK"])
        for floor_name, fnd_name in self.foundation_floors:
            add("Foundation:Kiva", *([fnd_name] + [""] * 11 + [0]))
            add("SurfaceProperty:ExposedFoundationPerimeter", floor_name,
                "ExposedPerimeterFraction", "", 1)

        for zone in self.zones:
            add("Zone", zone.name, 0, 0, 0, 0, 1, 1, height,
                zone.poly.area * height, zone.poly.area, "", "", "Yes" if zone.conditioned else "No")
            add("ZoneInfiltration:DesignFlowRate", "INF_" + zone.name, zone.name,
                "AlwaysOne", "AirChanges/Hour", "", "", "",
                air["conditioned_zone_infiltration_ach"] if zone.conditioned else air["unconditioned_zone_infiltration_ach"],
                *air["infiltration_coefficients_A_B_C_D"], "Outdoor")
            if not zone.conditioned:
                continue
            add("ZoneControl:Thermostat", "TC_" + zone.name, zone.name, "DualControl",
                "ThermostatSetpoint:DualSetpoint", "DualSetpoint")
            add("Lights", "LGT_" + zone.name, zone.name, "AlwaysOne", "Watts/Area",
                "", air["lighting_W_m2"], "", 0, 0, 0, 1)
            add("ElectricEquipment", "EQP_" + zone.name, zone.name, "AlwaysOne",
                "Watts/Area", "", air["electric_equipment_W_m2"], "", 0, 0, 0)
            supply, exhaust, return_node, zone_air = (zone.name + suffix for suffix in
                                                      ("_SUPPLY", "_EXHAUST", "_RETURN", "_AIR"))
            oa_node = zone.name + "_OUTDOOR_AIR"
            add("OutdoorAir:Node", oa_node)
            add("ZoneHVAC:IdealLoadsAirSystem", "IDEAL_" + zone.name,
                "AlwaysOne", supply, exhaust, "", 50, 13, 0.0156, 0.0077,
                "NoLimit", "", "", "NoLimit", "", "", "", "", "None", "",
                "None", "OA_PerArea", oa_node, "None", "NoEconomizer", "None", "", "")
            add("ZoneHVAC:EquipmentList", "EQLIST_" + zone.name, "SequentialLoad",
                "ZoneHVAC:IdealLoadsAirSystem", "IDEAL_" + zone.name, 1, 1, "", "")
            add("ZoneHVAC:EquipmentConnections", zone.name, "EQLIST_" + zone.name,
                supply, exhaust, zone_air, return_node)

        for surface in self.surfaces:
            verts = [coordinate for vertex in surface["vertices"] for coordinate in vertex]
            add("BuildingSurface:Detailed", surface["name"], surface["type"],
                surface["construction"], surface["zone"], "", surface["bc"],
                surface["mate"], surface["sun"], surface["wind"], "", len(surface["vertices"]), *verts)
        for window in self.windows:
            verts = [coordinate for vertex in window["vertices"] for coordinate in vertex]
            add("FenestrationSurface:Detailed", window["name"], "Window", "C_WINDOW",
                window["base"], "", "", "", 1, 4, *verts)

        add("Output:VariableDictionary", "Regular")
        add("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Heating Energy", "Monthly")
        add("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Cooling Energy", "Monthly")
        add("Output:Variable", "*", "Zone Mean Air Temperature", "Monthly")
        add("Output:Variable", "*", "Zone Mean Air Temperature", "Timestep")
        add("Output:Variable", "*", "Zone Air Humidity Ratio", "Timestep")
        add("Output:Variable", "*", "Site Outdoor Air Drybulb Temperature", "Timestep")
        add("Output:Variable", "*", "Site Outdoor Air Wetbulb Temperature", "Timestep")
        add("Output:Variable", "*", "Zone Air System Sensible Heating Rate", "Hourly")
        add("Output:Variable", "*", "Zone Air System Sensible Cooling Rate", "Hourly")
        add("Output:SQLite", "SimpleAndTabular")
        add("Output:Table:SummaryReports", "AllSummary")
        add("Output:Diagnostics", "DisplayExtraWarnings")
        return "\n".join(lines)

    def audit(self):
        return {
            "prototype": self.prototype,
            "status": "STATIC_QA_ONLY_NOT_ENERGYPLUS_VERIFIED",
            "solar_distribution_override": SOLAR_DISTRIBUTION_OVERRIDE,
            "zone_count": len(self.zones),
            "conditioned_zone_count": sum(z.conditioned for z in self.zones),
            "unconditioned_zone_count": sum(not z.conditioned for z in self.zones),
            "conditioned_area_m2": sum(z.poly.area for z in self.zones if z.conditioned),
            "surface_count": len(self.surfaces),
            "paired_surface_count": sum(s["bc"] == "Surface" for s in self.surfaces),
            "foundation_surface_count": sum(s["bc"] == "Foundation" for s in self.surfaces),
            "window_count": len(self.windows),
            "sub_1cm_sliver_triangles_discarded": self.skipped_sliver_count,
            "sub_1cm_sliver_area_discarded_m2": self.skipped_sliver_area_m2,
            "wwr_by_cardinal_direction": {
                k: (v["window_m2"] / v["wall_m2"] if v["wall_m2"] else None)
                for k, v in self.wwr.items()
            },
            "floor_area_check_m2": self.floor_area,
            "ceiling_roof_area_check_m2": self.top_area,
            "wall_perimeter_check_m": self.wall_length,
        }
