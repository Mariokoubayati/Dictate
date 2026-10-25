"""Unit test for the interaction state machine (no hardware needed)."""

import config
from fsm import Action, DictationFSM, State


def run():
    # 1. Hold-to-talk: down, hold 1s, up -> process
    m = DictationFSM()
    assert m.on_key_down(10.0) == Action.START_RECORDING
    assert m.on_key_up(11.0) == Action.STOP_AND_PROCESS
    assert m.state == State.IDLE

    # 2. Mis-press: down-up in 80ms -> discard
    m = DictationFSM()
    assert m.on_key_down(10.0) == Action.START_RECORDING
    assert m.on_key_up(10.08) == Action.STOP_AND_DISCARD
    assert m.state == State.IDLE

    # 3. Double-tap -> hands-free lock, third tap -> process
    m = DictationFSM()
    assert m.on_key_down(10.00) == Action.START_RECORDING
    assert m.on_key_up(10.08) == Action.STOP_AND_DISCARD
    assert m.on_key_down(10.20) == Action.START_RECORDING  # 2nd tap within 300ms
    assert m.on_key_up(10.28) == Action.LOCK
    assert m.state == State.LOCKED
    assert m.on_key_down(15.0) == Action.NONE
    assert m.on_key_up(15.1) == Action.STOP_AND_PROCESS
    assert m.state == State.IDLE

    # 4. Two taps too far apart -> both discarded, no lock
    m = DictationFSM()
    m.on_key_down(10.0)
    assert m.on_key_up(10.08) == Action.STOP_AND_DISCARD
    m.on_key_down(10.5)  # 420ms after first tap's release
    assert m.on_key_up(10.58) == Action.STOP_AND_DISCARD

    # 5. Tap then long hold -> hold-to-talk, not lock
    m = DictationFSM()
    m.on_key_down(10.0)
    m.on_key_up(10.08)
    m.on_key_down(10.2)
    assert m.on_key_up(12.0) == Action.STOP_AND_PROCESS

    # 6. Hold slightly over mis-press threshold but under tap window,
    #    not following a tap -> processed as a (short) hold
    m = DictationFSM()
    m.on_key_down(10.0)
    assert m.on_key_up(10.2) == Action.STOP_AND_PROCESS

    print("FSM tests: all passed")


if __name__ == "__main__":
    run()
