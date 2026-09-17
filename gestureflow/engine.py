"""Deterministic gesture arbitration. No camera or OS side effects here."""
from dataclasses import dataclass
import math


@dataclass
class Hand:
    palm: tuple[float, float]
    index_pinch: float
    middle_pinch: float
    fingers: tuple[bool, bool, bool, bool]
    thumb_out: bool
    ring_pinch: float = 1.0
    index_tip: tuple[float, float] | None = None
    index_click_shape: bool = False
    middle_pinch_shape: bool = True
    ring_pinch_shape: bool = True
    index_side_touch: float = 1.0

    @staticmethod
    def point_segment_distance(point, start, end):
        """Euclidean distance to a finite segment, including degenerate segments."""
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-12:
            return math.dist(point, start)
        projection = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
        fraction = max(0.0, min(1.0, projection))
        return math.dist(point, (start[0] + fraction * dx, start[1] + fraction * dy))

    @classmethod
    def from_landmarks(cls, landmarks, aspect=4 / 3):
        p = [(v.x * aspect, v.y) for v in landmarks]
        def distance(a, b):
            return math.dist(p[a], p[b])
        def extended(mcp, pip, tip):
            a = (p[mcp][0] - p[pip][0], p[mcp][1] - p[pip][1])
            b = (p[tip][0] - p[pip][0], p[tip][1] - p[pip][1])
            denom = math.hypot(*a) * math.hypot(*b)
            cosine = sum(x * y for x, y in zip(a, b)) / max(denom, 1e-8)
            return cosine < -0.65 and distance(tip, 0) > distance(pip, 0) * 1.08
        scale = max(distance(5, 17), distance(0, 9), 0.04)
        fingers = tuple(extended(m, j, t) for m, j, t in [(5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)])
        palm = (sum(landmarks[i].x for i in (0, 5, 9, 13, 17)) / 5,
                sum(landmarks[i].y for i in (0, 5, 9, 13, 17)) / 5)
        thumb_out = distance(4, 17) > scale * 1.08 and distance(4, 5) > distance(3, 5) * 1.15
        return cls(palm, distance(4, 8) / scale, distance(4, 12) / scale, fingers, thumb_out, distance(4, 16) / scale,
                   (landmarks[8].x, landmarks[8].y), distance(8, 5) / scale > 0.35,
                   distance(12, 9) / scale > 0.50, distance(16, 13) / scale > 0.50,
                   min(cls.point_segment_distance(p[4], p[5], p[6]),
                       cls.point_segment_distance(p[4], p[6], p[7])) / scale)


