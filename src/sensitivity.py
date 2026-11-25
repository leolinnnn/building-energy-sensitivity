"""Pairwise rank reversals and finite contrasts for deterministic scenarios."""
from __future__ import annotations
import itertools
import math

from .results import METRICS

PROTOTYPES = ("horizontal", "vertical", "hybrid", "north_south")
PANELS = {
    "A": ("wwr_target", "setpoint_pair_C", "total_internal_gains_W_m2"),
    "B": ("wwr_target", "infiltration_ach", "outdoor_air_L_s_m2"),
    "C": ("wwr_target", "wall_xps_thickness_m", "roof_xps_thickness_m"),
}


def pair_status(baseline_gap: float, condition_gap: float, tolerance: float = 0.01) -> str:
    """A near-tie is descriptive, not a numerical or statistical error bound."""
    if tolerance < 0 or not all(math.isfinite(x) for x in (baseline_gap, condition_gap, tolerance)):
        raise ValueError("Finite gaps and a nonnegative threshold are required")
    if abs(baseline_gap) <= tolerance or abs(condition_gap) <= tolerance:
        return "near_tie"
    return "reversal" if baseline_gap * condition_gap < 0 else "same_order"


def compare_conditions(rows: list[dict], tolerance: float = 0.01) -> tuple[dict, list[dict]]:
    baseline = {r['prototype']: r for r in rows if r['group'] == 'baseline'}
    if set(baseline) != set(PROTOTYPES):
        raise ValueError('Four baseline prototypes are required')
    summary, pairs = {}, []
    for group, count in [('ofat', 16), ('factorial', 24)]:
        conditions = {}
        for row in rows:
            if row['group'] == group:
                case = conditions.setdefault(row['condition'], {})
                if row['prototype'] in case:
                    raise ValueError('Duplicate condition/prototype')
                case[row['prototype']] = row
        if len(conditions) != count or any(set(v) != set(PROTOTYPES) for v in conditions.values()):
            raise ValueError(f'Expected {count} complete four-prototype conditions: {group}')
        group_summary = {'condition_count': count, 'metrics': {}}
        for metric in METRICS:
            changed, tied = set(), set()
            for condition, models in sorted(conditions.items()):
                for a, b in itertools.combinations(PROTOTYPES, 2):
                    bg = float(baseline[a][metric]) - float(baseline[b][metric])
                    cg = float(models[a][metric]) - float(models[b][metric])
                    status = pair_status(bg, cg, tolerance)
                    if status == 'reversal':
                        changed.add(condition)
                    if status == 'near_tie':
                        tied.add(condition)
                    pairs.append({'group':group, 'condition':condition, 'metric':metric,
                                  'prototype_a':a, 'prototype_b':b, 'baseline_gap':bg,
                                  'condition_gap':cg, 'status':status})
            group_summary['metrics'][metric] = {
                'conditions_with_reversal': len(changed), 'reversal_conditions': sorted(changed),
                'conditions_with_near_tie': len(tied), 'near_tie_conditions': sorted(tied),
            }
        summary[group] = group_summary
    summary['near_tie_threshold_kWh_per_m2_a'] = tolerance
    return summary, pairs


def factorial_contrasts(rows: list[dict]) -> list[dict]:
    """High-minus-low main effects, averaged 2-way differences and 3-way differences.

    Descriptive finite contrasts of 2^3 designs, not fitted causal effects,
    confidence intervals, or global variance-based sensitivity indices.
    """
    table = {(r['condition'], r['prototype']):r for r in rows if r['group']=='factorial'}
    contrasts = []
    for panel, factors in PANELS.items():
        for prototype in PROTOTYPES:
            for metric in METRICS:
                values = {bits:float(table[panel+''.join(map(str,bits)),prototype][metric])
                          for bits in itertools.product((0,1),repeat=3)}
                for size in (1,2,3):
                    for selected in itertools.combinations(range(3),size):
                        contrast = math.fsum(value * math.prod(1 if bits[i] else -1 for i in selected)
                                             for bits,value in values.items()) / (2 ** (3-size))
                        contrasts.append({'panel':panel,'prototype':prototype,'metric':metric,
                                          'order':size,'factors':' x '.join(factors[i] for i in selected),
                                          'contrast_kWh_per_m2_a':contrast})
    return contrasts
