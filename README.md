# GestureFlow

A Windows desktop app that turns local webcam hand landmarks into mouse control and an additional hold-to-talk trigger for the existing FlowSpeak app.

## Install on a laptop

1. Use Windows on an Intel/AMD 64-bit processor. This release does not support macOS, Linux, or native Windows ARM.
2. Install Python 3.13 **64-bit** from the tested [Python 3.13.13 release](https://www.python.org/downloads/release/python-31313/).
3. Extract the **complete** v0.1.2 release **Source code (zip)** archive into a writable folder such as `Documents\GestureFlow`. Do not run inside the ZIP or install into Program Files.
4. Double-click `Install.cmd` with internet access. Setup creates a local `.venv`, installs pinned binary dependencies, verifies them, loads the model, checks the input helper, and creates a desktop shortcut.
5. Launch the shortcut or `Start-GestureFlow.cmd`. Neither the optional large executable nor .NET is needed for this launch path.
6. Install FlowSpeak separately, test its physical Right Ctrl hold-to-talk shortcut, then use GestureFlow's **Locate** button if needed. Calibrate again on the laptop.

The source ZIP includes code, model, docs, and setup scripts. It does not include Python, installed dependencies, or FlowSpeak. Do not copy another PC's `.venv`, `settings.json`, or calibration. Fresh settings use the right hand with the floating status overlay off. See `docs/Laptop-Install.md` for troubleshooting.

**Launch after setup:** use the desktop shortcut or `Start-GestureFlow.cmd`; the original PC can also use its existing `GestureFlow.exe`. Keep the project folder intact. Camera starts automatically. Turn ON with a deliberate closed-fist-to-open-palm sequence; turn OFF with open-palm-to-closed-fist. Hold the first pose 0.25 seconds and the second 0.30 seconds, finishing within 1.5 seconds after leaving the first. Static poses never toggle. After a toggle, relax/change pose before making a fresh sequence; simply reopening the OFF-ending fist cannot turn control ON. While OFF, the camera listens but gesture mouse/keyboard commands are disabled. Neither action closes the app or camera.

**Controls (right hand):** while ON, only index extended moves the pointer using its fingertip. Keep the index straight and other fingers curled; touch your thumb to the side of the index to click, hold contact to drag, and release to drop. The old index-tip pinch no longer clicks. Middle bent to thumb with index/ring/pinky extended holds FlowSpeak's Right Ctrl; ring bent to thumb with index/middle/pinky extended sends Enter once. Maintain each exact shape; changing it releases after 0.10 seconds. Thumbs-up scrolls up/down; thumb and pinky extended right-clicks. Index and pinky extended with middle, ring, and thumb closed switches windows: hold 0.30 seconds to open Alt+Tab, keep holding to advance every 0.75 seconds, then release the gesture for 0.15 seconds to select the highlighted window. Physical modifier keys block switching; the pointer stays still. Actions do not switch control OFF. Hand loss releases input and freezes movement while retaining ON state. **Ctrl+Alt+G** locks/unlocks; Escape locks when GestureFlow is focused. Wait for FlowSpeak's text before Enter; it acts immediately in the focused app.

**Calibrate:** rest your elbow and follow the neutral, left, right, up, and down prompts, holding each index-pointing position for three seconds. Calibration maps your comfortable fingertip range to the screen and saves it. No input is sent during calibration; cancel preserves the previous mapping. Horizontal and vertical sensitivity can be adjusted separately.

Enable **Preview only — do not control PC** to practice without injecting input. FlowSpeak's code, settings, model choices, recording, transcription, cleanup, and insertion behavior are unchanged.

## Documentation

- `docs/GestureFlow-User-Guide.pdf`: setup, architecture, settings, troubleshooting and verification.
- `docs/GestureFlow-Gesture-Cheat-Sheet.pdf`: printable quick reference.
- Markdown sources are alongside the PDFs.
- `docs/Laptop-Install.md`: clean laptop setup and verification steps.

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
