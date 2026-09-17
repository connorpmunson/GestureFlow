import queue
import unittest
from unittest.mock import Mock, patch
from gestureflow import broker


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.owner = broker.InputOwner(self.backend)

    def test_holds_are_exclusive_and_idempotent(self):
        for command in [('voice_down',), ('voice_down',), ('left_down',), ('right_click',), ('scroll', 120)]:
            self.owner.apply(command)
        self.backend.right_control.assert_called_once_with(True)
        self.backend.mouse.assert_not_called()
        self.owner.release()
        self.owner.release()
        self.assertEqual(self.backend.right_control.call_args_list, [((True,),), ((False,),)])

    def test_click_ownership_blocks_voice_and_releases_once(self):
        self.owner.apply(('left_down',))
        self.owner.apply(('left_down',))
        self.owner.apply(('voice_down',))
        self.owner.release()
        self.owner.release()
        self.backend.right_control.assert_not_called()
        self.assertEqual(self.backend.mouse.call_args_list, [((2,),), ((4,),)])

    def test_failed_release_retains_ownership_for_retry(self):
        self.owner.apply(('voice_down',))
        self.backend.right_control.side_effect = OSError('simulated failure')
        with self.assertRaises(OSError):
            self.owner.release()
        self.assertTrue(self.owner.voice)
        self.backend.right_control.side_effect = None
        self.owner.release()
        self.assertFalse(self.owner.voice)

    def run_loop(self, schedule):
        clock = [100.0]
        items = iter(schedule)
        def get(timeout):
            clock[0], item = next(items)
            if item == 'timeout':
                raise queue.Empty()
            return item
        inbox = Mock()
        inbox.get.side_effect = get
        with patch.object(broker.queue, 'Queue', return_value=inbox), patch.object(broker.threading, 'Thread'), patch.object(broker.native, 'dpi_aware'), patch.object(broker.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(broker, 'InputOwner', return_value=self.owner):
            broker.main()

    def test_eof_releases_held_voice(self):
        self.run_loop([(100.1, {'time': 100.1, 'actions': [('voice_down',)]}), (100.2, None)])
        self.assertEqual(self.backend.right_control.call_args_list, [((True,),), ((False,),)])

    def test_watchdog_releases_and_discards_stale_commands(self):
        self.run_loop([(100.1, {'time': 100.1, 'actions': [('voice_down',)]}), (100.8, 'timeout'), (101.0, {'time': 100.1, 'actions': [('voice_down',)]}), (101.1, None)])
        self.assertEqual(self.backend.right_control.call_args_list, [((True,),), ((False,),)])

    def test_watchdog_release_retries_after_repeated_failures(self):
        self.backend.right_control.side_effect = [None, OSError('first release rejected'), OSError('retry rejected'), None]
        with self.assertLogs(level='ERROR'):
            self.run_loop([(100.1, {'time': 100.1, 'actions': [('voice_down',)]}), (100.8, 'timeout'), (100.9, 'timeout'), (101.0, 'timeout'), (101.1, None)])
        self.assertEqual(self.backend.right_control.call_args_list, [((True,),), ((False,),), ((False,),), ((False,),)])
        self.assertFalse(self.owner.voice)

    def test_failed_release_command_is_retried_before_new_input(self):
        self.backend.right_control.side_effect = [None, OSError('release rejected'), None]
        with self.assertLogs(level='ERROR'):
            self.run_loop([(100.1, {'time': 100.1, 'actions': [('voice_down',)]}), (100.2, {'time': 100.2, 'actions': [('voice_up',), ('left_down',)]}), (100.3, {'time': 100.3, 'actions': [('left_down',)]}), (100.4, None)])
        self.assertEqual(self.backend.right_control.call_args_list, [((True,),), ((False,),), ((False,),)])
        self.assertEqual(self.backend.mouse.call_args_list, [((2,),), ((4,),)])
        self.assertFalse(self.owner.voice)
        self.assertFalse(self.owner.left)

    def test_eof_release_retries_transient_failure(self):
        self.backend.right_control.side_effect = [None, OSError('release rejected'), None]
        with patch.object(broker.time, 'sleep') as sleep:
            self.run_loop([(100.1, {'time': 100.1, 'actions': [('voice_down',)]}), (100.2, None)])
        sleep.assert_called_once_with(0.05)
        self.assertFalse(self.owner.voice)
    def test_fresh_empty_heartbeat_preserves_hold(self):
        self.run_loop([(100.1, {'time': 100.1, 'actions': [('left_down',)]}), (100.6, {'time': 100.6, 'actions': []}), (101.0, 'timeout'), (101.1, None)])
        self.assertEqual(self.backend.mouse.call_args_list, [((2,),), ((4,),)])


if __name__ == '__main__':
    unittest.main()

