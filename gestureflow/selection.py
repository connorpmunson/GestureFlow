"""Select the requested hand independently of detector result ordering."""
def anatomical_side(model_side):
    # In this Tasks model, inference on our horizontally flipped camera frame
    # reverses anatomical handedness. Keep UI choices in the user's body space.
    return {"Left": "Right", "Right": "Left"}.get(model_side, model_side)


def select_hand(handedness, requested="Right", minimum_confidence=0.80):
    candidates = []
    for index, categories in enumerate(handedness):
        if not categories:
            continue
        category = categories[0]
        if category.score >= minimum_confidence and (requested == "Either" or anatomical_side(category.category_name) == requested):
            candidates.append((category.score, index))
    return max(candidates)[1] if candidates else None
