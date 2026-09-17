"""Guided comfortable-range calibration; never injects input."""
from statistics import median

class Calibration:
    STEPS = [
        "Rest your elbow. Point at your comfortable CENTER position.",
        "Point as far LEFT as is comfortable. Keep your elbow planted.",
        "Point as far RIGHT as is comfortable. Keep your elbow planted.",
        "Tilt your wrist comfortably UP, then hold your pointing finger still.",
        "Tilt your wrist comfortably DOWN, then hold your pointing finger still.",
    ]
    def __init__(self):
        self.phase = 0
        self.started = None
        self.samples = []
        self.positions = []
        self.finished = False
        self.result = None
        self.error = None

    def update(self, hand, now):
        if self.finished:
            return "Calibration complete" if self.result else self.error
        valid = hand is not None and hand.fingers == (True,False,False,False) and hand.index_tip is not None
        instruction = f"Step {self.phase+1}/5 · {self.STEPS[self.phase]}"
        if not valid:
            self.started = None
            self.samples = []
            return instruction + " Extend ONLY your index finger to continue."
        if self.started is None:
            self.started = now
        elapsed = now-self.started
        if elapsed >= 2.2:
            self.samples.append(hand.index_tip)
        if elapsed < 3.0 or len(self.samples)<6:
            return instruction + f" Hold · {max(1, int(3.99-elapsed))}"
        self.positions.append(tuple(median(p[axis] for p in self.samples) for axis in (0,1)))
        self.phase += 1
        self.started = None
        self.samples = []
        if self.phase < 5:
            return f"Step {self.phase+1}/5 · {self.STEPS[self.phase]}"
        self.finished = True
        center,left,right,up,down = self.positions
        x1,x2 = left[0],right[0]
        y1,y2 = up[1],down[1]
        if x2-x1<0.035 or y2-y1<0.025:
            self.error = "Range was too small or reversed. Try again with distinct comfortable positions."
        elif not (x1 <= center[0] <= x2 and y1 <= center[1] <= y2):
            self.error = "The center must sit between your extremes. Try again from the same resting position."
        else:
            self.result = (max(0,x1),max(0,y1),min(1,x2),min(1,y2))
        return "Comfortable range saved. Open palm turns control on; point to move." if self.result else self.error