class Engine:
    """Persistent armed latch, independent gesture modes, and owned input holds."""
    def __init__(self):
        self.paused = True
        self.locked = False
        self.mode = "idle"
        self.candidate = ""
        self.since = 0.0
        self.release_since = None
        self.last_seen = None
        self.last_tick = None
        self.entered = 0.0
        self.switch_next_at = 0.0
        self.pinch_on = 0.30
        self.pinch_off = 0.46
        self.scroll_speed = 1.0
        self.scroll_y = None
        self.scroll_accum = 0.0
        self.right_latched = False
        self.right_clear_since = None
        self.status = "Control OFF — open your palm to turn on"

    @property
    def click_on(self):
        return self.pinch_on * 0.65

    @property
    def click_off(self):
        return self.pinch_off * 0.65

    @property
    def click_approach(self):
        return self.click_off + 0.06

    def _exit(self):
        actions = []
        if self.mode == "click":
            actions.append(("left_up",))
        if self.mode == "dictate":
            actions.append(("voice_up",))
        if self.mode == "switch":
            actions.append(("switch_end",))
        self.mode = "idle"
        self.release_since = None
        self.scroll_y = None
        self.scroll_accum = 0.0
        return actions

    def release_tracking(self):
        """Release holds on lost/stalled tracking without changing the armed latch."""
        actions = self._exit()
        actions.append(("release_all",))
        self.candidate = ""
        self.last_seen = None
        self.right_latched = False
        self.right_clear_since = None
        self.status = ("Controls locked — use the button or Ctrl+Alt+G" if self.locked else
                       "Control OFF — open your palm to turn on" if self.paused else
                       "Control ON — hand not tracked; inputs released")
        return actions

    def stop(self, locked=False):
        self.paused = True
        self.locked = locked
        actions = self.release_tracking()
        self.status = "Controls locked — use the button or Ctrl+Alt+G" if locked else "Control OFF — open your palm to turn on"
        return actions

    def _stable(self, name, now, seconds):
        if self.candidate != name:
            self.candidate, self.since = name, now
        return now - self.since >= seconds

    def step(self, hand, now):
        actions = []
        if self.last_tick is not None and now - self.last_tick > 0.65:
            actions += self.release_tracking()
        self.last_tick = now
        if self.locked:
            return actions
        if hand is None:
            self.candidate = ""
            if self.last_seen is not None and now - self.last_seen > 0.30:
                actions += self.release_tracking()
            return actions
        self.last_seen = now
        i, m, r, p = hand.fingers
        open_palm = i and m and r and p
        pointing = i and not m and not r and not p
        tip = hand.index_tip if hand.index_tip is not None else hand.palm
        shaka = p and not i and not m and not r and hand.thumb_out
        thumbs_up = not any(hand.fingers) and hand.thumb_out
        fist = not any(hand.fingers) and not hand.thumb_out
        voice_pose = i and not m and r and p
        enter_pose = i and m and not r and p
        switch_pose = i and not m and not r and p and not hand.thumb_out

        if self.paused:
            if open_palm and self._stable("resume", now, 0.35):
                self.paused = False
                self.candidate = ""
                self.status = "Control ON — point to move or make any tool gesture"
                actions.append(("resume",))
            elif not open_palm:
                self.candidate = ""
            return actions

        if fist:
            self.status = "Hold closed fist to turn control off"
            # Shape release and the ON/OFF latch have independent dwell times.
            # Exiting a hold must not restart the longer closed-fist OFF dwell.
            if self.mode in ("click", "dictate", "enter", "switch"):
                self.release_since = now if self.release_since is None else self.release_since
                if now - self.release_since >= 0.10:
                    actions += self._exit()
            if self._stable("pause", now, 0.30):
                actions += self.stop()
            return actions
        if self.candidate == "pause":
            self.candidate = ""

        if self.mode == "switch":
            if not switch_pose:
                self.release_since = now if self.release_since is None else self.release_since
                if now - self.release_since >= 0.15:
                    actions += self._exit()
                    self.candidate = ""
                    self.status = "Window selected — control ON"
            else:
                self.release_since = None
                if now >= self.switch_next_at:
                    actions.append(("switch_next",))
                    self.switch_next_at = now + 0.75
            return actions

        if self.mode in ("click", "dictate", "enter"):
            distance = {"click": hand.index_side_touch, "dictate": hand.middle_pinch, "enter": hand.ring_pinch}[self.mode]
            threshold = self.click_off if self.mode == "click" else self.pinch_off
            # Changing out of the finger-gun shape ends a mouse hold even if
            # the thumb still happens to overlap the index knuckle in the image.
            released = (distance > threshold or (self.mode == "click" and not pointing)
                        or (self.mode == "dictate" and not voice_pose)
                        or (self.mode == "enter" and not enter_pose))
            if released:
                self.release_since = now if self.release_since is None else self.release_since
                if now - self.release_since >= 0.10:
                    actions += self._exit()
                    self.candidate = ""
                    self.status = "Control ON — ready"
                    return actions
            else:
                self.release_since = None
            if self.mode == "click" and self.release_since is None and now - self.entered > 0.24:
                actions.append(("drag", *tip))
                self.status = "Dragging — lift thumb from index side to drop"
            return actions

        if not shaka:
            if self.right_clear_since is None:
                self.right_clear_since = now
            if now - self.right_clear_since > 0.20:
                self.right_latched = False
        else:
            self.right_clear_since = None

        # Mouse contact is exclusively the thumb touching the SIDE of a straight
        # index finger. Its approaching shape takes precedence over tucked fingers.
        index_ready = pointing and hand.index_side_touch < self.click_on
        index_approach = pointing and hand.index_side_touch < self.click_approach
        # The other three extended fingers distinguish a deliberate tool pinch
        # from a resting thumb. Do not require the bent tip to stay away from
        # its knuckle: a compact, valid pinch naturally brings it close.
        middle_ready = hand.middle_pinch < self.pinch_on and voice_pose
        ring_ready = hand.ring_pinch < self.pinch_on and enter_pose
        pinches = sorted((distance, name) for ready, distance, name in
                         [(middle_ready, hand.middle_pinch, "dictate"),
                          (ring_ready, hand.ring_pinch, "enter")] if ready)
        ambiguous = len(pinches) > 1 and pinches[1][0] - pinches[0][0] < 0.08
        pinch = pinches[0][1] if pinches and not ambiguous else None
        gesture = ("click" if index_ready else "approach" if index_approach else
                   "neutral" if ambiguous else pinch if pinch else
                   "switch" if switch_pose else "right" if shaka else "scroll" if thumbs_up else
                   "move" if pointing else "neutral")
        if gesture != "scroll" and self.mode == "scroll":
            actions += self._exit()
        if gesture in ("dictate", "click", "enter"):
            self.status = ("Hold ring pinch briefly for Enter" if gesture == "enter" else
                           "Thumb-side contact detected" if gesture == "click" else "Pinch detected")
            if self._stable(gesture, now, 0.18 if gesture == "enter" else 0.085):
                self.mode, self.entered = gesture, now
                self.release_since = None
                actions.append(("voice_down",) if gesture == "dictate" else ("enter",) if gesture == "enter" else ("left_down", *tip))
                self.status = ("FlowSpeak held — release to finish" if gesture == "dictate" else
                               "Enter pressed — release pinch to rearm" if gesture == "enter" else "Click held")
        elif gesture == "switch":
            self.status = "Hold index + pinky to switch windows"
            if self._stable("switch", now, 0.30):
                self.mode = "switch"
                self.release_since = None
                self.switch_next_at = now + 0.75
                actions.append(("switch_start",))
                self.status = "Cycling windows — release gesture to select"
        elif gesture == "right":
            self.status = "Right-click" if self.right_latched else "Hold shaka to right-click"
            if self._stable("right", now, 0.30) and not self.right_latched:
                actions.append(("right_click",))
                self.right_latched = True
        elif gesture == "scroll":
            self.status = "Scrolling — hold thumbs-up and move your hand up or down"
            if self.mode != "scroll":
                if self._stable("scroll", now, 0.16):
                    self.mode, self.scroll_y = "scroll", hand.palm[1]
            else:
                delta = self.scroll_y - hand.palm[1]
                self.scroll_y = hand.palm[1]
                self.scroll_accum += max(-0.08, min(0.08, delta)) * self.scroll_speed / 0.025
                steps = math.trunc(self.scroll_accum)
                if steps:
                    actions.append(("scroll", max(-4, min(4, steps)) * 120))
                    self.scroll_accum -= steps
        elif gesture == "move":
            self.candidate = ""
            self.status = "Control ON — pointer active"
            actions.append(("move", *tip))
        else:
            self.candidate = ""
            self.status = ("Control ON — pointer frozen for thumb-side click" if gesture == "approach" else
                           "Control ON — ready for a gesture")
            if gesture == "neutral":
                nearby = [(hand.middle_pinch, "FlowSpeak", 1), (hand.ring_pinch, "Enter", 2)]
                distance, tool, target = min(nearby)
                if distance < self.pinch_off:
                    names = ("index", "middle", "ring", "pinky")
                    missing = [name for j, name in enumerate(names) if j != target and not hand.fingers[j]]
                    if missing:
                        self.status = f"{tool}: extend {' / '.join(missing)}; keep thumb contact"
                    elif hand.fingers[target]:
                        self.status = f"{tool}: bend {names[target]} to touch thumb"
                    else:
                        self.status = f"{tool}: bring fingertips closer together"
                elif voice_pose or enter_pose:
                    self.status = ("FlowSpeak: touch middle fingertip to thumb" if voice_pose else
                                   "Enter: touch ring fingertip to thumb")
        return actions


