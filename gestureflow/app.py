from __future__ import annotations
import ctypes
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
from PySide6.QtCore import Qt, QTimer, QLockFile, QRectF, QAbstractNativeEventFilter, Signal, QStandardPaths
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFrame, QComboBox, QCheckBox, QSlider, QSpinBox, QFileDialog, QMessageBox,
    QScrollArea, QSizePolicy)
from .engine import Engine, Pointer
from .calibration import Calibration
from .tracker import Tracker, ROOT
from . import native

SETTINGS = ROOT / "settings.json"

class EmergencyHotkey(QAbstractNativeEventFilter):
    ID = 0x4746
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        # Register with the GUI thread so even a very short chord is queued reliably.
        self.registered = bool(native.user32.RegisterHotKey(None, self.ID, 0x4000 | 0x0001 | 0x0002, 0x47))

    def nativeEventFilter(self, event_type, message):
        msg = native.W.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == self.ID:
            self.callback()
            return True, 0
        return False, 0

    def close(self):
        if self.registered:
            native.user32.UnregisterHotKey(None, self.ID)

class Preview(QWidget):
    area_moved = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.frame = None
        self.margin = 0.40
        self.center_x = 0.78
        self.center_y = 0.68
        self.image_rect = QRectF()
        self.range_bounds = (0.68,0.58,0.88,0.78)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Click or drag in the camera preview to position your pointer area.")
        self.message = "Opening your camera…"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0c141b"))
        if self.frame:
            scaled = self.frame.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x, y = (self.width()-scaled.width())/2, (self.height()-scaled.height())/2
            self.image_rect = QRectF(x, y, scaled.width(), scaled.height())
            painter.drawImage(int(x), int(y), scaled)
            x1,y1,x2,y2 = self.range_bounds
            area = QRectF(x+scaled.width()*x1, y+scaled.height()*y1, scaled.width()*(x2-x1), scaled.height()*(y2-y1))
            painter.setPen(QPen(QColor(132, 230, 202, 155), 1, Qt.DashLine))
            painter.drawRoundedRect(area, 12, 12)
            painter.setPen(QColor("#cce9e0"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(max(int(x), min(int(area.x()), int(x+scaled.width()-190))), max(int(y+16), int(area.y()-7)), "FINGERTIP RANGE · DRAG TO MOVE")
        else:
            painter.setPen(QColor("#99adbb"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect().adjusted(32,32,-32,-32), Qt.AlignCenter | Qt.TextWordWrap, self.message)

    def move_area(self, point):
        if self.frame and self.image_rect.width() > 0:
            half_x = (self.range_bounds[2]-self.range_bounds[0])/2
            half_y = (self.range_bounds[3]-self.range_bounds[1])/2
            x = (point.x()-self.image_rect.x())/self.image_rect.width()
            y = (point.y()-self.image_rect.y())/self.image_rect.height()
            self.area_moved.emit(max(half_x,min(1-half_x,x)), max(half_y,min(1-half_y,y)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.image_rect.contains(event.position()):
            self.setCursor(Qt.ClosedHandCursor)
            self.move_area(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move_area(event.position())

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)

class Hud(QLabel):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 46)
        self.setFont(QFont("Segoe UI", 10, QFont.DemiBold))

    def display(self, message, recording=False):
        self.setText(message)
        self.setStyleSheet("QLabel { background: %s; color: %s; border: 1px solid %s; border-radius: 12px; padding: 10px 22px; }" %
                          (("#402b30", "#ffc5c5", "#aa6d75") if recording else ("#12232b", "#cdeee3", "#375b5b")))
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x()-self.width()//2, screen.top()+16)

class Broker:
    def __init__(self):
        self.log = open(ROOT / "work/input-helper.log", "a", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-m", "gestureflow.broker"],
             cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log,
             text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        self.last = 0.0

    def send(self, actions, force=False):
        now = time.monotonic()
        if self.process.poll() is not None:
            raise RuntimeError("Input helper stopped. Close and reopen GestureFlow to reconnect.")
        if actions or force or now-self.last > 0.10:
            self.process.stdin.write(json.dumps({"time": now, "actions": actions}) + "\n")
            self.process.stdin.flush()
            self.last = now

    def close(self):
        try:
            self.send([("release_all",)], True)
            self.process.stdin.close()
            self.process.wait(timeout=2)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            logging.exception("Input helper shutdown")
        self.log.close()

STYLE = """
QMainWindow, QWidget#root { background: #101a23; color: #e6eeeF; }
QWidget { font-family: 'Segoe UI'; font-size: 12px; color: #e6eeef; }
QLabel { background: transparent; }
QFrame#card { background: #17242f; border: 1px solid #293a48; border-radius: 14px; }
QLabel#muted { color: #9aafbd; }
QLabel#eyebrow { color: #86dcc0; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 32px; font-weight: 700; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#badge { color: #96e1c8; background: #223d3e; border-radius: 12px; padding: 7px 12px; }
QPushButton { background: #243643; border: 1px solid #3a5060; border-radius: 8px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #314956; border-color: #719caa; }
QPushButton:disabled { color: #647780; background: #1b2933; }
QPushButton#primary { background: #8ee1c4; color: #102820; border: 0; }
QPushButton#primary:hover { background: #b2efd9; }
QComboBox, QSpinBox { background: #101c26; border: 1px solid #3b4e5e; border-radius: 6px; padding: 6px 8px; min-height: 20px; }
QComboBox QAbstractItemView { background: #20333f; selection-background-color: #41655f; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #607b88; border-radius: 4px; background: #13212b; }
QCheckBox::indicator:checked { background: #8ee1c4; border: 3px solid #405e56; }
QSlider::groove:horizontal { height: 5px; background: #334956; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #80ceb4; }
QSlider::handle:horizontal { background: #c7f6e5; width: 14px; margin: -5px 0; border-radius: 7px; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: #14212b; width: 8px; }
QScrollBar::handle:vertical { background: #435b66; border-radius: 4px; min-height: 30px; }
QToolTip { background: #e0f2eb; color: #132b23; padding: 8px; }
"""

def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget

def card():
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20,18,20,18)
    layout.setSpacing(12)
    return widget, layout

class Window(QMainWindow):
    def __init__(self, preview=False, no_camera=False):
        super().__init__()
        self.setWindowTitle("GestureFlow")
        available = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(640, 400)
        self.resize(min(1180, max(640, available.width() - 40)),
                    min(850, max(400, available.height() - 60)))
        self.setWindowIcon(make_icon())
        self.engine, self.pointer = Engine(), Pointer()
        self.tracker = None
        self.last_frame_time = 0.0
        self.last_side = "No hand"
        self.last_hand = None
        self.last_health = 0.0
        self.last_hotkey = False
        self.closing = False
        self.broker_error = False
        self.flow_running = False
        self.voice_held = False
        documents = Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation))
        candidate = documents / "flowspeak/publish/FlowSpeak-win-x64/FlowSpeak.exe"
        self.flow_path = str(candidate) if candidate.is_file() else ""
        self.settings = self.load_settings()
        self.calibrator = None
        self.calibration_was_locked = False
        self.calibration_was_paused = True
        self.calibration_bounds = self.settings.get("calibration_bounds")
        if not (isinstance(self.calibration_bounds,list) and len(self.calibration_bounds)==4 and
                all(isinstance(v,(int,float)) and 0<=v<=1 for v in self.calibration_bounds) and
                self.calibration_bounds[2]>self.calibration_bounds[0] and self.calibration_bounds[3]>self.calibration_bounds[1]):
            self.calibration_bounds = None
        self.flow_path = self.settings.get("flow_path", self.flow_path)
        self.broker = Broker()
        self.hud = Hud()
        self.build_ui(preview)
        self.emergency = EmergencyHotkey(lambda: self.lock_controls(not self.engine.locked))
        QApplication.instance().installNativeEventFilter(self.emergency)
        if not self.emergency.registered:
            QTimer.singleShot(700, lambda: QMessageBox.warning(self, "Shortcut already in use",
                "Ctrl+Alt+G could not be registered. Use Lock controls or Escape in this window."))
        self.update_tuning()
        self.refresh_flow()
        self.flow_timer = QTimer(self)
        self.flow_timer.timeout.connect(self.refresh_flow)
        self.flow_timer.start(3000)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.escape = QShortcut(QKeySequence("Esc"), self)
        self.escape.activated.connect(lambda: self.lock_controls(True))
        if not no_camera:
            QTimer.singleShot(300, self.start_camera)
        else:
            self.preview.message = "Camera is off. Start it when you are ready."

    def build_ui(self, preview):
        root = QWidget()
        root.setObjectName("root")
        root.setMinimumSize(970, 720)
        viewport = QScrollArea()
        viewport.setObjectName("workspaceScroll")
        viewport.setStyleSheet("QScrollArea#workspaceScroll { border: none; }")
        viewport.setWidgetResizable(True)
        viewport.setWidget(root)
        self.setCentralWidget(viewport)
        main = QVBoxLayout(root)
        main.setContentsMargins(28,22,28,20)
        main.setSpacing(18)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label("HANDS ON. HANDS FREE.", "eyebrow"))
        brand.addWidget(label("GestureFlow", "title"))
        brand.addWidget(label("Your hand is the shortcut.", "muted"))
        header.addLayout(brand)
        header.addStretch()
        self.badge = label("CAMERA OFF", "badge")
        header.addWidget(self.badge, alignment=Qt.AlignVCenter)
        main.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(20)
        left = QVBoxLayout()
        preview_card, pc = card()
        heading = QHBoxLayout()
        heading.addWidget(label("Live view", "section"))
        heading.addStretch()
        self.fps_label = label("Local camera · no video saved", "muted")
        heading.addWidget(self.fps_label)
        pc.addLayout(heading)
        self.preview = Preview()
        self.preview.area_moved.connect(self.reposition_area)
        pc.addWidget(self.preview, stretch=1)
        self.status = label("Open your hand to turn gesture control on", "section", True)
        pc.addWidget(self.status)
        self.details = label("Show one hand, with your palm toward the camera.", "muted", True)
        pc.addWidget(self.details)
        bar = QHBoxLayout()
        self.camera_button = QPushButton("Start camera")
        self.camera_button.clicked.connect(self.toggle_camera)
        self.pause_button = QPushButton("Lock controls")
        self.pause_button.setObjectName("primary")
        self.pause_button.clicked.connect(lambda: self.lock_controls(not self.engine.locked))
        bar.addWidget(self.camera_button)
        bar.addWidget(self.pause_button)
        pc.addLayout(bar)
        left.addWidget(preview_card, stretch=1)
        guide, gl = card()
        gl.addWidget(label("Your gesture controls", "section"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        for row, (title, desc) in enumerate([
            ("01  Open palm / closed fist", "Turn control ON / OFF"),
            ("02  Index finger only", "Move cursor with your fingertip"),
            ("03  Thumb to index SIDE", "Finger-gun click · hold to drag"),
            ("04  Middle + thumb", "Others extended · hold FlowSpeak"),
            ("05  Ring + thumb", "Others extended · press Enter"),
            ("06  Thumbs-up", "Curl four fingers · move to scroll"),
            ("07  Thumb + pinky out", "Hold shaka briefly to right-click"),
            ("08  Index + pinky out", "Hold to cycle · release to select")]):
            grid.addWidget(label(title), row, 0)
            grid.addWidget(label(desc, "muted"), row, 1)
        gl.addLayout(grid)
        left.addWidget(guide)
        body.addLayout(left, stretch=3)
        controls = QWidget()
        controls.setObjectName("sidebar")
        controls.setStyleSheet("QWidget#sidebar { background: transparent; }")
        sidebar = QVBoxLayout(controls)
        sidebar.setContentsMargins(0,0,8,0)
        sidebar.setSpacing(14)
        setup, sl = card()
        sl.addWidget(label("Your setup", "section"))
        camera_row = QHBoxLayout()
        camera_row.addWidget(label("Camera index", "muted"))
        self.camera_index = QSpinBox()
        self.camera_index.setRange(0,9)
        self.camera_index.setValue(self.settings.get("camera",0))
        self.camera_index.setToolTip("0 is usually the built-in camera. Stop the camera before changing this.")
        camera_row.addWidget(self.camera_index)
        sl.addLayout(camera_row)
        sl.addWidget(label("Controlling hand", "muted"))
        self.hand_combo = QComboBox()
        self.hand_combo.addItems(["Either", "Right", "Left"])
        self.hand_combo.setCurrentText(self.settings.get("hand", "Right"))
        self.hand_combo.currentTextChanged.connect(self.change_hand)
        sl.addWidget(self.hand_combo)
        sl.addWidget(label("Pointer display", "muted"))
        self.screen_combo = QComboBox()
        self.screens = native.monitors()
        for j, (rect, primary) in enumerate(self.screens):
            self.screen_combo.addItem(f"Display {j+1} · {rect[2]} × {rect[3]}" + (" · primary" if primary else ""))
        self.screen_combo.setCurrentIndex(min(self.settings.get("screen",0), max(0,len(self.screens)-1)))
        self.screen_combo.currentIndexChanged.connect(self.change_screen)
        sl.addWidget(self.screen_combo)
        self.preview_only = QCheckBox("Preview only — do not control PC")
        self.preview_only.setChecked(preview)
        self.preview_only.toggled.connect(self.change_preview)
        sl.addWidget(self.preview_only)
        self.show_hud = QCheckBox("Show floating status")
        self.show_hud.setChecked(self.settings.get("hud",False))
        self.show_hud.toggled.connect(self.save_settings)
        sl.addWidget(self.show_hud)
        sidebar.addWidget(setup)
        calibration_card, cl = card()
        cl.addWidget(label("Keep your elbow on the desk", "section", True))
        cl.addWidget(label("Point with only your index finger. Teach GestureFlow the wrist movements that feel comfortable.", "muted", True))
        self.calibration_button = QPushButton("Calibrate wrist range")
        self.calibration_button.setObjectName("primary")
        self.calibration_button.clicked.connect(self.toggle_calibration)
        cl.addWidget(self.calibration_button)
        self.calibration_label = label("Saved range loaded" if self.calibration_bounds else "About 15 seconds · cursor stays still", "muted", True)
        cl.addWidget(self.calibration_label)
        sidebar.addWidget(calibration_card)
        tuning, tl = card()
        tl.addWidget(label("Make it feel right", "section"))
        self.sliders = {}
        for key, title, low, high, value, tip in [
            ("smoothing", "Pointer smoothing", 0,100,45,"Higher values make motion steadier, with more lag."),
            ("x_gain", "Horizontal sensitivity", 50,300,100,"Higher = less side-to-side fingertip travel. 100% uses the full calibrated range."),
            ("y_gain", "Vertical sensitivity", 50,400,150,"Higher = less up/down fingertip travel. Adjust independently of horizontal movement."),
            ("pinch", "Pinch sensitivity",20,45,30,"Higher values recognize a pinch before fingers fully touch."),
            ("scroll", "Scroll speed",25,200,100,"How far a thumbs-up hand movement scrolls.")]:
            row = QHBoxLayout()
            row.addWidget(label(title, "muted"))
            number = label("")
            row.addWidget(number, alignment=Qt.AlignRight)
            tl.addLayout(row)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(low,high)
            slider.setValue(self.settings.get(key,value))
            slider.setToolTip(tip)
            self.sliders[key] = (slider, number)
            slider.valueChanged.connect(self.update_tuning)
            tl.addWidget(slider)
        reset = QPushButton("Reset tuning")
        reset.clicked.connect(self.reset_tuning)
        tl.addWidget(reset)
        sidebar.addWidget(tuning)
        flow, fl = card()
        fl.addWidget(label("Connected to FlowSpeak", "section"))
        self.flow_label = label("Checking FlowSpeak…", "muted", True)
        fl.addWidget(self.flow_label)
        fl.addWidget(label("Uses your existing Right Ctrl hold-to-talk shortcut. FlowSpeak stays unchanged.", "muted", True))
        flow_buttons = QHBoxLayout()
        start_flow = QPushButton("Launch")
        start_flow.clicked.connect(self.launch_flow)
        browse_flow = QPushButton("Locate…")
        browse_flow.clicked.connect(self.browse_flow)
        flow_buttons.addWidget(start_flow)
        flow_buttons.addWidget(browse_flow)
        fl.addLayout(flow_buttons)
        sidebar.addWidget(flow)
        sidebar.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(410)
        body.addWidget(scroll, stretch=2)
        main.addLayout(body, stretch=1)
        footer = QHBoxLayout()
        footer.addWidget(label("Ctrl + Alt + G   Lock / unlock controls     •     Esc   Lock this window", "muted"))
        footer.addStretch()
        docs_button = QPushButton("Guides")
        docs_button.clicked.connect(lambda: os.startfile(str(ROOT / "docs")))
        footer.addWidget(docs_button)
        main.addLayout(footer)

    def load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_settings(self, *_):
        if not hasattr(self,"sliders"):
            return
        values = {k:v[0].value() for k,v in self.sliders.items()}
        values.update(area=self.settings.get("area",20),horizontal=self.settings.get("horizontal",78),height=self.settings.get("height",68),
                      calibration_bounds=list(self.calibration_bounds) if self.calibration_bounds else None)
        values.update(camera=self.camera_index.value(), hand=self.hand_combo.currentText(),
                      screen=self.screen_combo.currentIndex(), hud=self.show_hud.isChecked(), flow_path=self.flow_path)
        try:
            temp = SETTINGS.with_suffix(".tmp")
            temp.write_text(json.dumps(values,indent=2),encoding="utf-8")
            temp.replace(SETTINGS)
        except OSError:
            logging.exception("Cannot save settings")

    def update_tuning(self, *_):
        for key,(slider,number) in self.sliders.items():
            number.setText(str(slider.value()) + ("%" if key in ("x_gain","y_gain","scroll") else ""))
        self.pointer.smoothing = self.sliders["smoothing"][0].value()/100
        self.pointer.margin = (1-self.settings.get("area",20)/100)/2
        self.pointer.center_x = self.settings.get("horizontal",78)/100
        self.pointer.center_y = self.settings.get("height",68)/100
        self.pointer.gain_x = self.sliders["x_gain"][0].value()/100
        self.pointer.gain_y = self.sliders["y_gain"][0].value()/100
        self.pointer.calibrated_bounds = tuple(self.calibration_bounds) if self.calibration_bounds else None
        self.preview.range_bounds = self.pointer.bounds()
        self.preview.update()
        self.engine.pinch_on = self.sliders["pinch"][0].value()/100
        self.engine.pinch_off = self.engine.pinch_on+0.16
        self.engine.scroll_speed = self.sliders["scroll"][0].value()/100
        if self.screens:
            self.pointer.rect = self.screens[self.screen_combo.currentIndex()][0]
        self.save_settings()

    def reset_tuning(self):
        for key,value in {"smoothing":45,"x_gain":100,"y_gain":100 if self.calibration_bounds else 150,"pinch":30,"scroll":100}.items():
            self.sliders[key][0].setValue(value)

    def reposition_area(self, x, y):
        if self.calibrator:
            return
        self.dispatch(self.engine.release_tracking())
        if self.calibration_bounds:
            x1,y1,x2,y2 = self.calibration_bounds
        else:
            span = 1-2*self.pointer.margin
            x1,x2 = self.pointer.center_x-span/2,self.pointer.center_x+span/2
            y1,y2 = self.pointer.center_y-span/2,self.pointer.center_y+span/2
        width,height = x2-x1,y2-y1
        x = max(width/2,min(1-width/2,x))
        y = max(height/2,min(1-height/2,y))
        self.calibration_bounds = (x-width/2,y-height/2,x+width/2,y+height/2)
        self.pointer.position = None
        self.calibration_label.setText("Range position saved · drag to adjust again")
        self.update_tuning()

    def toggle_calibration(self):
        if self.calibrator:
            self.finish_calibration(cancelled=True)
            return
        if not self.tracker or not self.tracker.is_alive():
            QMessageBox.information(self,"Start the camera","Start your camera before calibrating your wrist range.")
            return
        self.calibration_was_locked = self.engine.locked
        self.calibration_was_paused = self.engine.paused
        self.dispatch(self.engine.stop(True))
        self.calibrator = Calibration()
        self.calibration_button.setText("Cancel calibration")
        self.calibration_label.setText(self.calibrator.STEPS[0])
        for slider,_ in self.sliders.values():
            slider.setEnabled(False)
        self.hand_combo.setEnabled(False)
        self.screen_combo.setEnabled(False)

    def calibrate_frame(self, hand, now):
        message = self.calibrator.update(hand,now)
        self.calibration_label.setText(message)
        self.engine.status = message
        self.dispatch([])
        if self.calibrator.finished:
            self.finish_calibration()

    def finish_calibration(self, cancelled=False):
        if not self.calibrator:
            return
        result = self.calibrator.result if not cancelled else None
        message = ("Calibration cancelled. Previous range kept." if cancelled else
                   self.calibrator.error or "Range saved. Open palm turns control on; point to move.")
        self.calibrator = None
        if result:
            self.calibration_bounds = result
            self.sliders["x_gain"][0].setValue(100)
            self.sliders["y_gain"][0].setValue(100)
            self.pointer.position = None
            self.update_tuning()
        self.calibration_button.setText("Calibrate wrist range")
        self.calibration_label.setText(message)
        for slider,_ in self.sliders.values():
            slider.setEnabled(True)
        self.hand_combo.setEnabled(True)
        self.screen_combo.setEnabled(True)
        self.dispatch(self.engine.stop(self.calibration_was_locked))
        self.engine.paused = self.calibration_was_paused
        if not self.engine.paused and not self.engine.locked:
            self.engine.status = "Control ON — point to move or use a gesture"
        self.pause_button.setText("Unlock controls" if self.engine.locked else "Lock controls")

    def change_hand(self, *_):
        self.dispatch(self.engine.release_tracking())
        if self.tracker:
            self.tracker.hand = self.hand_combo.currentText()
        self.save_settings()

    def change_screen(self, *_):
        self.dispatch(self.engine.release_tracking())
        self.pointer.position = None
        self.update_tuning()

    def change_preview(self, *_):
        self.dispatch(self.engine.release_tracking())
        self.voice_held = False
        self.pointer.position = None

    def lock_controls(self, locked):
        if self.calibrator:
            self.finish_calibration(cancelled=True)
            locked = True
        self.dispatch(self.engine.stop(locked))
        self.pointer.position = None
        self.pause_button.setText("Unlock controls" if locked else "Lock controls")

    def toggle_camera(self):
        if self.tracker and self.tracker.is_alive():
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        if self.tracker and self.tracker.is_alive():
            return
        self.engine.stop(self.engine.locked)
        self.preview.message = "Opening your camera…"
        self.preview.frame = None
        self.preview.update()
        self.tracker = Tracker(self.camera_index.value(), self.hand_combo.currentText())
        self.last_frame_time = time.monotonic()
        self.tracker.start()
        self.camera_button.setText("Stop camera")
        self.camera_button.setEnabled(True)
        self.camera_index.setEnabled(False)
        self.save_settings()

    def stop_camera(self):
        if self.calibrator:
            self.finish_calibration(cancelled=True)
        self.dispatch(self.engine.stop(self.engine.locked))
        if self.tracker:
            self.tracker.stop_event.set()
        self.camera_button.setText("Stopping…")
        self.camera_button.setEnabled(False)

    def refresh_flow(self):
        self.flow_running = any(p.info["name"] and p.info["name"].lower()=="flowspeak.exe"
                                for p in psutil.process_iter(["name"]))
        self.flow_label.setText("Running · Right Ctrl bridge ready" if self.flow_running else "Not running · launch FlowSpeak before dictating")

    def launch_flow(self):
        self.refresh_flow()
        if self.flow_running:
            return
        if not Path(self.flow_path).is_file():
            QMessageBox.information(self,"Locate FlowSpeak","Select your existing FlowSpeak.exe using Locate…")
            return
        try:
            subprocess.Popen([self.flow_path], cwd=str(Path(self.flow_path).parent))
            QTimer.singleShot(1200,self.refresh_flow)
        except OSError as exc:
            QMessageBox.warning(self,"FlowSpeak",str(exc))

    def browse_flow(self):
        path,_ = QFileDialog.getOpenFileName(self,"Locate FlowSpeak",str(Path(self.flow_path).parent),"FlowSpeak executable (*.exe)")
        if path:
            self.flow_path=path
            self.save_settings()

    def dispatch(self, actions):
        outgoing = []
        for action in actions:
            op = action[0]
            if op in ("move","drag"):
                if self.preview_only.isChecked():
                    continue
                position = (self.pointer.move(*action[1:],time.monotonic()) if op=="move" else self.pointer.drag(*action[1:]))
                if position:
                    outgoing.append(("move",*position))
            elif op == "left_down":
                self.pointer.start_drag(*action[1:], native.cursor())
                if not self.preview_only.isChecked():
                    outgoing.append(("left_down",))
            elif op == "voice_down":
                if not self.preview_only.isChecked():
                    if not self.flow_running:
                        self.engine.status = "Launch FlowSpeak, then pinch again"
                    elif native.user32.GetAsyncKeyState(0xA3) & 0x8000:
                        self.engine.status = "Release physical Right Ctrl, then pinch again"
                    else:
                        outgoing.append(("voice_down",))
                        self.voice_held = True
            elif op == "resume":
                self.pointer.position = native.cursor()
            elif op in ("enter", "switch_start"):
                if not self.preview_only.isChecked():
                    if any(native.user32.GetAsyncKeyState(k) & 0x8000 for k in (0x10,0x11,0x12,0x5B,0x5C)):
                        self.engine.status = "Release keyboard modifiers, then repeat the gesture"
                    else:
                        outgoing.append(action)
            elif op in ("release_all","voice_up","left_up","switch_end"):
                outgoing.append(action)
                if op in ("release_all","voice_up"):
                    self.voice_held = False
            elif not self.preview_only.isChecked():
                outgoing.append(action)
        if not self.broker_error:
            try:
                self.broker.send(outgoing)
            except (OSError, RuntimeError) as exc:
                logging.exception("Input bridge failed")
                self.broker_error = True
                self.engine.stop(True)
                self.voice_held = False
                self.status.setText(str(exc))

    def tick(self):
        if self.closing:
            return
        now = time.monotonic()
        frame = self.tracker.take() if self.tracker else None
        if frame:
            rgb, hand, side, stamp = frame
            self.last_frame_time, self.last_side, self.last_hand = stamp, side, hand
            if self.calibrator:
                self.calibrate_frame(hand if now-stamp<=0.25 else None,now)
            elif now-stamp <= 0.25:
                self.dispatch(self.engine.step(hand,now))
            else:
                self.dispatch(self.engine.step(None,now))
            h,w,c = rgb.shape
            self.preview.frame = QImage(rgb.data,w,h,rgb.strides[0],QImage.Format_RGB888).copy()
            self.preview.update()
        elif now-self.last_frame_time > 0.30:
            if self.calibrator:
                self.calibrate_frame(None,now)
            else:
                self.dispatch(self.engine.step(None,now))
        else:
            self.dispatch([])
        if self.tracker and not self.tracker.is_alive():
            if self.calibrator:
                self.finish_calibration(cancelled=True)
            error = self.tracker.error
            self.dispatch(self.engine.stop(self.engine.locked))
            self.tracker = None
            self.camera_button.setText("Start camera")
            self.camera_button.setEnabled(True)
            self.camera_index.setEnabled(True)
            self.preview.frame = None
            self.preview.message = error or "Camera is off. Start it when you are ready."
            self.preview.update()
            if error:
                self.engine.status = error
        active = bool(self.tracker and self.tracker.is_alive())
        badge = "CALIBRATING" if self.calibrator else "PREVIEW ONLY" if self.preview_only.isChecked() else "LOCKED" if self.engine.locked else "CONTROL OFF" if self.engine.paused else "CONTROL ON"
        self.badge.setText(badge if active else "CAMERA OFF")
        if not self.broker_error:
            self.status.setText(self.engine.status)
        else:
            self.status.setText("Input helper stopped — close and reopen GestureFlow")
        if self.tracker:
            self.fps_label.setText(f"{self.tracker.fps:.0f} FPS · local processing")
        if self.last_hand and active and now-self.last_frame_time < 0.4:
            extended = ', '.join(name for name, up in zip(('index', 'middle', 'ring', 'pinky'), self.last_hand.fingers) if up) or 'none'
            self.details.setText(f"{self.last_side} hand · extended: {extended} · middle contact {self.last_hand.middle_pinch:.2f} · ring contact {self.last_hand.ring_pinch:.2f}")
        else:
            required = self.hand_combo.currentText()
            self.details.setText("Show a hand, with your palm toward the camera." if required == "Either" else
                                 f"Show your {required.lower()} hand. The other hand is ignored.")
        if self.show_hud.isChecked() and active:
            text = ("PREVIEW · " if self.preview_only.isChecked() else "GestureFlow · ") + self.engine.status
            self.hud.display(text,self.voice_held)
            self.hud.show()
        else:
            self.hud.hide()
        if now-self.last_health > 2:
            self.last_health = now
            try:
                (ROOT/"work/status.json").write_text(json.dumps({"pid":os.getpid(),"camera":active,
                    "frames":self.tracker.frames if self.tracker else 0,"fps":round(self.tracker.fps,1) if self.tracker else 0,
                    "hand":self.last_side,"mode":self.engine.mode,"paused":self.engine.paused,
                    "locked":self.engine.locked,"preview":self.preview_only.isChecked(),"status":self.engine.status,
                    "flowspeak":self.flow_running,"input_helper":self.broker.process.poll(),
                    "gesture_features": {"extended": self.last_hand.fingers,
                        "middle_distance": self.last_hand.middle_pinch,
                        "ring_distance": self.last_hand.ring_pinch,
                        "activation_distance": self.engine.pinch_on} if self.last_hand and now-self.last_frame_time < 0.4 else None,
                    "time":time.time()},indent=2),encoding="utf-8")
            except OSError:
                pass

    def closeEvent(self,event):
        self.closing = True
        self.timer.stop()
        self.flow_timer.stop()
        self.save_settings()
        self.hud.close()
        self.emergency.close()
        QApplication.instance().removeNativeEventFilter(self.emergency)
        if self.tracker:
            self.tracker.stop_event.set()
        self.broker.close()
        if self.tracker:
            self.tracker.join(timeout=2)
        event.accept()

def make_icon():
    pixmap = QPixmap(64,64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#162d35"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0,0,64,64,15,15)
    painter.setPen(QColor("#91e4c5"))
    painter.setFont(QFont("Segoe UI",25,QFont.Bold))
    painter.drawText(pixmap.rect(),Qt.AlignCenter,"G")
    painter.end()
    return QIcon(pixmap)

def main():
    native.dpi_aware()
    (ROOT/"work").mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT/"work/gestureflow.log",level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",encoding="utf-8")
    app = QApplication(sys.argv)
    app.setApplicationName("GestureFlow")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    lock = QLockFile(str(ROOT/"work/gestureflow.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None,"GestureFlow","GestureFlow is already running. Open its existing window from the taskbar.")
        return 0
    def exception_hook(kind,value,trace):
        logging.critical("Unhandled exception",exc_info=(kind,value,trace))
        if hasattr(app,"window"):
            app.window.lock_controls(True)
    sys.excepthook=exception_hook
    window = Window("--preview" in sys.argv,"--no-camera" in sys.argv)
    app.window = window
    window.show()
    logging.info("GestureFlow started")
    result = app.exec()
    lock.unlock()
    return result
