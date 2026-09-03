#!/usr/bin/env python3
"""Passive CommunicationMod listener.

Handshake test: send "ready", then read state forever and send NOTHING back.
If the game stays playable with this attached, observe-while-you-play works
and we can build the advisor on top. If the game freezes on the first state,
the mod blocks on a command and this whole approach is dead.

stdout is the command channel -- anything printed there is parsed as a
command. All output goes to the log files instead.
"""
import json
import os
import sys
import time

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
RAW = os.path.join(LOG_DIR, "states.jsonl")
TRACE = os.path.join(LOG_DIR, "trace.log")


def trace(msg):
    with open(TRACE, "a") as f:
        f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
        f.flush()


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
        trace("#%d %s" % (n, summarize(state)))
        # Deliberately send no command. This is the blocking test.

    trace("=== stdin closed after %d states ===" % n)


if __name__ == "__main__":
    main()
