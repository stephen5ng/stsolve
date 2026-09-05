#!/usr/bin/env python3
"""CommunicationMod listener with an opt-in command channel.

Reading is unconditional: every state the mod pushes is appended to
states.jsonl, exactly as the original passive listener did. That half is the
one the advisor depends on and it must never be able to break.

Writing is the new part, and it is deliberately awkward to reach. Commands are
accepted only from a named pipe (logs/../cmd.fifo) and forwarded verbatim to
stdout, which is CommunicationMod's command channel. Nothing in this process
ever invents a command -- it is a courier, not a player.

Why a FIFO and not a file the main loop polls: the main loop blocks on
sys.stdin, and the mod only pushes a state when something happens in the game.
A queued command would therefore sit unsent for as long as the game sat idle,
which is precisely when you most want to send one. A reader thread blocked on
the pipe has no such dependency.

Safety properties, in the order they matter:

- If the FIFO cannot be created, the command thread never starts and this file
  behaves exactly like observe.py.passive.bak. Degrading to passive is always
  the correct failure.
- Only whitelisted verbs are forwarded. A typo reaches the trace log, not
  the game.
- stdout is guarded by a lock and is written to from nowhere else, so a
  command can never be interleaved into the middle of another.
- Every command is traced with a timestamp before it is sent, so the log
  shows intent even if the game dies on receipt.
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
RAW = os.path.join(LOG_DIR, "states.jsonl")
TRACE = os.path.join(LOG_DIR, "trace.log")
FIFO = os.path.join(HERE, "cmd.fifo")

# CommunicationMod's verbs. Anything else is a typo or a mistake and is
# refused rather than forwarded. KEY and CLICK are deliberately absent: they
# are raw input injection, they bypass the mod's own validation, and nothing
# the advisor does needs them.
ALLOWED = {"start", "potion", "play", "end", "choose", "proceed", "return",
           "skip", "state", "wait", "cancel", "confirm", "leave"}

_out_lock = threading.Lock()


def trace(msg):
    with open(TRACE, "a") as f:
        f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
        f.flush()


def send(line):
    """Forward one command to the mod. Returns whether it was sent."""
    verb = line.split()[0].lower() if line.split() else ""
    if verb not in ALLOWED:
        trace("REFUSED (verb %r not allowed): %s" % (verb, line))
        return False
    with _out_lock:
        trace("--> %s" % line)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    return True


def command_reader():
    """Forward whatever is written to the FIFO, forever.

    Reopening on EOF is what makes `echo cmd > cmd.fifo` work repeatedly: each
    writer that opens and closes the pipe ends one read loop, and we go back
    to waiting for the next one.
    """
    while True:
        try:
            with open(FIFO, "r") as pipe:
                for line in pipe:
                    line = line.strip()
                    if line:
                        send(line)
        except Exception as e:            # never let this kill the listener
            trace("command reader error (%s), retrying in 1s" % e)
            time.sleep(1)


def start_command_channel():
    if not os.path.exists(FIFO):
        os.mkfifo(FIFO, 0o600)
    t = threading.Thread(target=command_reader, daemon=True)
    t.start()
    trace("command channel open at %s" % FIFO)


def summarize(state):
    """One line per state, enough to see whether manual play pushes updates."""
    if not state.get("in_game"):
        return "not in game (screen=%s)" % state.get("screen_type")
    g = state.get("game_state", {})
    bits = ["floor=%s" % g.get("floor"), "room=%s" % g.get("room_phase"),
            "hp=%s/%s" % (g.get("current_hp"), g.get("max_hp"))]
    cs = g.get("combat_state")
    if cs:
        p = cs.get("player", {})
        bits.append("turn=%s" % cs.get("turn"))
        bits.append("energy=%s" % p.get("energy"))
        bits.append("block=%s" % p.get("block"))
        bits.append("hand=[%s]" % ",".join(c["name"] for c in cs.get("hand", [])))
        for m in cs.get("monsters", []):
            if m.get("is_gone"):
                continue
            bits.append("%s(%s/%s %s %sx%s)" % (
                m.get("name"), m.get("current_hp"), m.get("max_hp"),
                m.get("intent"), m.get("move_adjusted_damage"), m.get("move_hits")))
    return "  ".join(bits)


def main():
    trace("=== started, pid=%d ===" % os.getpid())
    sys.stdout.write("ready\n")
    sys.stdout.flush()
    trace("sent ready")

    try:
        start_command_channel()
    except Exception as e:
        # Passive is a perfectly good mode. Losing the reader is not a reason
        # to lose the log as well.
        trace("no command channel (%s) -- running passive" % e)

    n = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        n += 1
        with open(RAW, "a") as f:
            f.write(line + "\n")
        try:
            state = json.loads(line)
        except ValueError as e:
            trace("#%d UNPARSEABLE (%s): %s" % (n, e, line[:200]))
            continue
        # The mod reports a rejected command in the very next state it pushes.
        # Surfacing it here is the only feedback a command ever gets.
        if state.get("error"):
            trace("#%d MOD ERROR: %s" % (n, state["error"]))
        trace("#%d %s" % (n, summarize(state)))

    trace("=== stdin closed after %d states ===" % n)


if __name__ == "__main__":
    main()
