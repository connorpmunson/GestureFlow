"""Camera/inference worker with a single latest-frame mailbox (no UI backlog)."""
import logging
import threading
import time
from pathlib import Path
import cv2
import mediapipe as mp
from .engine import Hand
from .selection import select_hand, anatomical_side

ROOT = Path(__file__).resolve().parent.parent
CONNECTIONS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),
               (9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]

class Tracker(threading.Thread):
    def __init__(self, camera=0, hand="Right"):
        super().__init__(daemon=True, name="camera-inference")
        self.camera, self.hand = camera, hand
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.error = None
        self.frames = 0
        self.fps = 0.0

    def take(self):
        with self.lock:
            latest, self.latest = self.latest, None
        return latest

    def run(self):
        capture = None
        try:
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT / "models/hand_landmarker.task")),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.6)
            with mp.tasks.vision.HandLandmarker.create_from_options(options) as model:
                capture = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW)
                if not capture.isOpened():
                    capture.release()
                    capture = cv2.VideoCapture(self.camera, cv2.CAP_MSMF)
                if not capture.isOpened():
                    raise RuntimeError("Camera unavailable. Choose another camera, or close apps using it.")
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                capture.set(cv2.CAP_PROP_FPS, 30)
                previous = time.monotonic()
                stamp = 0
                failures = 0
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        failures += 1
                        if failures > 15:
                            raise RuntimeError("Camera stopped delivering frames. Reconnect it and restart the camera.")
                        time.sleep(0.03)
                        continue
                    failures = 0
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    stamp = max(stamp + 1, int(time.monotonic() * 1000))
                    result = model.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                    h, w = frame.shape[:2]
                    requested = self.hand
                    hand, side = None, "No hand" if requested == "Either" else f"Waiting for {requested.lower()} hand"
                    selected = select_hand(result.handedness, requested)
                    if selected is not None and selected < len(result.hand_landmarks):
                        side = anatomical_side(result.handedness[selected][0].category_name)
                        points = result.hand_landmarks[selected]
                        hand = Hand.from_landmarks(points, w / h)
                        for a,b in CONNECTIONS:
                            cv2.line(rgb, (int(points[a].x*w),int(points[a].y*h)),
                                     (int(points[b].x*w),int(points[b].y*h)), (96,225,194), 2, cv2.LINE_AA)
                        for j,v in enumerate(points):
                            cv2.circle(rgb, (int(v.x*w),int(v.y*h)), 5 if j in (4,8,12,16) else 3,
                                       (255,199,112) if j in (4,8,12,16) else (227,248,241), -1, cv2.LINE_AA)
                    now = time.monotonic()
                    self.fps = 0.9 * self.fps + 0.1 / max(0.001, now-previous)
                    previous = now
                    self.frames += 1
                    with self.lock:
                        self.latest = (rgb, hand, side, now)
        except Exception as exc:
            logging.exception("Tracker failed")
            self.error = str(exc)
        finally:
            if capture is not None:
                capture.release()
