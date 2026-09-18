import unittest
from types import SimpleNamespace
from gestureflow.engine import Engine, Hand


def hand(fingers=(True, False, False, False), side=1, tip=(0.7, 0.3), thumb=False, middle=1, ring=1):
    return Hand((0.4, 0.6), 1, middle, fingers, thumb, ring_pinch=ring,
                index_tip=tip, index_side_touch=side)


class SideClickTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.now = 0.0
        self.engine.paused = False

    def hold(self, pose, seconds=0.5):
        actions = []
        for _ in range(round(seconds / 0.02)):
            self.now += 0.02
            actions += self.engine.step(pose, self.now)
        return actions

    def test_side_contact_dwell_click_and_drag_use_tip(self):
        self.assertEqual(self.hold(hand(side=0.1), 0.08), [])
        actions = self.hold(hand(side=0.1), 0.3)
        self.assertEqual(actions[0], ('left_down', 0.7, 0.3))
        actions = self.hold(hand(side=0.1, tip=(0.8, 0.2)), 0.4)
        self.assertTrue(actions)
        self.assertTrue(all(a == ('drag', 0.8, 0.2) for a in actions))
        actions = self.hold(hand(side=0.8))
        self.assertEqual(actions.count(('left_up',)), 1)
        self.assertFalse(self.engine.paused)

    def test_approach_freezes_pointer_before_contact(self):
        self.assertTrue(all(a[0] == 'move' for a in self.hold(hand())))
        self.assertEqual(self.hold(hand(side=0.33)), [])
        self.assertEqual(self.engine.mode, 'idle')
        self.assertEqual(self.hold(hand(side=0.1), 0.2), [('left_down', 0.7, 0.3)])

    def test_side_contact_hysteresis_and_release_jitter(self):
        self.hold(hand(side=0.1))
        self.hold(hand(side=0.25))
        self.assertEqual(self.engine.mode, 'click')
        self.assertEqual(self.hold(hand(side=0.5), 0.06), [])
        self.hold(hand(side=0.1), 0.06)
        self.assertEqual(self.engine.mode, 'click')
        actions = self.hold(hand(side=0.5), 0.2)
        self.assertEqual(actions.count(('left_up',)), 1)

    def test_static_fist_releases_mouse_once_but_does_not_disarm(self):
        self.hold(hand(side=0.1))
        actions = self.hold(hand(fingers=(False,) * 4, side=0.01))
        self.assertEqual(actions.count(('left_up',)), 1)
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.engine.mode, 'idle')

    def test_fist_releases_voice_and_click_without_changing_power(self):
        for pose, release in [(hand(side=0.1), 'left_up'),
                              (hand(fingers=(True, False, True, True), middle=0.1), 'voice_up')]:
            with self.subTest(release=release):
                self.engine = Engine()
                self.engine.paused = False
                self.hold(pose)
                fist = hand(fingers=(False,) * 4, side=0.01, middle=0.01)
                self.assertEqual(self.hold(fist, 0.08), [])
                actions = self.hold(fist, 0.08)
                self.assertEqual(actions, [(release,)])
                self.assertFalse(self.engine.paused)
                self.assertEqual(self.engine.mode, 'idle')
                actions = self.hold(fist, 0.40)
                self.assertEqual(actions, [])
                self.assertFalse(self.engine.paused)

    def test_click_requires_straight_index_and_other_fingers_curled(self):
        for fingers in [(False,) * 4, (True,) * 4, (True, True, False, False)]:
            self.engine = Engine()
            self.engine.paused = False
            actions = self.hold(hand(fingers=fingers, side=0.01))
            self.assertFalse(any(a[0] == 'left_down' for a in actions))

    def test_old_tip_pinch_with_extended_other_fingers_no_longer_clicks(self):
        old = hand(fingers=(False, True, True, True))
        old.index_pinch = 0.01
        old.index_click_shape = True
        self.assertEqual(self.hold(old), [])
        self.assertFalse(self.engine.paused)

    def test_voice_enter_and_shaka_work_without_pointing_first(self):
        for pose, expected in [(hand(fingers=(True, False, True, True), middle=0.1), 'voice_down'),
                               (hand(fingers=(True, True, False, True), ring=0.1), 'enter'),
                               (hand(fingers=(False, False, False, True), thumb=True), 'right_click')]:
            self.engine = Engine()
            self.engine.paused = False
            actions = self.hold(pose)
            self.assertIn((expected,), actions)
            self.assertFalse(self.engine.paused)

    def test_tracking_cleanup_preserves_on_off_and_locked_latches(self):
        for paused, locked in [(False, False), (True, False), (True, True)]:
            self.engine = Engine()
            self.engine.paused, self.engine.locked = paused, locked
            self.engine.mode = 'dictate' if not paused else 'idle'
            actions = self.engine.release_tracking()
            self.assertEqual((self.engine.paused, self.engine.locked), (paused, locked))
            self.assertEqual(self.engine.mode, 'idle')
            if not paused:
                self.assertIn(('voice_up',), actions)

    def test_loss_releases_mouse_and_new_gesture_works_without_rearming(self):
        self.hold(hand(side=0.1))
        actions = self.hold(None)
        self.assertIn(('left_up',), actions)
        self.assertFalse(self.engine.paused)
        actions = self.hold(hand(fingers=(True, False, True, True), middle=0.1))
        self.assertEqual(actions, [('voice_down',)])

    def test_finger_gun_never_starts_tool_even_if_tucked_finger_nearer_thumb(self):
        pose = hand(side=0.25, middle=0.02, ring=0.02)
        self.assertEqual(self.hold(pose), [])
        self.assertEqual(self.engine.mode, 'idle')
        self.assertFalse(self.engine.paused)

    def test_side_click_wins_when_tool_contact_is_not_clearly_closer(self):
        actions = self.hold(hand(side=0.1, middle=0.08, ring=0.09), 0.2)
        self.assertEqual(actions, [('left_down', 0.7, 0.3)])


class SideGeometryTests(unittest.TestCase):
    def test_distance_uses_segment_interior_and_clamped_endpoints(self):
        distance = Hand.point_segment_distance
        self.assertAlmostEqual(distance((0.2, 0.5), (0, 0), (0, 1)), 0.2)
        self.assertAlmostEqual(distance((0, 2), (0, 0), (0, 1)), 1)
        self.assertAlmostEqual(distance((0, -1), (0, 0), (0, 1)), 1)
        self.assertAlmostEqual(distance((3, 4), (0, 0), (0, 0)), 5)

    def test_fingertip_contact_is_not_side_segment_contact(self):
        # Tip8 lies above DIP7; measuring only MCP/PIP/DIP excludes the tip.
        thumb = (0, 0)
        side = min(Hand.point_segment_distance(thumb, (0, 1), (0, 0.6)),
                   Hand.point_segment_distance(thumb, (0, 0.6), (0, 0.3)))
        self.assertAlmostEqual(side, 0.3)


if __name__ == '__main__':
    unittest.main()
