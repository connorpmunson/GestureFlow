import unittest
from types import SimpleNamespace
from gestureflow.calibration import Calibration

class CalibrationTests(unittest.TestCase):
    def run_positions(self, positions):
        cal = Calibration()
        now = 0
        for position in positions:
            phase = cal.phase
            hand = SimpleNamespace(fingers=(True,False,False,False),index_tip=position)
            for _ in range(100):
                now += .05
                cal.update(hand,now)
                if cal.phase != phase:
                    break
        return cal

    def test_five_comfortable_positions_produce_bounds(self):
        cal=self.run_positions([(.7,.7),(.5,.7),(.9,.7),(.7,.65),(.7,.78)])
        self.assertEqual(cal.result,(.5,.65,.9,.78))
        self.assertTrue(cal.finished)

    def test_missing_hand_does_not_record_or_advance(self):
        cal=Calibration()
        for time in range(100):
            cal.update(None,time)
        self.assertEqual(cal.phase,0)
        self.assertIsNone(cal.result)

    def test_open_palm_does_not_calibrate(self):
        cal=Calibration()
        for time in range(100):
            cal.update(SimpleNamespace(fingers=(True,)*4,index_tip=(.5,.5)),time)
        self.assertEqual(cal.phase,0)

    def test_invalid_small_or_reversed_ranges_are_not_saved(self):
        for points in [[(.5,.5)]*5,[(.5,.5),(.8,.5),(.2,.5),(.5,.3),(.5,.8)]]:
            cal=self.run_positions(points)
            self.assertIsNone(cal.result)
            self.assertTrue(cal.error)

    def test_center_outside_extremes_is_rejected(self):
        cal=self.run_positions([(.1,.1),(.4,.5),(.8,.5),(.5,.4),(.5,.8)])
        self.assertIsNone(cal.result)
        self.assertTrue(cal.error)

if __name__ == '__main__':
    unittest.main()
