"""Exercise recognition from landmarks, not preclassified Hand flags."""
import unittest
from types import SimpleNamespace
from gestureflow.engine import Engine, Hand


def pinched_hand(target):
    points = [(0.5, 0.9)] * 21
    for base, x in [(5, 0.35), (9, 0.45), (13, 0.55), (17, 0.65)]:
        points[base:base + 4] = [(x, 0.65), (x, 0.45), (x, 0.32), (x, 0.2)]
    # A bent fingertip touches the thumb near its MCP knuckle.
    x = points[target][0]
    points[target + 2] = (x, 0.51)
    points[target + 3] = (x, 0.60)
    points[1:5] = [(0.28, 0.8), (0.3, 0.73), (x - 0.03, 0.64), (x + 0.01, 0.60)]
    return Hand.from_landmarks([SimpleNamespace(x=x, y=y) for x, y in points])


class ToolLandmarkTests(unittest.TestCase):
    def test_compact_pinch_activates_and_releases_both_tools(self):
        for target, expected, fingers in [(9, 'voice_down', (True, False, True, True)),
                                          (13, 'enter', (True, True, False, True))]:
            with self.subTest(target=target):
                hand = pinched_hand(target)
                self.assertEqual(hand.fingers, fingers)
                engine = Engine()
                engine.paused = False
                actions = []
                for frame in range(20):
                    actions += engine.step(hand, frame * 0.02)
                self.assertEqual(actions, [(expected,)])
                hand.middle_pinch = hand.ring_pinch = 1.0
                released = []
                for frame in range(20, 30):
                    released += engine.step(hand, frame * 0.02)
                self.assertEqual(engine.mode, 'idle')
                self.assertEqual(released, [('voice_up',)] if target == 9 else [])

    def test_extra_folded_finger_still_blocks_compact_pinch(self):
        hand = pinched_hand(9)
        hand.fingers = (False, False, True, True)
        engine = Engine()
        engine.paused = False
        actions = []
        for frame in range(20):
            actions += engine.step(hand, frame * 0.02)
        self.assertEqual(actions, [])
        self.assertIn('index', engine.status)
