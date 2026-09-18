import unittest
from gestureflow.engine import Engine, Hand, Pointer


def pointing(tip=(0.7, 0.6)):
    return Hand((0.4, 0.4), 1, 1, (True, False, False, False), False, index_tip=tip)


def curled_click(shape=True):
    return Hand((0.4, 0.4), 0.1, 1, (False,) * 4, False,
                index_tip=(0.5, 0.5), index_click_shape=shape)


class PointingTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.now = 0.0

    def hold(self, hand, seconds=0.5):
        actions = []
        for _ in range(round(seconds / 0.02)):
            self.now += 0.02
            actions += self.engine.step(hand, self.now)
        return actions

    def activate(self):
        self.hold(Hand((0.4, 0.4), 1, 1, (False,) * 4, False))
        self.hold(Hand((0.4, 0.4), 1, 1, (True,) * 4, True))
        self.assertFalse(self.engine.paused)

    def test_pointing_never_arms_but_moves_tip_after_deliberate_transition(self):
        self.assertEqual(self.hold(pointing()), [])
        self.assertTrue(self.engine.paused)
        self.activate()
        actions = self.hold(pointing())
        self.assertIn(('move', 0.7, 0.6), actions)
        self.assertNotIn(('move', 0.4, 0.4), actions)
        self.assertEqual(self.hold(Hand((0.4, 0.4), 1, 1, (True,) * 4, True)), [])
        self.assertFalse(self.engine.paused)

    def test_other_extended_fingers_freeze_pointer_without_disarming(self):
        self.activate()
        for fingers in [(True, True, False, False), (True,) * 4, (False, True, True, False)]:
            self.assertEqual(self.hold(Hand((0.4, 0.4), 1, 1, fingers, True)), [])
            self.assertFalse(self.engine.paused)

    def test_old_curled_index_tip_pinch_never_clicks(self):
        self.activate()
        self.hold(pointing())
        self.assertFalse(any(a[0] == 'left_down' for a in self.hold(curled_click())))
        self.assertFalse(self.engine.paused)

    def test_thumb_resting_on_folded_middle_or_ring_does_not_activate(self):
        self.activate()
        resting = pointing()
        resting.middle_pinch = 0.1
        resting.ring_pinch = 0.12
        resting.middle_pinch_shape = False
        resting.ring_pinch_shape = False
        actions = self.hold(resting)
        self.assertTrue(all(a[0] == 'move' for a in actions))
        self.assertTrue(actions)

    def test_tracking_loss_preserves_armed_latch_and_pointing_returns_immediately(self):
        self.activate()
        self.hold(None)
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.hold(pointing(), 0.02), [('move', 0.7, 0.6)])
        self.engine.stop()
        self.hold(None)
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.hold(pointing()), [])


class PointerBoundsTests(unittest.TestCase):
    def assertBounds(self, pointer, expected):
        for actual, want in zip(pointer.bounds(), expected):
            self.assertAlmostEqual(actual, want)

    def test_independent_gains_shrink_each_axis_around_same_center(self):
        pointer = Pointer()
        pointer.gain_x = 2
        pointer.gain_y = 0.5
        self.assertBounds(pointer, (0.73, 0.48, 0.83, 0.88))
        pointer.rect = (0, 0, 1001, 1001)
        for tip, expected in [((0.73, 0.48), (0, 0)), ((0.78, 0.68), (500, 500)), ((0.83, 0.88), (1000, 1000))]:
            pointer.position = None
            self.assertEqual(pointer.move(*tip, 1.0), expected)

    def test_calibrated_bounds_are_base_area_then_gains_apply(self):
        pointer = Pointer()
        pointer.calibrated_bounds = (0.2, 0.3, 0.8, 0.7)
        self.assertBounds(pointer, (0.2, 0.3, 0.8, 0.7))
        pointer.gain_x = 2
        pointer.gain_y = 2
        self.assertBounds(pointer, (0.35, 0.4, 0.65, 0.6))

    def test_effective_bounds_stay_inside_camera_even_at_edges(self):
        pointer = Pointer()
        pointer.center_x = 0.99
        pointer.center_y = 0.01
        pointer.gain_x = 0.5
        pointer.gain_y = 0.5
        self.assertBounds(pointer, (0.6, 0.0, 1.0, 0.4))

    def test_drag_uses_independent_calibrated_spans(self):
        pointer = Pointer()
        pointer.rect = (0, 0, 1000, 1000)
        pointer.calibrated_bounds = (0.2, 0.2, 0.8, 0.8)
        pointer.gain_x = 2
        pointer.gain_y = 1
        pointer.start_drag(0.5, 0.5, (500, 500))
        self.assertEqual(pointer.drag(0.53, 0.53), (540, 520))


if __name__ == '__main__':
    unittest.main()
