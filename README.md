# GestureFlow

A Windows desktop app that turns local webcam hand landmarks into mouse control and an additional hold-to-talk trigger for the existing FlowSpeak app.

**Launch:** double-click `GestureFlow.exe` in this folder, or use the GestureFlow desktop shortcut. The launcher uses the installed `.venv`; keep the project folder intact. Camera starts automatically. Hold an open palm for 0.35 seconds to turn gesture control ON; hold a closed fist for 0.30 seconds to turn it OFF. Neither action closes the app or camera.

**Controls (right hand):** while ON, only index extended moves the pointer using its fingertip. Keep the index straight and other fingers curled; touch your thumb to the side of the index to click, hold contact to drag, and release to drop. The old index-tip pinch no longer clicks. Middle bent to thumb with index/ring/pinky extended holds FlowSpeak's Right Ctrl; ring bent to thumb with index/middle/pinky extended sends Enter once. Maintain each exact shape; changing it releases after 0.10 seconds. Thumbs-up scrolls up/down; thumb and pinky extended right-clicks. Index and pinky extended with middle, ring, and thumb closed switches windows: hold 0.30 seconds to open Alt+Tab, keep holding to advance every 0.75 seconds, then release the gesture for 0.15 seconds to select the highlighted window. Physical modifier keys block switching; the pointer stays still. Actions do not switch control OFF. Hand loss releases input and freezes movement while retaining ON state. **Ctrl+Alt+G** locks/unlocks; Escape locks when GestureFlow is focused. Wait for FlowSpeak's text before Enter; it acts immediately in the focused app.

**Calibrate:** rest your elbow and follow the neutral, left, right, up, and down prompts, holding each index-pointing position for three seconds. Calibration maps your comfortable fingertip range to the screen and saves it. No input is sent during calibration; cancel preserves the previous mapping. Horizontal and vertical sensitivity can be adjusted separately.

Enable **Preview only — do not control PC** to practice without injecting input. FlowSpeak's code, settings, model choices, recording, transcription, cleanup, and insertion behavior are unchanged.

## Documentation

- `docs/GestureFlow-User-Guide.pdf`: setup, architecture, settings, troubleshooting and verification.
- `docs/GestureFlow-Gesture-Cheat-Sheet.pdf`: printable quick reference.
- Markdown sources are alongside the PDFs.

## Development

Python 3.13 on Windows x64 is used for this build. The local dependencies are pinned in `requirements-lock.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe main.py --preview
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Model: Google's MediaPipe Hand Landmarker float16 v1, stored in `models/hand_landmarker.task`. Source: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

Rebuild the optional Windows launcher with .NET 10 SDK:

```powershell
dotnet publish launcher/GestureFlow.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o work/launcher-publish
Copy-Item work/launcher-publish/GestureFlow.exe GestureFlow.exe
```

The executable is a launcher, not a standalone redistribution of Python, model and dependencies. Camera frames stay in memory; no camera recording or uploads. FlowSpeak retains its own existing cloud audio processing. Debug metadata and errors are in `work/`; configuration is in `settings.json`.

Recognition feedback: a compact middle-thumb or ring-thumb pinch is valid even when the bent fingertip is near its knuckle. The other three fingers must still be extended. If a tool gesture is incomplete, the HUD identifies which fingers need extending or whether the fingertips need to touch. The dashboard reports the detected extended fingers; `work/status.json` includes current finger flags and normalized contact distances for troubleshooting, without saving camera images. FlowSpeak continues to use the unchanged Right Ctrl hold/release bridge.


