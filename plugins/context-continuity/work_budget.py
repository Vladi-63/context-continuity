"""Read only context counters for explicitly registered local Work chats."""
import argparse
import json
import os
from pathlib import Path
import re
import sys


WARN = 30
STOP = 35
MAX_TAIL = 2 * 1024 * 1024
THREAD_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def limits(info):
    if not isinstance(info, dict) or not isinstance(info.get("last_token_usage"), dict):
        return None
    tokens = info["last_token_usage"].get("total_tokens")
    window = info.get("model_context_window")
    if type(tokens) is not int or type(window) is not int or tokens <= 0 or window <= 0:
        return None
    return tokens, window


def measure(rows):
    """Associate counters with a completed turn; discard pre-compaction samples."""
    active = None
    latest = None
    receipt = None
    sample = None
    compact = None
    closed = set()
    for line in rows:
        if not line.endswith(b"\n"):
            return {"state": "UNKNOWN", "reason": "partial record"}
        if not any(tag in line[:256] for tag in (
            b'"task_started"', b'"task_complete"', b'"turn_aborted"', b'"token_count"', b'"compacted"',
            b'"turn_context"',
        )):
            continue
        try:
            event = json.loads(line)
            payload = event["payload"]
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
        except (KeyError, ValueError, TypeError, UnicodeError):
            return {"state": "UNKNOWN", "reason": "invalid event"}
        event_type = event.get("type")
        kind = payload.get("type") if event_type == "event_msg" else event_type
        if kind == "task_started":
            active = payload.get("turn_id")
            if not isinstance(active, str) or not active:
                return {"state": "UNKNOWN", "reason": "invalid start turn id"}
            closed.discard(active)
            latest = sample = compact = None
        elif event_type == "turn_context":
            turn = payload.get("turn_id")
            if (not isinstance(turn, str) or not turn or turn in closed
                    or (active is not None and turn != active)):
                return {"state": "UNKNOWN", "reason": "conflicting turn context"}
            if active is None:
                # The journal can repeat this record after compaction. It can
                # anchor the tail, but cannot bind counters from before it.
                active = turn
                latest = sample = compact = None
        elif kind == "turn_aborted":
            if active:
                closed.add(active)
            turn = payload.get("turn_id")
            if isinstance(turn, str) and turn:
                closed.add(turn)
            active = latest = sample = compact = None
        elif kind == "token_count" and active:
            if payload.get("info") is not None:
                sample = limits(payload["info"])
        elif kind == "compacted":
            compact = (event.get("timestamp"), sample) if active else None
            latest = sample = None
        elif kind == "task_complete" and active == payload.get("turn_id") and active:
            closed.add(active)
            if sample:
                latest = {"turn": active, "time": event.get("timestamp"),
                          "tokens": sample[0], "window": sample[1]}
                if compact and compact[1] and compact[1][1] == sample[1]:
                    receipt = {"time": compact[0], "turn": active, "before": compact[1][0],
                               "after": sample[0], "window": sample[1]}
            else:
                latest = None
            active = sample = compact = None
        elif kind == "task_complete" and active is None:
            turn = payload.get("turn_id")
            if isinstance(turn, str) and turn:
                closed.add(turn)
            latest = None
    if active:
        result = {"state": "BUSY", "reason": "turn in progress"}
    elif not latest:
        result = {"state": "UNKNOWN", "reason": "no completed turn with a context counter in the bounded tail"}
    else:
        used, window = latest["tokens"], latest["window"]
        state = "HOLD" if 100 * used >= STOP * window else "COMPACT" if 100 * used >= WARN * window else "READY"
        result = {"state": state, "percent": round(100 * used / window, 2), **latest}
    if receipt:
        result["observed_compaction"] = receipt
    return result


def snapshot(root, thread_id):
    if not isinstance(thread_id, str) or not THREAD_ID.fullmatch(thread_id):
        return {"state": "UNKNOWN", "reason": "invalid thread id"}
    paths = list(root.glob(f"*/*/*/rollout-*-{thread_id}.jsonl"))
    if len(paths) != 1 or not paths[0].is_file() or paths[0].is_symlink():
        return {"state": "UNKNOWN", "reason": "no unique local journal"}
    path = paths[0]
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            offset = max(0, before.st_size - MAX_TAIL)
            stream.seek(offset)
            data = stream.read(before.st_size - offset)
            after = path.stat()
        if ((before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev)
                != (after.st_size, after.st_mtime_ns, after.st_ino, after.st_dev)):
            return {"state": "UNKNOWN", "reason": "journal changed during read"}
    except OSError:
        return {"state": "UNKNOWN", "reason": "journal unavailable"}
    if offset:
        _, _, data = data.partition(b"\n")
    return measure(data.splitlines(keepends=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", required=True, type=Path)
    parser.add_argument("--target")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        with args.roster.open("rb") as stream:
            roster = json.loads(stream.read(8193))
        if (not isinstance(roster, dict) or not 1 <= len(roster) <= 16
                or not all(isinstance(k, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,23}", k)
                           and isinstance(v, str) and THREAD_ID.fullmatch(v) for k, v in roster.items())
                or len(set(roster.values())) != len(roster)):
            raise ValueError("invalid roster")
        if args.target and args.target not in roster:
            raise ValueError("target is not in the roster")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    root = Path.home() / ".codex" / "sessions"
    results = {name: snapshot(root, thread) for name, thread in roster.items()
               if not args.target or args.target == name}
    if args.json:
        print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
    else:
        for name, result in results.items():
            measured = f" {result['percent']:.2f}%" if "percent" in result else ""
            print(f"{name}: {result['state']}{measured}")
    return 3 if args.target and results[args.target]["state"] != "READY" else 0


if __name__ == "__main__":
    sys.exit(main())
