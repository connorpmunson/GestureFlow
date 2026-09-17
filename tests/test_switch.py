import unittest
from unittest.mock import Mock, call
from gestureflow.engine import Engine, Hand
from gestureflow.broker import InputOwner


class SwitchTests(unittest.TestCase):
    def test_hold_cycles_and_release_selects(self):
        engine = Engine()
        pose = Hand((.5, .5), 1, 1, (True, False, False, True), False)
        self.assertEqual(engine.step(pose, 0), [])
        engine.paused = False
        actions = []
        for frame in range(1, 101):
            actions += engine.step(pose, frame * .02)
        self.assertEqual(actions, [('switch_start',), ('switch_next',), ('switch_next',)])
        neutral = Hand((.5, .5), 1, 1, (True,) * 4, True)
        released = []
        for frame in range(101, 115):
            released += engine.step(neutral, frame * .02)
        self.assertEqual(released, [('switch_end',)])
        actions = []
        for frame in range(115, 145):
            actions += engine.step(pose, frame * .02)
        self.assertEqual(actions, [('switch_start',)])

    def test_thumb_extended_does_not_switch(self):
        engine = Engine()
        engine.paused = False
        pose = Hand((.5, .5), 1, 1, (True, False, False, True), True)
        actions = [a for frame in range(30) for a in engine.step(pose, frame * .02)]
        self.assertEqual(actions, [])

    def test_broker_key_order_and_exclusive_holds(self):
        backend = Mock()
        owner = InputOwner(backend)
        owner.apply(('switch_start',))
        self.assertEqual(owner.switch_held, {'alt'})
        owner.apply(('switch_next',))
        owner.apply(('switch_end',))
        self.assertEqual(backend.switch_key.call_args_list,
                         [call('alt', True), call('tab', True), call('tab', False),
                          call('tab', True), call('tab', False), call('alt', False)])
        self.assertFalse(owner.switch_held)
        backend.reset_mock()
        owner.apply(('voice_down',))
        owner.apply(('switch_start',))
        backend.switch_key.assert_not_called()

    def test_failed_tab_release_still_releases_alt_and_retries_tab(self):
        backend = Mock()
        backend.switch_key.side_effect = [None, None, OSError('failure'), None, None]
        owner = InputOwner(backend)
        with self.assertRaises(OSError):
            owner.apply(('switch_start',))
        self.assertEqual(owner.switch_held, {'alt', 'tab'})
        owner.release()
        self.assertFalse(owner.switch_held)
        self.assertEqual(backend.switch_key.call_args_list[-2:], [call('tab', False), call('alt', False)])

    def test_tracking_loss_and_stop_release_alt(self):
        for lost in (True, False):
            engine = Engine()
            engine.paused = False
            engine.mode = 'switch'
            engine.last_seen = 0
            actions = engine.step(None, .4) if lost else engine.stop(True)
            self.assertIn(('switch_end',), actions)
            self.assertIn(('release_all',), actions)

    def test_no_cycle_while_release_is_pending(self):
        engine = Engine()
        engine.paused = False
        engine.mode = 'switch'
        engine.switch_next_at = 0
        neutral = Hand((.5, .5), 1, 1, (True,) * 4, True)
        self.assertEqual(engine.step(neutral, 1), [])
        self.assertEqual(engine.step(neutral, 1.16), [('switch_end',)])

    def test_other_inputs_blocked_during_switch_and_cleanup_is_idempotent(self):
        backend = Mock()
        owner = InputOwner(backend)
        owner.apply(('switch_start',))
        for op in ('voice_down', 'left_down', 'enter'):
            owner.apply((op,))
        backend.right_control.assert_not_called()
        backend.mouse.assert_not_called()
        backend.enter_key.assert_not_called()
        owner.release()
        owner.release()
        self.assertEqual(backend.switch_key.call_args_list.count(call('alt', False)), 1)
