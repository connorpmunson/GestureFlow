"""Power transitions are deliberate sequences, independent of tool recognition."""
import unittest
from gestureflow.engine import Engine, Hand


def pose(name):
    fingers = {'open': (True,) * 4, 'fist': (False,) * 4,
               'neutral': (True, False, False, False)}[name]
    return Hand((0.5, 0.5), 1, 1, fingers, name == 'open', index_tip=(0.6, 0.4))


class PowerTransitionTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.now = 0.0

    def step(self, hand, elapsed=0.02):
        self.now += elapsed
        return self.engine.step(hand, self.now)

    def hold(self, name, seconds=0.4):
        hand = pose(name) if isinstance(name, str) else name
        actions = []
        for _ in range(round(seconds / 0.02)):
            actions += self.step(hand)
        return actions

    def turn_on(self):
        self.hold('fist')
        actions = self.hold('open')
        self.assertEqual(actions.count(('resume',)), 1)
        self.assertFalse(self.engine.paused)

    def test_static_open_never_turns_on_and_static_fist_never_turns_off(self):
        self.assertEqual(self.hold('open', 3), [])
        self.assertTrue(self.engine.paused)
        self.engine.paused = False
        self.assertEqual(self.hold('fist', 3), [])
        self.assertFalse(self.engine.paused)

    def test_both_source_and_destination_need_separate_stable_dwell(self):
        self.hold('fist', 0.20)
        self.hold('open')
        self.assertTrue(self.engine.paused)
        self.hold('fist')
        self.assertEqual(self.hold('open', 0.20), [])
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.hold('open', 0.20), [('resume',)])

    def test_intermediate_shapes_allowed_within_deadline(self):
        self.hold('fist')
        self.hold('neutral', 0.8)
        self.assertEqual(self.hold('open'), [('resume',)])

    def test_static_source_has_no_expiry_before_it_is_left(self):
        self.hold('fist', 3)
        self.assertEqual(self.hold('open'), [('resume',)])

    def test_destination_must_finish_before_transition_deadline(self):
        self.hold('fist')
        self.hold('neutral', 1.3)
        self.hold('open', 1.0)
        self.assertTrue(self.engine.paused)
        self.hold('fist')
        self.assertEqual(self.hold('open'), [('resume',)])

    def test_destination_dwell_resets_on_intermediate_shape(self):
        self.hold('fist')
        self.hold('open', 0.18)
        self.hold('neutral', 0.02)
        self.hold('open', 0.18)
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.hold('open', 0.18), [('resume',)])

    def test_consumed_off_fist_cannot_reactivate_by_reopening(self):
        self.engine.paused = False
        self.hold('open')
        self.hold('fist')
        self.assertTrue(self.engine.paused)
        self.hold('fist', 2)
        self.assertEqual(self.hold('open', 2), [])
        self.assertTrue(self.engine.paused)
        self.hold('fist')
        self.assertEqual(self.hold('open'), [('resume',)])

    def test_on_destination_is_consumed_symmetrically(self):
        self.turn_on()
        self.hold('open', 1)
        self.hold('fist', 1)
        self.assertFalse(self.engine.paused)
        self.hold('open')
        self.assertIn(('release_all',), self.hold('fist'))
        self.assertTrue(self.engine.paused)

    def test_single_missing_frame_cancels_source_and_destination_evidence(self):
        for phase in ('source', 'destination'):
            with self.subTest(phase=phase):
                self.engine = Engine()
                self.hold('fist')
                if phase == 'destination':
                    self.hold('open', 0.18)
                self.step(None)
                self.assertEqual(self.hold('open'), [])
                self.assertTrue(self.engine.paused)

    def test_missing_frame_does_not_remove_consumed_destination_guard(self):
        self.engine.paused = False
        self.hold('open')
        self.hold('fist')
        self.step(None)
        self.hold('fist')
        self.assertEqual(self.hold('open'), [])
        self.assertTrue(self.engine.paused)

    def test_stall_stop_lock_and_settings_reset_clear_pending_transition(self):
        for reason in ('stall', 'stop', 'lock', 'settings'):
            with self.subTest(reason=reason):
                self.engine = Engine()
                self.hold('fist')
                if reason == 'stall':
                    self.step(pose('open'), elapsed=0.8)
                elif reason == 'stop':
                    self.engine.stop()
                elif reason == 'lock':
                    self.engine.stop(locked=True)
                    self.hold('fist')
                    self.engine.locked = False
                else:
                    self.engine.reset_power_transition()
                self.assertEqual(self.hold('open'), [])
                self.assertTrue(self.engine.paused)

    def test_stale_open_source_does_not_turn_off_after_tool_work(self):
        self.engine.paused = False
        self.hold('open')
        self.hold('neutral', 2)
        self.hold('fist')
        self.assertFalse(self.engine.paused)

    def test_fist_releases_all_held_modes_without_power_source(self):
        for mode, release in [('click', 'left_up'), ('dictate', 'voice_up'),
                              ('switch', 'switch_end'), ('enter', None)]:
            with self.subTest(mode=mode):
                self.engine = Engine()
                self.engine.paused = False
                self.engine.mode = mode
                self.assertEqual(self.hold('fist', 0.08), [])
                actions = self.hold('fist', 0.12)
                self.assertEqual(actions, [(release,)] if release else [])
                self.assertEqual(self.engine.mode, 'idle')
                self.assertFalse(self.engine.paused)
                self.hold('fist', 1)
                self.assertFalse(self.engine.paused)

    def test_loss_releases_holds_but_preserves_power_latch(self):
        for mode, release in [('click', 'left_up'), ('dictate', 'voice_up'), ('switch', 'switch_end')]:
            with self.subTest(mode=mode):
                self.engine = Engine()
                self.engine.paused = False
                self.step(pose('neutral'))
                self.engine.mode = mode
                actions = self.hold(None)
                self.assertIn((release,), actions)
                self.assertIn(('release_all',), actions)
                self.assertFalse(self.engine.paused)
                self.assertIsNone(self.engine.power_source_since)

    def test_off_suppresses_every_tool_and_cursor_action(self):
        tools = [
            Hand((0.5,0.5), 1, 1, (True,False,False,False), False, index_side_touch=0.1),
            Hand((0.5,0.5), 1, 0.1, (True,False,True,True), True),
            Hand((0.5,0.5), 1, 1, (True,True,False,True), True, ring_pinch=0.1),
            Hand((0.5,0.5), 1, 1, (True,False,False,True), False),
            Hand((0.5,0.5), 1, 1, (False,False,False,True), True),
            Hand((0.5,0.5), 1, 1, (False,) * 4, True),
            pose('neutral'),
        ]
        for hand in tools:
            self.assertEqual(self.hold(hand), [])
            self.assertTrue(self.engine.paused)
            self.assertEqual(self.engine.mode, 'idle')

    def test_tool_dwell_does_not_replace_power_transition_state(self):
        self.engine.paused = False
        self.hold('open')
        voice = Hand((0.5,0.5), 1, 0.1, (True,False,True,True), True)
        self.assertEqual(self.hold(voice, 0.2), [('voice_down',)])
        actions = self.hold('fist')
        self.assertIn(('voice_up',), actions)
        self.assertIn(('release_all',), actions)
        self.assertTrue(self.engine.paused)


if __name__ == '__main__':
    unittest.main()
