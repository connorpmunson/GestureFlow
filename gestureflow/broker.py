"""Input subprocess: EOF or a missed heartbeat releases every owned hold."""
import json
import logging
import queue
import sys
import threading
import time
from . import native


class InputOwner:
    def __init__(self, backend=native):
        self.backend = backend
        self.left = False
        self.voice = False
        self.enter_held = False
        self.switch_held = set()

    def apply(self, command):
        op = command[0]
        if self.switch_held and op not in ("switch_next", "switch_end", "release_all"):
            return
        if op == "move":
            self.backend.user32.SetCursorPos(int(command[1]), int(command[2]))
        elif op == "left_down" and not self.left and not self.voice:
            self.backend.mouse(0x0002)
            self.left = True
        elif op == "left_up" and self.left:
            self.backend.mouse(0x0004)
            self.left = False
        elif op == "voice_down" and not self.voice and not self.left:
            self.backend.right_control(True)
            self.voice = True
        elif op == "voice_up" and self.voice:
            self.backend.right_control(False)
            self.voice = False
        elif op == "right_click" and not self.voice and not self.left:
            self.backend.mouse(0x0008)
            self.backend.mouse(0x0010)
        elif op == "scroll" and not self.voice and not self.left:
            self.backend.mouse(0x0800, int(command[1]))
        elif op == "enter" and not self.voice and not self.left and not self.enter_held:
            self.backend.enter_key(True)
            self.enter_held = True
            self.backend.enter_key(False)
            self.enter_held = False
        elif op == "switch_start" and not self.voice and not self.left and not self.switch_held:
            self.backend.switch_key("alt", True)
            self.switch_held.add("alt")
            self.advance_switch()
        elif op == "switch_next" and "alt" in self.switch_held:
            self.advance_switch()
        elif op == "switch_end":
            self.release_switch()
        elif op == "release_all":
            self.release()

    def advance_switch(self):
        self.backend.switch_key("tab", True)
        self.switch_held.add("tab")
        self.backend.switch_key("tab", False)
        self.switch_held.remove("tab")

    def release_switch(self):
        try:
            if "tab" in self.switch_held:
                self.backend.switch_key("tab", False)
                self.switch_held.remove("tab")
        finally:
            if "alt" in self.switch_held:
                self.backend.switch_key("alt", False)
                self.switch_held.remove("alt")

    def release(self):
        # Retry failed releases on the next heartbeat instead of forgetting ownership.
        try:
            self.apply(["left_up"])
        finally:
            try:
                self.apply(["voice_up"])
            finally:
                try:
                    if self.enter_held:
                        self.backend.enter_key(False)
                        self.enter_held = False
                finally:
                    self.release_switch()


def main():
    native.dpi_aware()
    inbox = queue.Queue()
    def read():
        try:
            for line in sys.stdin:
                inbox.put(json.loads(line))
        finally:
            inbox.put(None)
    threading.Thread(target=read, daemon=True).start()
    owner = InputOwner()
    last = time.monotonic()
    release_pending = False
    try:
        while True:
            try:
                item = inbox.get(timeout=0.08)
            except queue.Empty:
                item = "tick"
            if item is None:
                break
            if release_pending:
                try:
                    owner.release()
                    release_pending = False
                except OSError:
                    continue
            if item != "tick":
                # Expired command batches may never reactivate a stale hold.
                if time.monotonic() - item["time"] < 0.5:
                    last = time.monotonic()
                    for command in item["actions"]:
                        try:
                            owner.apply(command)
                        except OSError:
                            logging.exception("Input rejected; releasing held inputs before accepting more")
                            release_pending = True
                            break
            if time.monotonic() - last > 0.65:
                try:
                    owner.release()
                except OSError:
                    release_pending = True
                    logging.exception("Release rejected; retrying on the next heartbeat")
    finally:
        for attempt in range(10):
            try:
                owner.release()
                break
            except OSError:
                time.sleep(0.05)

if __name__ == "__main__":
    main()
