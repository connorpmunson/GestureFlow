"""Camera-free, input-free dependency and model check for a fresh installation."""
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    assert sys.platform == 'win32', 'Windows is required'
    assert sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8, 'Python 3.13 64-bit is required'
    import cv2
    import mediapipe as mp
    import psutil
    from PySide6.QtWidgets import QApplication
    from gestureflow import native
    from gestureflow.engine import Engine
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])
    assert app is not None and Engine().paused
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT / 'models/hand_landmarker.task')),
        num_hands=2)
    with mp.tasks.vision.HandLandmarker.create_from_options(options):
        pass
    assert native.monitors(), 'No Windows display detected'
    result = subprocess.run([sys.executable, '-m', 'gestureflow.broker'], cwd=ROOT,
                            input='', text=True, capture_output=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, f'Input helper failed to start: {result.stderr}'
    print('PASS: Python, Qt, OpenCV, MediaPipe model, psutil, Windows bindings, and input helper load.')
    print('No camera was opened and no mouse or keyboard input was sent.')

if __name__ == '__main__':
    main()
