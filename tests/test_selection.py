import unittest
from types import SimpleNamespace
from gestureflow.selection import select_hand, anatomical_side

def hand(name, confidence=0.99):
    return [SimpleNamespace(category_name={"Right":"Left", "Left":"Right"}[name], score=confidence)]

class SelectionTests(unittest.TestCase):
    def test_mirrored_model_labels_are_converted_to_actual_hand(self):
        self.assertEqual(anatomical_side("Left"), "Right")
        self.assertEqual(anatomical_side("Right"), "Left")
        self.assertEqual(select_hand([[SimpleNamespace(category_name="Left", score=0.99)]]), 0)
        self.assertIsNone(select_hand([[SimpleNamespace(category_name="Right", score=0.99)]]))

    def test_right_hand_is_selected_even_when_left_is_first(self):
        self.assertEqual(select_hand([hand("Left"), hand("Right", 0.95)]), 1)

    def test_result_reordering_does_not_change_controlling_side(self):
        self.assertEqual(select_hand([hand("Right", 0.95), hand("Left")]), 0)

    def test_no_fallback_to_left_when_right_is_absent(self):
        self.assertIsNone(select_hand([hand("Left")]))
        self.assertIsNone(select_hand([]))

    def test_uncertain_right_classification_is_ignored(self):
        self.assertIsNone(select_hand([hand("Left"), hand("Right", 0.65)]))
        self.assertIsNone(select_hand([[]]))

if __name__ == "__main__":
    unittest.main()
