"""Small, typed Win32 boundary. All injected holds are owned by the broker."""
import ctypes as C
from ctypes import wintypes as W

user32 = C.WinDLL("user32", use_last_error=True)
ULONG_PTR = C.c_size_t

class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]
class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
class INPUT(C.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", W.DWORD), ("value", INPUTUNION)]

user32.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
user32.SendInput.restype = W.UINT
user32.SetCursorPos.argtypes = [C.c_int, C.c_int]
user32.SetCursorPos.restype = W.BOOL
user32.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
user32.GetAsyncKeyState.argtypes = [C.c_int]
user32.GetAsyncKeyState.restype = W.SHORT

def send(item):
    if user32.SendInput(1, C.byref(item), C.sizeof(INPUT)) != 1:
        raise OSError(C.get_last_error(), "Windows rejected input (an elevated app may be focused)")

def mouse(flags, data=0):
    event = INPUT(type=0)
    event.mi = MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)
    send(event)

def right_control(down):
    event = INPUT(type=1)
    # E0 1D is right Control. FlowSpeak's WH_KEYBOARD_LL hook sees VK_RCONTROL.
    event.ki = KEYBDINPUT(0, 0x1D, 0x0008 | 0x0001 | (0 if down else 0x0002), 0, 0)
    send(event)

def enter_key(down):
    event = INPUT(type=1)
    event.ki = KEYBDINPUT(0, 0x1C, 0x0008 | (0 if down else 0x0002), 0, 0)
    send(event)

def switch_key(key, down):
    event = INPUT(type=1)
    event.ki = KEYBDINPUT(0, {"alt": 0x38, "tab": 0x0F}[key], 0x0008 | (0 if down else 0x0002), 0, 0)
    send(event)

def cursor():
    point = W.POINT()
    user32.GetCursorPos(C.byref(point))
    return point.x, point.y

def dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except (AttributeError, OSError):
        pass

def monitors():
    result = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HMONITOR, W.HDC, C.POINTER(W.RECT), W.LPARAM)
    class MONITORINFO(C.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]
    def callback(handle, dc, rect, data):
        info = MONITORINFO(cbSize=C.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(handle, C.byref(info))
        r = rect.contents
        result.append(((r.left, r.top, r.right-r.left, r.bottom-r.top), bool(info.dwFlags & 1)))
        return True
    user32.GetMonitorInfoW.argtypes = [W.HMONITOR, C.POINTER(MONITORINFO)]
    cb = callback_type(callback)
    user32.EnumDisplayMonitors(None, None, cb, 0)
    return sorted(result, key=lambda v: not v[1])