class Pointer:
    """Smoothed fingertip mapping with independent gains and anchored fingertip dragging."""
    def __init__(self):
        self.rect = (0, 0, 1920, 1080)
        self.margin = 0.40
        self.center_x = 0.78
        self.center_y = 0.68
        self.gain_x = 1.0
        self.gain_y = 1.0
        self.calibrated_bounds = None
        self.smoothing = 0.45
        self.position = None
        self.last_time = None
        self.drag_anchor = None

    def bounds(self):
        """Effective normalized camera area, including independent sensitivity gains."""
        if self.calibrated_bounds is None:
            base_span = max(0.001, min(1.0, 1 - 2 * self.margin))
            base_left = max(0.0, min(1 - base_span, self.center_x - base_span / 2))
            base_top = max(0.0, min(1 - base_span, self.center_y - base_span / 2))
            base = (base_left, base_top, base_left + base_span, base_top + base_span)
        else:
            raw_left, raw_top, raw_right, raw_bottom = self.calibrated_bounds
            base = (max(0.0, min(1.0, raw_left)), max(0.0, min(1.0, raw_top)),
                    max(0.0, min(1.0, raw_right)), max(0.0, min(1.0, raw_bottom)))
        left, top, right, bottom = base
        span_x = max(0.001, min(1.0, max(0.001, right - left) / max(0.01, self.gain_x)))
        span_y = max(0.001, min(1.0, max(0.001, bottom - top) / max(0.01, self.gain_y)))
        left = max(0.0, min(1 - span_x, (left + right) / 2 - span_x / 2))
        top = max(0.0, min(1 - span_y, (top + bottom) / 2 - span_y / 2))
        return left, top, left + span_x, top + span_y

    def move(self, x, y, now):
        left, top, width, height = self.rect
        left_edge, top_edge, right_edge, bottom_edge = self.bounds()
        span_x, span_y = right_edge - left_edge, bottom_edge - top_edge
        target = (left + max(0, min(1, (x - left_edge) / span_x)) * (width - 1),
                  top + max(0, min(1, (y - top_edge) / span_y)) * (height - 1))
        if self.position is None:
            self.position = target
        dt = min(0.08, max(0.001, now - self.last_time)) if self.last_time else 0.033
        self.last_time = now
        tau = 0.015 + self.smoothing * 0.16
        alpha = 1 - math.exp(-dt / tau)
        self.position = tuple(a + (b - a) * alpha for a, b in zip(self.position, target))
        return tuple(round(v) for v in self.position)

    def start_drag(self, x, y, cursor):
        self.drag_anchor = (x, y, *cursor)
        self.position = cursor

    def drag(self, x, y):
        if not self.drag_anchor:
            return None
        ax, ay, cx, cy = self.drag_anchor
        left, top, width, height = self.rect
        x0, y0, x1, y1 = self.bounds()
        target = (max(left, min(left + width - 1, cx + (x - ax) * width / (x1 - x0))),
                  max(top, min(top + height - 1, cy + (y - ay) * height / (y1 - y0))))
        self.position = tuple(a + (b - a) * 0.40 for a, b in zip(self.position, target))
        return tuple(round(v) for v in self.position)
