"""Explicit finite state machine for the single-hotkey interaction model.

Driven purely by hotkey down/up transitions (from flagsChanged events):

  IDLE --down--> HOLD (recording starts)
  HOLD --up (< MIN_HOLD, no pending tap)--> IDLE, discard (mis-press / 1st tap)
  HOLD --up (>= MIN_HOLD)--> IDLE, process recording      (hold-to-talk)
  HOLD --up (2nd quick tap within window)--> LOCKED       (hands-free)
  LOCKED --down+up--> IDLE, process recording             (hands-free stop)
"""

import enum
import time

import config


class State(enum.Enum):
    IDLE = "idle"
    HOLD = "hold"       # hotkey held, recording
    LOCKED = "locked"   # hands-free, recording


class Action(enum.Enum):
    NONE = "none"
    START_RECORDING = "start_recording"
    STOP_AND_PROCESS = "stop_and_process"
    STOP_AND_DISCARD = "stop_and_discard"
    LOCK = "lock"  # keep recording, switch icon to hands-free


class DictationFSM:
    def __init__(self):
        self.state = State.IDLE
        self._press_time = 0.0
        self._last_tap_up = -1.0  # time of a recent short tap's release

    def on_key_down(self, now: float | None = None) -> Action:
        now = time.monotonic() if now is None else now
        if self.state == State.IDLE:
            self._press_time = now
            self.state = State.HOLD
            return Action.START_RECORDING
        return Action.NONE  # LOCKED: stop happens on key up

    def on_key_up(self, now: float | None = None) -> Action:
        now = time.monotonic() if now is None else now
        if self.state == State.HOLD:
            held = now - self._press_time
            is_tap = held < config.DOUBLE_TAP_WINDOW_SECONDS
            follows_tap = (self._press_time - self._last_tap_up) < config.DOUBLE_TAP_WINDOW_SECONDS
            if is_tap and follows_tap:
                self._last_tap_up = -1.0
                self.state = State.LOCKED
                return Action.LOCK
            if held < config.MIN_HOLD_SECONDS:
                # mis-press, or the first tap of a potential double-tap
                self._last_tap_up = now
                self.state = State.IDLE
                return Action.STOP_AND_DISCARD
            self._last_tap_up = -1.0
            self.state = State.IDLE
            return Action.STOP_AND_PROCESS
        if self.state == State.LOCKED:
            self._last_tap_up = -1.0
            self.state = State.IDLE
            return Action.STOP_AND_PROCESS
        return Action.NONE
