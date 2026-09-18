import unittest
from gestureflow.engine import Engine, Hand, Pointer


def hand(index=1.0, middle=1.0, fingers=None, y=0.5, thumb=None):
    if fingers is None:
        fingers = (True, False, True, True) if middle < 0.46 else (True,) * 4
    return Hand((0.5, y), index, middle, fingers, any(fingers) if thumb is None else thumb)


def side_click():
    return Hand((0.4, 0.4), 1, 1, (True, False, False, False), False,
                index_tip=(0.5, 0.5), index_side_touch=0.1)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.now = 0.0

    def step(self, pose, dt=0.05):
        self.now += dt
        return self.engine.step(pose, self.now)

    def hold(self, pose, duration=0.5):
        actions = []
        for _ in range(round(duration / 0.05)):
            actions.extend(self.step(pose))
        return actions

    def activate(self):
        self.hold(hand(fingers=(True, False, False, False)))
        self.hold(hand(fingers=(False,) * 4, thumb=False))
        actions = self.hold(hand())
        self.assertIn(('resume',), actions)
        self.assertFalse(self.engine.paused)

    def test_deliberate_fist_open_arms_and_new_open_fist_disarms(self):
        self.assertEqual(self.step(hand()), [])
        self.assertTrue(self.engine.paused)
        self.activate()
        self.hold(hand(fingers=(True, False, False, False)))
        self.hold(hand())
        actions = self.hold(hand(fingers=(False,) * 4))
        self.assertIn(('release_all',), actions)
        self.assertTrue(self.engine.paused)
        self.activate()

    def test_lock_cannot_be_resumed_by_pointing(self):
        self.engine.stop(locked=True)
        self.assertEqual(self.hold(hand(fingers=(True, False, False, False))), [])
        self.assertTrue(self.engine.paused)

    def test_click_drag_one_down_one_up(self):
        self.activate()
        actions = self.hold(side_click(), 0.6)
        self.assertEqual(sum(a[0] == 'left_down' for a in actions), 1)
        self.assertTrue(any(a[0] == 'drag' for a in actions))
        released = self.hold(hand())
        self.assertEqual(released.count(('left_up',)), 1)
        self.assertNotIn(('voice_down',), actions)

    def test_voice_hold_freezes_pointer_and_releases_once(self):
        self.activate()
        actions = self.hold(hand(middle=0.1), 0.6)
        self.assertEqual(actions, [('voice_down',)])
        actions = self.hold(hand())
        self.assertEqual(actions.count(('voice_up',)), 1)

    def test_pinch_hysteresis_and_release_jitter(self):
        self.activate()
        self.hold(hand(middle=0.1))
        self.assertEqual(self.hold(hand(middle=0.38)), [])
        self.assertEqual(self.step(hand(middle=0.6)), [])
        self.assertEqual(self.step(hand(middle=0.2)), [])
        self.assertEqual(self.engine.mode, 'dictate')
        released = self.hold(hand(middle=0.7), 0.25)
        self.assertEqual(released.count(('voice_up',)), 1)
        self.assertEqual(released[0], ('voice_up',))
        self.assertEqual(self.engine.mode, 'idle')

    def test_ambiguous_pinches_do_not_start_either_hold(self):
        self.activate()
        ambiguous = hand(middle=0.17, fingers=(True, False, False, True))
        ambiguous.ring_pinch = 0.15
        actions = self.hold(ambiguous)
        self.assertFalse(any(a[0] in ('left_down', 'voice_down') for a in actions))

    def test_closer_pinch_wins_and_active_hold_has_exclusivity(self):
        self.activate()
        self.assertEqual(self.hold(hand(index=0.25, middle=0.1)), [('voice_down',)])
        self.assertEqual(self.hold(hand(index=0.05, middle=0.2)), [])
        self.assertEqual(self.engine.mode, 'dictate')

    def test_fist_does_not_trigger_pinches(self):
        self.activate()
        actions = self.hold(hand(index=0.1, middle=0.1, fingers=(False,) * 4))
        self.assertFalse(any(a[0] in ('voice_down', 'left_down') for a in actions))
        self.assertFalse(self.engine.paused)

    def test_hand_loss_releases_voice_but_keeps_armed(self):
        self.activate()
        self.hold(hand(middle=0.1))
        actions = self.hold(None)
        self.assertEqual(actions.count(('voice_up',)), 1)
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.hold(hand(middle=0.1, fingers=(True, False, True, True))), [('voice_down',)])

    def test_stall_releases_drag(self):
        self.activate()
        self.hold(side_click())
        actions = self.step(side_click(), 0.8)
        self.assertIn(('left_up',), actions)
        self.assertIn(('release_all',), actions)
        self.assertFalse(self.engine.paused)

    def test_shaka_fires_once_until_released(self):
        self.activate()
        shaka = hand(fingers=(False, False, False, True))
        self.assertEqual(self.hold(shaka, 1.0), [('right_click',)])
        self.hold(hand(), 0.1)
        self.assertEqual(self.hold(shaka, 0.5), [])
        self.hold(hand(), 0.35)
        self.assertEqual(self.hold(shaka), [('right_click',)])

    def test_scroll_has_entry_dwell_and_direction(self):
        self.activate()
        scroll = hand(fingers=(False, False, False, False), thumb=True)
        self.assertEqual(self.hold(scroll, 0.3), [])
        actions = self.step(hand(fingers=scroll.fingers, y=0.42, thumb=True))
        self.assertTrue(actions and actions[0][0] == 'scroll' and actions[0][1] > 0)
        actions = self.step(hand(fingers=scroll.fingers, y=0.58, thumb=True))
        self.assertTrue(actions and actions[0][1] < 0)
        self.step(hand())
        self.assertEqual(self.engine.mode, 'idle')

    def test_sustained_fist_releases_active_holds_without_power_transition(self):
        for pinch, release in [('click', 'left_up'), ('dictate', 'voice_up')]:
            with self.subTest(pinch=pinch):
                self.engine = Engine()
                self.now = 0.0
                self.activate()
                self.hold(side_click() if pinch == 'click' else hand(middle=0.1))
                actions = self.hold(hand(index=0.1, middle=0.1, fingers=(False,) * 4), 0.5)
                self.assertEqual(actions.count((release,)), 1)
                self.assertFalse(self.engine.paused)
                self.assertEqual(self.engine.mode, 'idle')

    def test_thumbs_up_does_not_enter_or_pause_with_folded_fingertips(self):
        self.activate()
        thumbs = hand(index=0.1, middle=0.1, fingers=(False,)*4, thumb=True)
        thumbs.ring_pinch = 0.05
        actions = self.hold(thumbs)
        self.assertEqual(actions, [])
        self.assertEqual(self.engine.mode, 'scroll')
        self.assertFalse(self.engine.paused)

    def test_old_two_finger_pose_no_longer_scrolls(self):
        self.activate()
        actions = self.hold(hand(fingers=(True, True, False, False)))
        actions += self.step(hand(fingers=(True, True, False, False), y=0.3))
        self.assertFalse(any(a[0] == 'scroll' for a in actions))
        self.assertEqual(self.engine.mode, 'idle')

    def test_thumbs_up_returns_to_pointer_or_fist_freeze(self):
        self.activate()
        self.hold(hand(fingers=(False,)*4, thumb=True))
        self.assertIn('move', [a[0] for a in self.step(hand(fingers=(True, False, False, False)))])
        self.hold(hand(fingers=(False,)*4, thumb=True))
        self.hold(hand(fingers=(False,)*4, thumb=False))
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.engine.mode, 'idle')

    def test_brief_fist_does_not_end_hold_and_dwell_resets(self):
        self.activate()
        self.hold(hand(middle=0.1))
        fist = hand(index=0.1, middle=0.1, fingers=(False,) * 4)
        self.assertEqual(self.hold(fist, 0.05), [])
        self.assertEqual(self.step(hand(middle=0.1)), [])
        self.assertEqual(self.hold(fist, 0.05), [])
        self.assertEqual(self.engine.mode, 'dictate')
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.hold(hand(middle=0.1)), [])
    def test_pointer_clamps_to_selected_monitor(self):
        pointer = Pointer()
        pointer.rect = (-1920, 0, 1920, 1080)
        self.assertEqual(pointer.move(-1, -1, 1.0), (-1920, 0))
        pointer.position = None
        self.assertEqual(pointer.move(2, 2, 2.0), (-1, 1079))

    def test_small_lower_workspace_reaches_entire_screen(self):
        pointer = Pointer()
        pointer.rect = (0, 0, 1001, 1001)
        # A small lower-camera range covers the whole screen without raising the arm.
        for palm, expected in [((0.68, 0.58), (0, 0)), ((0.78, 0.68), (500, 500)),
                               ((0.88, 0.78), (1000, 1000))]:
            pointer.position = None
            self.assertEqual(pointer.move(*palm, 1.0), expected)


if __name__ == '__main__':
    unittest.main()


