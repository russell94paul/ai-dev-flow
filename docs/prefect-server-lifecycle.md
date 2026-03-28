# Prefect Server Lifecycle — Design Spike

**Status:** Design spike (not yet implemented)
**Date:** 2026-03-27
**Context:** `ai prefect-run` starts a local Prefect v3 server when needed. Two gaps exist:
1. When the server was already running before `ai prefect-run`, it is never stopped (no PID to track).
2. A future `ai prefect-stop` command needs to kill only the server _we_ started, not every Python process on the machine.

---

## Current Behaviour

| Path | `sandbox_proc` | Cleanup |
|------|---------------|---------|
| Server not running → we start it | `Popen` object | `terminate()` + `wait()` at end |
| Server already running, same version | `None` | ⚠️ never stopped — warning printed |
| Server running, version mismatch | killed via `taskkill /F /PID <port-pid>`, then we start fresh | `terminate()` + `wait()` at end |

The version-mismatch kill uses `netstat` to find the PID listening on port 4200 and calls `taskkill /F /PID`. This is safe because it targets a specific PID, not a process name.

---

## Problem: `already_up=True` Path

When the server was already up:
- `sandbox_proc = None`
- The cleanup block (`if sandbox_proc is not None`) never runs
- Server stays running after `ai prefect-run` exits
- No way to stop it without killing all `python.exe` processes (unsafe on Windows)

---

## Proposed Fix: PID File

### Write side (server start)

When `ai prefect-run` starts the server via `Popen`, write the process PID to a known file:

```
~/.prefect/devflow-server.pid
```

```python
pid_file = Path.home() / '.prefect' / 'devflow-server.pid'
sandbox_proc = subprocess.Popen(sandbox_cmd, ...)
pid_file.parent.mkdir(parents=True, exist_ok=True)
pid_file.write_text(str(sandbox_proc.pid))
```

### Read side (cleanup)

At the end of `ai prefect-run`, if `sandbox_proc is not None`, delete the PID file after terminating:

```python
if sandbox_proc is not None:
    sandbox_proc.terminate()
    try:
        sandbox_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        sandbox_proc.kill()
    pid_file.unlink(missing_ok=True)
    print('Prefect server stopped')
```

### `ai prefect-stop` command

A new `ai prefect-stop` mode reads the PID file and kills only that process:

```python
pid_file = Path.home() / '.prefect' / 'devflow-server.pid'
if not pid_file.exists():
    print('No devflow-managed Prefect server found (no PID file).')
    sys.exit(0)

pid = int(pid_file.read_text().strip())
try:
    import psutil
    proc = psutil.Process(pid)
    proc.terminate()
    proc.wait(timeout=5)
    pid_file.unlink(missing_ok=True)
    print(f'Prefect server (PID {pid}) stopped.')
except psutil.NoSuchProcess:
    pid_file.unlink(missing_ok=True)
    print(f'Process {pid} no longer running — PID file cleaned up.')
except psutil.TimeoutExpired:
    proc.kill()
    pid_file.unlink(missing_ok=True)
    print(f'Prefect server (PID {pid}) force-killed.')
```

> **Note:** `psutil` is required. Add to `requirements.txt` in any project using this. Alternatively, use `taskkill /F /PID <pid>` on Windows and `kill <pid>` on Unix to avoid the dependency.

### Cross-platform kill without psutil

```python
import os, signal, sys

pid = int(pid_file.read_text().strip())
try:
    if sys.platform == 'win32':
        subprocess.run(f'taskkill /F /PID {pid} /T', shell=True, check=True)
    else:
        os.kill(pid, signal.SIGTERM)
    pid_file.unlink(missing_ok=True)
    print(f'Prefect server (PID {pid}) stopped.')
except Exception as e:
    print(f'Could not stop PID {pid}: {e}')
    print(f'PID file left at: {pid_file}')
```

`/T` on Windows kills the process tree (server + any child workers).

---

## `already_up=True` Path — What To Do

When the server was already running before we started:
- We did **not** start it, so we must not stop it
- The current warning is the right behaviour for now
- Once PID file is in place: check if the PID file exists and matches the running server PID. If it does, we own it and can stop it. If it doesn't, we don't own it — leave it running, print the warning.

```python
if already_up:
    pid_file = Path.home() / '.prefect' / 'devflow-server.pid'
    if pid_file.exists():
        # We started it in a previous session — we own it
        sandbox_proc = _adopt_from_pid_file(pid_file)
    else:
        # Someone else started it — leave it alone
        print('⚠️  Server was not started by this session — it will not be stopped automatically.')
```

---

## PID File Location

`~/.prefect/devflow-server.pid` is chosen because:
- `~/.prefect/` already exists (Prefect creates it for its own config/DB)
- Scoped to the user, not the repo — one server per machine, not per project
- Outside version control

---

## Implementation Checklist

- [ ] Write PID file on `Popen` in `ai prefect-run` (both the main and the local-mode paths)
- [ ] Delete PID file in cleanup block
- [ ] Check PID file in `already_up=True` path — adopt if we own it
- [ ] Add `ai prefect-stop` mode to `ai` script
- [ ] Test: start server with `ai prefect-run`, confirm PID file written, confirm deleted on exit
- [ ] Test: `ai prefect-stop` when server running → stops it; when not running → clean message
- [ ] Test: `ai prefect-stop` when PID file stale (process already dead) → cleans up PID file
