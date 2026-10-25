"""Inject text at the cursor: pasteboard + simulated Cmd+V, then restore."""

import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

import config

_KEY_V = 9
_CMD_FLAG = Quartz.kCGEventFlagMaskCommand


def _paste_keystroke():
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    key_down = Quartz.CGEventCreateKeyboardEvent(source, _KEY_V, True)
    key_up = Quartz.CGEventCreateKeyboardEvent(source, _KEY_V, False)
    Quartz.CGEventSetFlags(key_down, _CMD_FLAG)
    Quartz.CGEventSetFlags(key_up, _CMD_FLAG)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)


def inject_text(text: str):
    if not text:
        return
    pasteboard = NSPasteboard.generalPasteboard()
    previous = pasteboard.stringForType_(NSPasteboardTypeString)

    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)
    time.sleep(0.05)  # let the pasteboard change propagate before pasting
    _paste_keystroke()

    time.sleep(config.PASTE_SETTLE_SECONDS)
    pasteboard.clearContents()
    if previous is not None:
        pasteboard.setString_forType_(previous, NSPasteboardTypeString)
