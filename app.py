"""Menu bar dictation daemon.

Hold Fn to talk; release to transcribe (local whisper.cpp), clean up
(Claude Haiku), and type the result into the focused text field.
Double-tap Fn for hands-free recording; tap again to stop.
"""

import os
import sys
import threading

import rumps
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSEvent,
    NSEventMaskFlagsChanged,
    NSEventMaskKeyDown,
    NSWorkspace,
    NSWorkspaceDidWakeNotification,
)
from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetMain,
    CFRunLoopRemoveSource,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventTapIsEnabled,
    CFMachPortInvalidate,
    kCFRunLoopCommonModes,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionListenOnly,
    kCGHeadInsertEventTap,
    kCGSessionEventTap,
)
from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
from Foundation import NSOperationQueue
from HIServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)

import cleanup
import config
import history
import inject
import transcribe
from audio import Recorder
from fsm import Action, DictationFSM, State


class DictateApp(rumps.App):
    def __init__(self):
        super().__init__("Dictate", title=config.ICON_IDLE, quit_button="Quit")
        # Menu-bar-only utility: no Dock icon, no Cmd+Tab entry.
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        self.menu = [rumps.MenuItem("History...", callback=self._show_history)]
        self._fsm = DictationFSM()
        self._recorder = Recorder()
        self._flag_mask, self._keycode = config.HOTKEY_SPECS[config.HOTKEY]
        self._monitors = []
        self._tap = None
        self._tap_source = None
        self._tap_failures = 0

        print("Loading whisper model...", flush=True)
        self._transcriber = transcribe.Transcriber()
        self._cleaner = cleanup.Cleaner()
        print("Ready. Hold Fn to dictate; double-tap Fn for hands-free.", flush=True)

        self._request_permissions()
        self._install_monitors()
        self._install_wake_observer()
        self._install_rearm_timer()
        self._install_watchdog()

    # --- permissions ---

    def _request_permissions(self):
        trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        if not trusted:
            print(
                "Waiting for Accessibility permission "
                "(System Settings > Privacy & Security > Accessibility). "
                "Grant it, then restart the app.",
                flush=True,
            )
        # PortAudio never triggers the TCC dialog, so ask AVFoundation
        # directly; without this macOS silently records zeros.
        self._request_mic_access()

    def _request_mic_access(self):
        # 0=notDetermined 1=restricted 2=denied 3=authorized
        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        if status == 3:
            return
        if status == 2:
            print(
                "Microphone permission DENIED — enable 'Python' in "
                "System Settings > Privacy & Security > Microphone, "
                "then restart the app.",
                flush=True,
            )
            return

        def handler(granted):
            print(f"Microphone access granted: {bool(granted)}", flush=True)

        print("Requesting Microphone permission...", flush=True)
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio, handler
        )

    # --- hotkey capture ---

    def _install_monitors(self):
        # Primary: a CGEventTap, which (unlike NSEvent global monitors) can be
        # health-checked and re-enabled. NSEvent monitors are the fallback if
        # the tap can't be created (e.g. Input Monitoring not granted).
        self._remove_monitors()
        if self._install_tap():
            return
        print("event tap unavailable (Input Monitoring?) — using NSEvent fallback", flush=True)
        self._install_ns_monitors()

    def _install_tap(self):
        mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown)

        def callback(proxy, etype, cgevent, refcon):
            try:
                if etype in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                    print("event tap was disabled by the system — re-enabling", flush=True)
                    if self._tap is not None:
                        CGEventTapEnable(self._tap, True)
                    return cgevent
                event = NSEvent.eventWithCGEvent_(cgevent)
                if event is not None:
                    if etype == kCGEventFlagsChanged:
                        self._on_flags_changed(event)
                    else:
                        self._on_key_down(event)
            except Exception as exc:
                print(f"event tap handler error: {exc}", file=sys.stderr, flush=True)
            return cgevent

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            callback,
            None,
        )
        if tap is None:
            return False
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        self._tap, self._tap_source = tap, source
        return True

    def _remove_tap(self):
        if self._tap is None:
            return
        CGEventTapEnable(self._tap, False)
        CFRunLoopRemoveSource(CFRunLoopGetMain(), self._tap_source, kCFRunLoopCommonModes)
        CFMachPortInvalidate(self._tap)
        self._tap = self._tap_source = None

    def _install_ns_monitors(self):
        handler_global = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._on_flags_changed
        )
        handler_local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._on_flags_changed_local
        )
        history_global = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, self._on_key_down
        )
        history_local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, self._on_key_down_local
        )
        self._monitors = [handler_global, handler_local, history_global, history_local]

    def _remove_monitors(self):
        self._remove_tap()
        for monitor in self._monitors:
            if monitor is not None:
                NSEvent.removeMonitor_(monitor)
        self._monitors = []

    def _install_wake_observer(self):
        # Global NSEvent monitors can silently stop delivering events after
        # enough sleep/wake cycles (no crash, no error — they just go dead).
        # Re-arming them on every wake keeps the hotkey reliable without
        # requiring a manual daemon restart. Block-based observer (rather
        # than a selector target) since DictateApp/rumps.App isn't an
        # NSObject subclass.
        NSWorkspace.sharedWorkspace().notificationCenter().addObserverForName_object_queue_usingBlock_(
            NSWorkspaceDidWakeNotification, None, NSOperationQueue.mainQueue(), self._on_wake
        )

    def _on_wake(self, notification):
        print("system woke — re-arming hotkey monitors", flush=True)
        self._install_monitors()

    def _install_rearm_timer(self):
        # The wake observer above isn't sufficient on its own: global NSEvent
        # monitors have been observed going dead without a wake in between
        # (or with a wake notification that never fired), leaving the daemon
        # silently unresponsive until a manual restart. This timer re-arms
        # the monitors unconditionally on a fixed interval, bounding how long
        # the hotkey can stay dead to one interval instead of indefinitely.
        self._rearm_timer = rumps.Timer(
            self._periodic_rearm, config.MONITOR_REARM_INTERVAL_SECONDS
        )
        self._rearm_timer.start()

    def _periodic_rearm(self, _timer):
        if self._fsm.state is not State.IDLE:
            return  # avoid swapping monitors out from under an active recording
        self._install_monitors()

    def _install_watchdog(self):
        self._watchdog = rumps.Timer(
            self._check_health, config.WATCHDOG_INTERVAL_SECONDS
        )
        self._watchdog.start()

    def _check_health(self, _timer):
        # Tap alive and enabled -> healthy. Otherwise rebuild; if rebuilding
        # keeps failing, exit non-zero so launchd restarts the whole process.
        if self._fsm.state is not State.IDLE:
            return
        if self._tap is not None and CGEventTapIsEnabled(self._tap):
            self._tap_failures = 0
            return
        if self._tap is None and self._monitors:
            return  # running on NSEvent fallback; periodic re-arm covers it
        print("hotkey tap unhealthy — rebuilding", flush=True)
        self._install_monitors()
        if self._tap is not None and CGEventTapIsEnabled(self._tap):
            self._tap_failures = 0
            return
        self._tap_failures += 1
        if self._tap_failures >= 3:
            print("hotkey tap cannot be restored — exiting for launchd restart", flush=True)
            os._exit(1)

    def _on_flags_changed_local(self, event):
        self._on_flags_changed(event)
        return event

    def _on_flags_changed(self, event):
        try:
            if event.keyCode() != self._keycode:
                return
            pressed = bool(event.modifierFlags() & self._flag_mask)
            action = self._fsm.on_key_down() if pressed else self._fsm.on_key_up()
            self._dispatch(action)
        except Exception as exc:
            print(f"hotkey handler error: {exc}", file=sys.stderr, flush=True)

    def _on_key_down_local(self, event):
        self._on_key_down(event)
        return event

    def _on_key_down(self, event):
        # Cmd+Shift+H opens the history window from any app, since the
        # menu bar icon can be easy to miss (crowded bar / notch-adjacent).
        try:
            if event.keyCode() != config.HISTORY_HOTKEY_KEYCODE:
                return
            if (event.modifierFlags() & config.HISTORY_HOTKEY_FLAGS) != config.HISTORY_HOTKEY_FLAGS:
                return
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._show_history(None)
            )
        except Exception as exc:
            print(f"history hotkey handler error: {exc}", file=sys.stderr, flush=True)

    # --- state machine actions ---

    def _dispatch(self, action: Action):
        if action == Action.START_RECORDING:
            self._recorder.start()
            self._set_icon(config.ICON_RECORDING)
        elif action == Action.LOCK:
            self._set_icon(config.ICON_LOCKED)
        elif action == Action.STOP_AND_DISCARD:
            self._recorder.discard()
            self._set_icon(config.ICON_IDLE)
        elif action == Action.STOP_AND_PROCESS:
            samples = self._recorder.stop()
            self._set_icon(config.ICON_IDLE)
            threading.Thread(
                target=self._process, args=(samples,), daemon=True
            ).start()

    def _process(self, samples):
        try:
            peak = float(abs(samples).max()) if samples.size else 0.0
            transcript = self._transcriber.transcribe(samples)
            print(
                f"recorded {samples.size / config.SAMPLE_RATE:.1f}s "
                f"(peak {peak:.4f}) -> transcript: {transcript!r}",
                flush=True,
            )
            if peak < 0.001 and samples.size:
                print(
                    "audio is silent — Microphone permission for 'Python' is "
                    "likely missing (System Settings > Privacy & Security > "
                    "Microphone).",
                    flush=True,
                )
            if not transcript:
                return
            cleaned = self._cleaner.clean(transcript)
            print(f"cleaned: {cleaned!r}", flush=True)
            history.add_entry(transcript, cleaned)
            if cleaned:
                if not AXIsProcessTrusted():
                    print(
                        "cannot inject: Accessibility permission for 'Python' "
                        "is missing (System Settings > Privacy & Security > "
                        "Accessibility) — macOS drops the paste keystroke.",
                        flush=True,
                    )
                inject.inject_text(cleaned)
        except Exception as exc:
            print(f"processing error: {exc}", file=sys.stderr, flush=True)

    def _show_history(self, sender):
        import history_window

        history_window.show_history_window()

    def _set_icon(self, icon: str):
        def update():
            self.title = icon
        NSOperationQueue.mainQueue().addOperationWithBlock_(update)


def main():
    cleanup.require_api_key()
    DictateApp().run()


if __name__ == "__main__":
    main()
