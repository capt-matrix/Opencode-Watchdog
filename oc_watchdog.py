#!/usr/bin/env python3
"""
oc_watchdog.py — OpenCode doom-loop watchdog
"""

import subprocess
import time
import re
import sys
import argparse
import shutil
import threading
import select
from collections import deque

# ── Config ────────────────────────────────────────────────────────────────────
POLL_INTERVAL   = 2
REPEAT_WINDOW   = 12
REPEAT_THRESH   = 4
MIN_PHRASE_LEN  = 8
COOLDOWN        = 8
STUCK_MSG       = "you were looping, watch that out next time strictly, now continue with your incomplete process"

LOOP_PHRASES = [
    "let me run",
    "let me check",
    "let me try",
    "let me now",
    "let me execute",
    "let me re-run",
    "let me verify",
    "running the",
    "i'll run",
    "i will run",
]
# ─────────────────────────────────────────────────────────────────────────────

paused        = False
user_phrases  = []
phrase_lock   = threading.Lock()


def tmux(*args):
    result = subprocess.run(["tmux"] + list(args), capture_output=True, text=True)
    return result.stdout.strip()


def capture_pane(session, pane):
    return tmux("capture-pane", "-p", "-t", f"{session}:{pane}")


def send_escape(session, pane):
    tmux("send-keys", "-t", f"{session}:{pane}", "Escape", "")
    time.sleep(0.15)
    tmux("send-keys", "-t", f"{session}:{pane}", "Escape", "")
    time.sleep(0.15)


def send_text_enter(session, pane, text):
    tmux("send-keys", "-t", f"{session}:{pane}", text, "")
    time.sleep(0.1)
    tmux("send-keys", "-t", f"{session}:{pane}", "Enter", "")


def strip_let_me(phrase):
    return re.sub(r'^let me\s+', '', phrase, flags=re.IGNORECASE).strip()


def format_trigger(trigger):
    cleaned = strip_let_me(trigger)
    cleaned = cleaned.replace('\n', ', ').replace('\r', '')
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def count_phrase_repetitions(lines, phrase):
    p = phrase.lower()
    return sum(1 for l in lines if p in l.lower())


def detect_loop(recent_lines):
    # Check known loop phrases
    for phrase in LOOP_PHRASES:
        count = count_phrase_repetitions(recent_lines, phrase)
        if count >= REPEAT_THRESH:
            return True, phrase

    # Check raw line repetition
    cleaned = [
        re.sub(r'\s+', ' ', l).strip()
        for l in recent_lines
        if len(l.strip()) >= MIN_PHRASE_LEN
    ]
    freq = {}
    for line in cleaned:
        freq[line] = freq.get(line, 0) + 1
    for line, count in freq.items():
        if count >= REPEAT_THRESH:
            return True, line[:60]

    return False, None


def build_stuck_message(trigger):
    return STUCK_MSG


def input_listener():
    """
    Runs in a background thread.
    - Typing anything pauses the watchdog and waits for input.
    - Empty line = resume.
    - 'add: some phrase' = add a custom loop phrase.
    - 'quit' or 'exit' = clean shutdown.
    """
    global paused
    print("[watchdog] Input listener ready. Type to pause | 'add: phrase' to add trigger | 'quit' to exit")
    while True:
        try:
            line = input()
        except EOFError:
            break

        line = line.strip()

        if line.lower() == 'exit':
            print("[watchdog] Stopping watchdog...")
            sys.exit(0)

        if line.lower() == 'quit':
            print("[watchdog] Killing session...")
            subprocess.run(["tmux", "kill-server"])
            sys.exit(0)

        if line.lower().startswith('add:'):
            phrase = line[4:].strip().lower()
            if phrase:
                with phrase_lock:
                    LOOP_PHRASES.append(phrase)
                    user_phrases.append(phrase)
                print(f"[watchdog] ✓ Added loop phrase: '{phrase}'")
            continue

        if not paused:
            paused = True
            print("[watchdog] ⏸  Paused. Press Enter to resume (or type a message to inject into opencode).")
        else:
            if line:
                # They typed a message — treat it as a custom injection
                print(f"[watchdog] → Injecting your message: '{line}'")
                # Store it for the main loop to pick up
                with phrase_lock:
                    user_phrases.insert(0, f"__inject__:{line}")
            paused = False
            print("[watchdog] ▶  Resumed.")


def get_tmux_sessions():
    out = tmux("list-sessions", "-F", "#{session_name}")
    return out.splitlines() if out else []


def run_watchdog(session, pane):
    global paused

    print(f"[watchdog] Monitoring tmux {session}:{pane}")
    print(f"[watchdog] Trigger: {REPEAT_THRESH}x repetition in last {REPEAT_WINDOW} lines")
    print(f"[watchdog] Intervention: Esc → Esc → message → Enter")
    print(f"[watchdog] Cooldown: {COOLDOWN}s between interventions")
    print("─" * 60)

    # Start input listener thread
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()

    history            = deque(maxlen=REPEAT_WINDOW)
    last_action        = 0
    intervention_count = 0

    while True:
        try:
            # Check for user-injected messages
            with phrase_lock:
                injections = [p for p in user_phrases if p.startswith('__inject__:')]
                for inj in injections:
                    user_phrases.remove(inj)
                    msg = inj[len('__inject__:'):]
                    send_escape(session, pane)
                    time.sleep(0.3)
                    send_escape(session, pane)
                    time.sleep(0.4)
                    send_text_enter(session, pane, msg)
                    print(f"[watchdog] ✓ User message injected.")

            if paused:
                time.sleep(POLL_INTERVAL)
                continue

            raw = capture_pane(session, pane)
            lines = [l for l in raw.splitlines() if l.strip()]
            history.extend(lines)

            looping, trigger = detect_loop(list(history))
            now = time.time()

            if looping and (now - last_action) > COOLDOWN:
                intervention_count += 1
                msg = build_stuck_message(trigger)

                print(f"\n[watchdog] ⚠ Loop #{intervention_count} — trigger: '{trigger}'")
                print(f"[watchdog] → Sending: '{msg}'")

                send_escape(session, pane)
                time.sleep(0.3)
                send_escape(session, pane)
                time.sleep(0.4)
                send_text_enter(session, pane, msg)

                last_action = now
                history.clear()
                print(f"[watchdog] ✓ Done. Cooling down {COOLDOWN}s…\n")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print(f"\n[watchdog] Stopped. Total interventions: {intervention_count}")
            break
        except Exception as e:
            print(f"[watchdog] Error: {e}")
            time.sleep(POLL_INTERVAL)


def main():
    global REPEAT_THRESH, COOLDOWN, STUCK_MSG

    if not shutil.which("tmux"):
        print("Error: tmux not found.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="OpenCode doom-loop watchdog")
    parser.add_argument("session", nargs="?", help="tmux session name")
    parser.add_argument("pane",    nargs="?", default="0")
    parser.add_argument("--thresh",   type=int, default=REPEAT_THRESH)
    parser.add_argument("--cooldown", type=int, default=COOLDOWN)
    parser.add_argument("--msg",      type=str, default=STUCK_MSG)
    args = parser.parse_args()

    REPEAT_THRESH = args.thresh
    COOLDOWN      = args.cooldown
    STUCK_MSG     = args.msg

    if args.session:
        session, pane = args.session, args.pane
    else:
        sessions = get_tmux_sessions()
        if not sessions:
            print("No tmux sessions found.")
            sys.exit(1)
        session, pane = sessions[0], "0"

    run_watchdog(session, pane)


if __name__ == "__main__":
    main()
