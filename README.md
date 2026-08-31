# Opencode Watchdog

Monitors a running [opencode](https://opencode.ai) session and automatically breaks doom-loops — when the AI gets stuck repeating itself, the watchdog injects a message to snap it out and resume the task.

```
┌─────────────────────────────────┬──────────────────┐
│                                 │ [watchdog] ▶     │
│   opencode . -c                 │ Monitoring oc:0  │
│                                 │ Trigger: 4x rep  │
│   > let me run the tests        │                  │
│   > let me run the tests        │ ⚠ Loop #1        │
│   > let me run the tests        │ → Injecting msg  │
│                                 │ ✓ Cooling 8s…    │
└─────────────────────────────────┴──────────────────┘
```

---

## How it works

Every 2 seconds the watchdog captures the visible tmux pane. If it sees the same phrase 4+ times in the last 12 lines — either from a built-in list of known loop phrases (`let me run`, `let me check`, etc.) or any raw line repeating — it sends:

```
Esc → Esc → "you were looping, watch that out next time strictly, now continue with your incomplete process" → Enter
```

Then waits 8 seconds (cooldown) before it can intervene again.

---

## Requirements

| Dependency | macOS | Linux |
|---|---|---|
| Python 3 | pre-installed (3.9+) or `brew install python` | `sudo apt install python3` / `sudo dnf install python3` |
| tmux | `brew install tmux` | `sudo apt install tmux` / `sudo dnf install tmux` |
| opencode | `brew install opencode` | see [opencode docs](https://opencode.ai) |

> **Windows:** Not supported — requires tmux which is unavailable on native Windows. Use WSL2 with the Linux instructions above.

---

## Install

### 1. Clone the repo

```bash
git clone git@github.com:capt-matrix/Opencode-Watchdog.git
cd Opencode-Watchdog
```

### 2. Copy files to `~/.local/bin`

```bash
mkdir -p ~/.local/bin
cp oc_watchdog.py ~/.local/bin/oc_watchdog.py
cp ocw ~/.local/bin/ocw
chmod +x ~/.local/bin/oc_watchdog.py ~/.local/bin/ocw
```

### 3. Add `~/.local/bin` to your PATH

**zsh** (`~/.zshrc`):
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**bash** (`~/.bashrc`):
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Verify:
```bash
which ocw          # should print /Users/you/.local/bin/ocw
which python3      # must return a path
```

---

## Usage

### The easy way — `ocw`

One command opens opencode and the watchdog side by side in a tmux split:

```bash
ocw
```

opencode takes the left 70%, watchdog logs take the right 30%. opencode is focused by default — you work normally and the watchdog runs silently in the background.

## Stopping

From inside the tmux session:
- `Ctrl+b` then `:kill-session` — kills opencode + watchdog together

From another terminal:
- `ocw stop`

**With options:**

```bash
ocw --cooldown 5          # intervene every 5s instead of 8s
ocw --cooldown 5 --thresh 3   # also trigger after 3 repetitions instead of 4
ocw --msg "stop and try a different approach"  # custom intervention message
ocw --session myproject   # use a custom tmux session name
```

**Environment variable defaults** (set once in `~/.zshrc`):

```bash
export OCW_COOLDOWN=5
export OCW_THRESH=3
```

Then just `ocw` picks them up automatically.

---

### The manual way — two terminals

If you want opencode fully visible in one terminal and watchdog in another:

**Terminal 1:**
```bash
tmux new -s oc
opencode . -c
```

**Terminal 2:**
```bash
oc_watchdog oc 0 --cooldown 8
```

---

### Watchdog-only (point at existing session)

```bash
oc_watchdog <session> <pane> [options]

oc_watchdog oc 0                       # attach to session 'oc', pane 0
oc_watchdog oc 0 --cooldown 5
oc_watchdog oc 0 --thresh 3
oc_watchdog oc 0 --msg "stop looping"
```

If you omit session/pane it auto-picks the first active tmux session.

---

## Watchdog controls (while running)

With the watchdog active in the right pane, you can interact with it live:

| What you type | What happens |
|---|---|
| Any key + Enter | Pauses the watchdog, prompts for input |
| Enter (empty, while paused) | Resumes monitoring |
| A message + Enter (while paused) | Injects that message into opencode, then resumes |
| `add: let me think` | Adds `let me think` as a new loop trigger phrase |
| `quit` / `exit` / `q` | Stops the watchdog cleanly |

---

## Options reference

| Flag | Default | Description |
|---|---|---|
| `--cooldown N` | `8` | Seconds to wait between interventions |
| `--thresh N` | `4` | Repetitions needed to trigger intervention |
| `--msg "..."` | see below | Custom message injected when loop detected |

**Default message:**
```
you were looping, watch that out next time strictly, now continue with your incomplete process
```

---

## Built-in loop phrases

The watchdog triggers if any of these appear 4+ times in the last 12 lines:

```
let me run       let me check     let me try
let me now       let me execute   let me re-run
let me verify    running the      i'll run
i will run
```

Add your own at runtime with `add: phrase`, or edit `LOOP_PHRASES` in `oc_watchdog.py`.

---

## Files

```
oc_watchdog.py   — the watchdog (Python 3, stdlib only)
ocw              — launcher script (bash)
```

No external Python packages required.

---
