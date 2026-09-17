# GestureFlow v0.1.1 - laptop installation

Use a Windows laptop with an Intel or AMD 64-bit processor and a working camera. This release is not for macOS, Linux, or native Windows ARM. Internet access is needed during dependency installation.

## Install

1. Install **Python 3.13, 64-bit** from the tested [Python 3.13.13 release](https://www.python.org/downloads/release/python-31313/). If offered, include the Python launcher.
2. Extract the **entire** v0.1.1 release **Source code (zip)** archive to a writable location such as your `Documents\GestureFlow` folder. Do not launch files from inside the ZIP, and avoid Program Files.
3. Double-click **Install.cmd**. Leave the setup window open until it reports that setup is verified.
4. Open the new **GestureFlow** desktop shortcut or double-click **Start-GestureFlow.cmd** in the extracted folder. This launch path needs neither the optional GestureFlow.exe nor .NET.
5. Allow desktop apps to access the camera in Windows privacy settings. If the wrong camera opens, stop it in GestureFlow, change Camera index, then restart it.
6. Install **FlowSpeak separately**. Confirm its physical Right Ctrl hold-to-talk behavior in a text field. GestureFlow looks in the current user's Documents folders; use **Locate** to select FlowSpeak.exe if needed, then **Launch**.
7. Click **Calibrate wrist range** and follow center, left, right, up, down with your elbow resting. Hold an open palm to turn control ON afterward; point with only the index to move.

Use Preview only while practicing. The default controlling hand is Right and the floating status overlay is off. Ctrl+Alt+G locks controls globally. A closed fist turns gesture control OFF while the camera remains on.

The dashboard fits the available screen at startup and scrolls horizontally and vertically on small or scaled displays; both scrollbars were verified in an offscreen 640 x 480 check.

## What setup installs

The ZIP contains source code, the local hand model, documentation, and installation scripts. It does **not** contain Python, installed third-party dependencies, or FlowSpeak. Install.cmd runs Install.ps1, which checks Windows/Python compatibility, creates a project-local `.venv`, downloads pinned binary wheels, runs `pip check`, verifies model loading and the input helper, and creates a desktop shortcut.

Start from the clean ZIP on each computer. Do not transfer the desktop PC's `.venv`, `settings.json`, or saved calibration: virtual environments are machine-specific, and camera coordinates must be recalibrated. If setup is interrupted, run Install.cmd again. An incompatible existing environment should be handled by extracting into a fresh folder.

GestureFlow does not modify FlowSpeak. Its existing recording, transcription, account settings, and insertion behavior stay with that app. Camera inference runs locally; GestureFlow does not save or upload video. FlowSpeak retains its existing audio/transcription processing.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Python missing or wrong version | Install Python 3.13 64-bit, then rerun Install.cmd. Python 3.12/3.14 and 32-bit Python are not this release's target. |
| Missing project file | Extract the complete ZIP, including models and scripts, before running setup. |
| Dependency download failed | Check internet access and rerun Install.cmd. Setup requires binary wheels for Windows x64. |
| OpenCV import reports a missing DLL | Install the x64 runtime from [Microsoft Visual C++ Redistributable downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist), then rerun setup. The [OpenCV package troubleshooting guide](https://pypi.org/project/opencv-python/) identifies this runtime as a Windows import prerequisite. |
| Incompatible .venv | Extract a fresh copy into a new writable folder; do not copy an environment from another PC. |
| Camera unavailable | Enable camera access for desktop apps, close other camera apps, and try the correct Camera index. |
| Command launcher does not open the app | From a terminal in the project folder, run `.\.venv\Scripts\python.exe main.py`. |
| FlowSpeak not found | Install it separately and use Locate to select that laptop's FlowSpeak.exe. Test physical Right Ctrl first. |
| Gestures feel too sensitive or require stretching | Calibrate on this laptop, then adjust horizontal/vertical sensitivity separately. |

Setup validation on the development PC is not a test on your physical laptop. The laptop's camera, microphone, FlowSpeak installation, gesture accuracy, and end-to-end dictation still need a local check.
