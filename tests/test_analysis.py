import itertools
import tempfile
import unittest
from pathlib import Path
from run_analysis import reproduce
from src.results import METRICS, annual_metrics
from src.sensitivity import pair_status, factorial_contrasts, PROTOTYPES, PANELS


class NumericalTests(unittest.TestCase):
    def test_units_and_separate_heating_cooling(self):
        result = annual_metrics([{'heating_J':36_000_000,'cooling_J':18_000_000}],5)
        self.assertEqual([result[m] for m in METRICS],[2,1,3])
        for area in (0,-1,float('nan')):
            with self.assertRaises(ValueError):
                annual_metrics([{'heating_J':1,'cooling_J':0}],area)

    def test_near_ties_are_not_reversals(self):
        self.assertEqual(pair_status(1,-2),'reversal')
        self.assertEqual(pair_status(1,-0.01),'near_tie')
        self.assertEqual(pair_status(0,2),'near_tie')
        self.assertEqual(pair_status(-1,-2),'same_order')

    def test_factorial_contrast_scaling(self):
        rows = []
        for panel, prototype, bits in itertools.product(PANELS,PROTOTYPES,itertools.product((0,1),repeat=3)):
            x,y,z = (2*b-1 for b in bits)
            value = 100+2*x+3*x*y+5*x*y*z
            rows.append({'group':'factorial','condition':panel+''.join(map(str,bits)),
                         'prototype':prototype, **dict.fromkeys(METRICS,value)})
        effects = factorial_contrasts(rows)
        first = [r['contrast_kWh_per_m2_a'] for r in effects[:7]]
        self.assertEqual(first,[4,0,0,12,0,0,40])

    def test_archived_results_and_rank_changes(self):
        with tempfile.TemporaryDirectory() as out:
            rows, summary = reproduce(Path(out),check_models=True)
        self.assertEqual(summary['run_count'],170)
        self.assertEqual(summary['group_counts'],{'baseline':4,'geometry':6,'ofat':64,'factorial':96})
        self.assertEqual([summary['ofat']['metrics'][m]['conditions_with_reversal'] for m in METRICS],[0,8,0])
        self.assertEqual([summary['factorial']['metrics'][m]['conditions_with_reversal'] for m in METRICS],[1,20,1])
        self.assertEqual(summary['factorial']['metrics'][METRICS[2]]['reversal_conditions'],['C010'])
        self.assertTrue(all(r[METRICS[1]]==0 for r in rows if r['condition']=='A000'))
        baselines = {r['prototype']:r for r in rows if r['group']=='baseline'}
        self.assertAlmostEqual(baselines['north_south'][METRICS[2]],63.25435161756652,places=10)


if __name__ == '__main__':
    unittest.main()
