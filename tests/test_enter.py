"""Enter gesture regression tests; all operating-system input is mocked."""
import unittest
from unittest.mock import Mock
from gestureflow.engine import Engine, Hand
from gestureflow.broker import InputOwner


def pose(middle=1.0, ring=1.0, fingers=None):
    if fingers is None:
        fingers = ((True, False, True, True) if middle < 0.46 else
                   (True, True, False, True) if ring < 0.46 else (True,) * 4)
    return Hand((0.5, 0.5), 1, middle, fingers, any(fingers), ring_pinch=ring)


class EnterEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.now = 0.0
        self.hold(pose())

    def hold(self, hand, duration=0.5):
        actions = []
        for _ in range(round(duration / 0.02)):
            self.now += 0.02
            actions.extend(self.engine.step(hand, self.now))
        return actions

    def test_enter_requires_dwell_and_fires_once_per_hold(self):
        self.assertEqual(self.hold(pose(ring=0.1), 0.14), [])
        self.assertEqual(self.hold(pose(ring=0.1)), [('enter',)])
        self.assertEqual(self.hold(pose(ring=0.1), 1.0), [])
        self.hold(pose(), 0.3)
        self.assertEqual(self.hold(pose(ring=0.1)), [('enter',)])

    def test_enter_hysteresis_and_brief_invalid_pose(self):
        self.hold(pose(ring=0.1))
        self.assertEqual(self.hold(pose(ring=0.38)), [])
        self.assertEqual(self.hold(pose(), 0.06), [])
        self.assertEqual(self.hold(pose(ring=0.1)), [])
        self.assertEqual(self.engine.mode, 'enter')
        self.hold(pose())
        self.assertEqual(self.engine.mode, 'idle')

    def test_two_curled_tool_fingers_trigger_neither_tool(self):
        self.assertEqual(self.hold(pose(middle=0.1, ring=0.1, fingers=(True, False, False, True))), [])

    def test_recording_releases_before_enter_can_fire(self):
        self.assertEqual(self.hold(pose(middle=0.1)), [('voice_down',)])
        actions = self.hold(pose(ring=0.1), 0.6)
        self.assertEqual(actions, [('voice_up',), ('enter',)])

    def test_click_releases_before_enter_can_fire(self):
        contact = pose(fingers=(True, False, False, False))
        contact.index_side_touch = 0.1
        self.hold(contact)
        self.assertEqual(self.hold(pose(ring=0.1), 0.6), [('left_up',), ('enter',)])

    def test_fist_loss_and_lock_end_enter_without_repeating(self):
        for reason in ('fist', 'loss', 'lock'):
            self.engine = Engine()
            self.hold(pose())
            self.assertEqual(self.hold(pose(ring=0.1)), [('enter',)])
            if reason == 'lock':
                actions = self.engine.stop(locked=True) + self.hold(pose(ring=0.1))
            else:
                actions = self.hold(None if reason == 'loss' else pose(ring=0.1, fingers=(False,) * 4))
            self.assertNotIn(('enter',), actions)
            self.assertEqual(self.engine.paused, reason != 'loss')
            self.assertEqual(self.engine.mode, 'idle')

    def test_tool_pose_requires_all_other_three_fingers_extended(self):
        for tool, valid in [('voice', (True, False, True, True)), ('enter', (True, True, False, True))]:
            for finger in (n for n, raised in enumerate(valid) if raised):
                fingers = list(valid)
                fingers[finger] = False
                invalid = pose(middle=0.1 if tool == 'voice' else 1,
                               ring=0.1 if tool == 'enter' else 1, fingers=tuple(fingers))
                self.assertEqual(self.hold(invalid), [])
                self.assertEqual(self.engine.mode, 'idle')

    def test_curling_extra_finger_ends_voice_after_debounce(self):
        self.hold(pose(middle=0.1))
        invalid = pose(middle=0.1, fingers=(True, False, False, True))
        self.assertEqual(self.hold(invalid, 0.06), [])
        self.assertEqual(self.hold(pose(middle=0.1), 0.06), [])
        self.assertEqual(self.hold(invalid, 0.2), [('voice_up',)])
        self.assertFalse(self.engine.paused)

    def test_curling_extra_finger_ends_enter_and_allows_rearm(self):
        self.hold(pose(ring=0.1))
        self.hold(pose(ring=0.1, fingers=(True, False, False, True)), 0.2)
        self.assertEqual(self.engine.mode, 'idle')
        self.assertEqual(self.hold(pose(ring=0.1)), [('enter',)])

    def test_old_positional_hand_constructor_keeps_ring_open(self):
        old_hand = Hand((0.5, 0.5), 1.0, 1.0, (True,) * 4, True)
        self.assertEqual(old_hand.ring_pinch, 1.0)


class EnterBrokerTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.owner = InputOwner(self.backend)

    def test_enter_is_a_down_up_pair_and_release_is_idempotent(self):
        self.owner.apply(('enter',))
        self.owner.release()
        self.assertEqual(self.backend.enter_key.call_args_list, [((True,),), ((False,),)])

    def test_enter_is_blocked_while_voice_or_mouse_is_held(self):
        for command in ('voice_down', 'left_down'):
            with self.subTest(command=command):
                self.owner = InputOwner(self.backend)
                self.owner.apply((command,))
                self.owner.apply(('enter',))
                self.backend.enter_key.assert_not_called()
                self.owner.release()

    def test_failed_enter_release_is_retried_from_owned_state(self):
        self.backend.enter_key.side_effect = [None, OSError('mock release rejected'), None]
        with self.assertRaises(OSError):
            self.owner.apply(('enter',))
        self.owner.release()
        self.owner.release()
        self.assertEqual(self.backend.enter_key.call_args_list, [((True,),), ((False,),), ((False,),)])


if __name__ == '__main__':
    unittest.main()
