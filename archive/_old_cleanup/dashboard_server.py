"""
Dynamic Dashboard Server for Market Insights
Real-time monitoring - READS FROM CHECKPOINT FILES
Location: market_insights/dashboard/
"""

import json
import os
import glob
import re
import time
import sqlite3
from collections import deque
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Get the directory where this script is located
DASHBOARD_DIR = Path(__file__).parent.resolve()

# Project root is parent of dashboard directory
PROJECT_ROOT = DASHBOARD_DIR.parent

# Pointer file - written by profile_runner to indicate active output directory
# This is the PRIMARY source for finding the active output (avoids scanning)
DASHBOARD_POINTER_FILE = PROJECT_ROOT / ".active_output_dir"

# Fallback: Scan these directories if pointer file doesn't exist
# NOTE: The active run output directory can be nested (e.g., ProfileRunner per-month folders).
# IMPORTANT: All paths MUST be inside project directory (see CLAUDE.md)
_env_output_dir = os.environ.get("MARKET_INSIGHTS_OUTPUT_DIR")
BASE_OUTPUT_DIRS: List[Path] = [
    PROJECT_ROOT / "outputs",  # Primary - inside project
]
if _env_output_dir:
    BASE_OUTPUT_DIRS.insert(0, Path(_env_output_dir).resolve())
# Remove duplicates and non-existent directories
BASE_OUTPUT_DIRS = list(dict.fromkeys(p.resolve() for p in BASE_OUTPUT_DIRS if p.exists()))

# These are dynamically updated by refresh_active_paths()
ACTIVE_OUTPUT_DIR = BASE_OUTPUT_DIRS[0] if BASE_OUTPUT_DIRS else PROJECT_ROOT / "outputs"
ACTIVE_CHECKPOINT_DIR = ACTIVE_OUTPUT_DIR / "checkpoints"
ACTIVE_LOGS_DIR = ACTIVE_OUTPUT_DIR / "logs"

# Local dashboard files
STATUS_FILE = DASHBOARD_DIR / "dashboard_status.json"
HTML_FILE = DASHBOARD_DIR / "live_dashboard.html"
LOGO_DIR = DASHBOARD_DIR / "Air_Cairo-brandlogos.net-O7cT7S"

# State files (from OUTPUTS)
RUN_STATE_FILE = ACTIVE_CHECKPOINT_DIR / "run_state.json"
TASKS_STATE_FILE = ACTIVE_CHECKPOINT_DIR / "tasks_state.json"
OAL_STATE_FILE = ACTIVE_CHECKPOINT_DIR / "oal_state.json"
FLIGHT_BOOKING_FILE = ACTIVE_CHECKPOINT_DIR / "flight_booking_data.json"
SQLITE_STATE_DB = ACTIVE_CHECKPOINT_DIR / "chunk_state.db"

# Cache active path resolution to avoid excessive filesystem scans.
_ACTIVE_SCAN_INTERVAL_SECONDS = 2.0
_last_active_scan_ts = 0.0
_active_run_state_file: Optional[Path] = None

# ChunkStateManager defaults (used to back-calculate "started_at" for running tasks)
_SQLITE_LEASE_DURATION_SECONDS = 900


def _parse_iso_timestamp(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


def _activity_timestamp_for_checkpoint(checkpoint_dir: Path) -> float:
    # NOTE: run_state.json is excluded because it doesn't represent actual work activity
    # and can be modified without any real extraction happening
    candidates = [
        checkpoint_dir / "chunk_state.db",
        checkpoint_dir / "oal_state.json",
        checkpoint_dir / "flight_booking_data.json",
        checkpoint_dir / "worker_heartbeats.json",
        checkpoint_dir / "tasks_state.json",
    ]
    mtimes: List[float] = []
    for p in candidates:
        try:
            if p.exists():
                mtimes.append(p.stat().st_mtime)
        except Exception:
            continue
    return max(mtimes) if mtimes else 0.0


def _select_active_run_state_file(run_state_files: List[Path]) -> Optional[Path]:
    best: Optional[Tuple[int, float, float, float, Path]] = None

    for run_state_file in run_state_files:
        try:
            checkpoint_dir = run_state_file.parent
            run_state = {}
            try:
                with open(run_state_file, "r", encoding="utf-8") as f:
                    run_state = json.load(f) or {}
            except Exception:
                run_state = {}

            shutdown_type = (run_state.get("shutdown_type") or "").strip().upper()
            is_active = 1 if shutdown_type != "COMPLETED" else 0
            started_ts = _parse_iso_timestamp(run_state.get("started_at"))
            activity_ts = _activity_timestamp_for_checkpoint(checkpoint_dir)
            run_state_mtime = run_state_file.stat().st_mtime

            key = (is_active, activity_ts, started_ts, run_state_mtime, run_state_file)
            if best is None or key > best:
                best = key
        except Exception:
            continue

    return best[-1] if best else None


def _read_pointer_file() -> Optional[Path]:
    """
    Read the pointer file written by profile_runner.

    Returns:
        Path to active output directory, or None if pointer file doesn't exist or is invalid
    """
    try:
        if DASHBOARD_POINTER_FILE.exists():
            with open(DASHBOARD_POINTER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            active_dir = Path(data.get("active_output_dir", ""))
            if active_dir.exists() and (active_dir / "checkpoints").exists():
                return active_dir
    except Exception:
        pass
    return None


def refresh_active_paths(force: bool = False) -> None:
    """
    Resolve the active run output/checkpoint directories.

    Priority:
    1. Read from pointer file (written by profile_runner) - FASTEST
    2. Scan all BASE_OUTPUT_DIRS for active run_state.json - FALLBACK

    The pointer file approach is preferred as it's instant and accurate.
    """
    global ACTIVE_OUTPUT_DIR, ACTIVE_CHECKPOINT_DIR, ACTIVE_LOGS_DIR
    global RUN_STATE_FILE, TASKS_STATE_FILE, OAL_STATE_FILE, FLIGHT_BOOKING_FILE, SQLITE_STATE_DB
    global _last_active_scan_ts, _active_run_state_file

    now = time.time()
    if not force and (now - _last_active_scan_ts) < _ACTIVE_SCAN_INTERVAL_SECONDS:
        return

    _last_active_scan_ts = now

    # PRIORITY 1: Try pointer file (written by profile_runner)
    pointer_dir = _read_pointer_file()
    if pointer_dir:
        output_dir = pointer_dir
        checkpoint_dir = pointer_dir / "checkpoints"
        _active_run_state_file = checkpoint_dir / "run_state.json"
    else:
        # FALLBACK: Scan all base output directories
        all_run_state_files: List[Path] = []
        for base_dir in BASE_OUTPUT_DIRS:
            pattern = str(base_dir / "**" / "checkpoints" / "run_state.json")
            all_run_state_files.extend(Path(p) for p in glob.glob(pattern, recursive=True))

        selected = _select_active_run_state_file(all_run_state_files)

        if selected is None:
            # Fallback to first available output dir
            checkpoint_dir = (BASE_OUTPUT_DIRS[0] if BASE_OUTPUT_DIRS else PROJECT_ROOT / "outputs") / "checkpoints"
        else:
            checkpoint_dir = selected.parent
            _active_run_state_file = selected

        output_dir = checkpoint_dir.parent

    ACTIVE_OUTPUT_DIR = output_dir
    ACTIVE_CHECKPOINT_DIR = checkpoint_dir
    ACTIVE_LOGS_DIR = output_dir / "logs"

    RUN_STATE_FILE = checkpoint_dir / "run_state.json"
    TASKS_STATE_FILE = checkpoint_dir / "tasks_state.json"
    OAL_STATE_FILE = checkpoint_dir / "oal_state.json"
    FLIGHT_BOOKING_FILE = checkpoint_dir / "flight_booking_data.json"
    SQLITE_STATE_DB = checkpoint_dir / "chunk_state.db"


def _sqlite_checkpoint_available() -> bool:
    try:
        return SQLITE_STATE_DB.exists()
    except Exception:
        return False


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    # Read-only connections are sufficient for the dashboard.
    # Use a short timeout to avoid blocking the monitor thread if the DB is busy.
    conn = sqlite3.connect(str(db_path), timeout=1)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_get_task_stats(db_path: Path) -> Dict[str, int]:
    stats = {
        "total": 0,
        "pending": 0,
        "running": 0,
        "done": 0,
        "failed": 0,
        "failed_exhausted": 0,
    }

    conn = _sqlite_connect(db_path)
    try:
        cur = conn.execute("SELECT state, COUNT(*) as c FROM chunk_tasks GROUP BY state")
        for row in cur.fetchall():
            state = (row["state"] or "").lower()
            count = int(row["c"] or 0)
            if state in stats:
                stats[state] = count
            stats["total"] += count

        # Normalize failure count to include exhausted tasks
        stats["failed"] = stats.get("failed", 0) + stats.get("failed_exhausted", 0)
        return stats
    finally:
        conn.close()


def _map_sqlite_state_to_task_status(state: str) -> str:
    s = (state or "").lower()
    if s == "running":
        return "RUNNING"
    if s == "done":
        return "DONE"
    if s in ("failed", "failed_exhausted"):
        return "FAILED"
    return "PENDING"


def _calculate_progress_from_sqlite(db_path: Path) -> Dict[str, Any]:
    stats = _sqlite_get_task_stats(db_path)

    total = stats.get("total", 0)
    done = stats.get("done", 0)
    running = stats.get("running", 0)
    pending = stats.get("pending", 0)
    failed = stats.get("failed", 0)
    percent = (done / total * 100) if total > 0 else 0.0

    # Only include RUNNING tasks in tasks_detail (used to render the running tasks panel).
    tasks_detail: List[Dict[str, Any]] = []
    conn = _sqlite_connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT task_id, route, chunk_idx, state, worker_id, dates, lease_expires_at, updated_at
            FROM chunk_tasks
            WHERE state = 'running'
            ORDER BY updated_at DESC
            """
        )

        for row in cur.fetchall():
            dates = row["dates"] or "[]"
            try:
                dates_list = json.loads(dates) if isinstance(dates, str) else (dates or [])
            except Exception:
                dates_list = []

            lease_expires_at = row["lease_expires_at"]
            started_ts = None
            if lease_expires_at:
                started_ts = float(lease_expires_at) - _SQLITE_LEASE_DURATION_SECONDS
            elif row["updated_at"]:
                started_ts = float(row["updated_at"])

            started_at = (
                datetime.fromtimestamp(started_ts).isoformat() if started_ts else datetime.now().isoformat()
            )

            tasks_detail.append(
                {
                    "id": row["task_id"],
                    "route": row["route"],
                    "chunk": row["chunk_idx"],
                    "status": _map_sqlite_state_to_task_status(row["state"]),
                    "worker": row["worker_id"],
                    "dates_count": len(dates_list),
                    "started_at": started_at,
                    "completed_at": None,
                }
            )
    finally:
        conn.close()

    return {
        "total": total,
        "done": done,
        "running": running,
        "pending": pending,
        "failed": failed,
        "percent": round(percent, 1),
        "tasks_detail": tasks_detail,
    }


def load_run_state():
    """Load current run configuration from checkpoint"""
    refresh_active_paths()
    try:
        if RUN_STATE_FILE.exists():
            with open(RUN_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load run_state.json: {e}")
    return None


def load_tasks_state():
    """Load current tasks state from checkpoint"""
    refresh_active_paths()
    try:
        if TASKS_STATE_FILE.exists():
            with open(TASKS_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load tasks_state.json: {e}")
    return {}


def load_oal_state():
    """Load OAL progress state from checkpoint (REAL tracking)"""
    refresh_active_paths()
    try:
        if OAL_STATE_FILE.exists():
            with open(OAL_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load oal_state.json: {e}")
    return None


def load_flight_booking_data():
    """Load flight booking data for dashboard real-time display"""
    refresh_active_paths()
    candidates = [
        FLIGHT_BOOKING_FILE,
        PROJECT_ROOT / "managers" / "outputs" / "checkpoints" / "flight_booking_data.json",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                with open(candidate, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data:
                    return data
        except Exception as e:
            print(f"[WARN] Could not load flight_booking_data.json from {candidate}: {e}")
    return None


def load_validation_warnings():
    """Load validation warnings from checkpoint for dashboard display"""
    refresh_active_paths()
    try:
        warnings_file = ACTIVE_CHECKPOINT_DIR / "validation_warnings.json"
        if warnings_file.exists():
            with open(warnings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
    except Exception as e:
        print(f"[WARN] Could not load validation_warnings.json: {e}")
    return None


# ===== LIVE LOG STREAM =====
def get_live_logs(max_lines=25):
    """Read last N lines from the most recent log file"""
    refresh_active_paths()
    try:
        # Find the most recent log file
        log_pattern = str(ACTIVE_LOGS_DIR / "**" / "*.log")
        log_files = glob.glob(log_pattern, recursive=True)

        if not log_files:
            return {"lines": [], "file": None, "error": "No log files found"}

        # Get most recently modified log file
        latest_log = max(log_files, key=os.path.getmtime)

        # Read last N lines (avoid loading the full file into memory)
        with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
            total_lines = 0
            tail = deque(maxlen=max_lines)
            for line in f:
                total_lines += 1
                tail.append(line.rstrip("\n"))

            formatted = [line.strip() for line in tail if line and line.strip()]

            return {
                "lines": formatted,
                "file": os.path.basename(latest_log),
                "total_lines": total_lines
            }
    except Exception as e:
        return {"lines": [], "file": None, "error": str(e)}


# ===== SPEED & ERROR METRICS =====
# Track processing speed over time
_speed_history = []  # List of (timestamp, tasks_done) tuples
_last_error_count = 0
_error_rate_history = []


def calculate_speed_metrics(tasks):
    """Calculate processing speed and error metrics"""
    global _speed_history, _last_error_count, _error_rate_history

    current_time = time.time()
    tasks_done = tasks.get("done", 0)
    tasks_failed = tasks.get("failed", 0)

    # Add current data point
    _speed_history.append((current_time, tasks_done))

    # Keep only last 60 seconds of data (30 data points at 2s interval)
    cutoff = current_time - 60
    _speed_history = [(t, d) for t, d in _speed_history if t > cutoff]

    # Calculate speed (tasks per minute)
    speed_per_minute = 0.0
    if len(_speed_history) >= 2:
        oldest = _speed_history[0]
        newest = _speed_history[-1]
        time_diff = newest[0] - oldest[0]
        tasks_diff = newest[1] - oldest[1]
        if time_diff > 0:
            speed_per_minute = (tasks_diff / time_diff) * 60

    # Track error rate
    if tasks_failed != _last_error_count:
        _error_rate_history.append((current_time, tasks_failed - _last_error_count))
        _last_error_count = tasks_failed

    # Keep only last 5 minutes of error history
    error_cutoff = current_time - 300
    _error_rate_history = [(t, e) for t, e in _error_rate_history if t > error_cutoff]

    # Calculate errors in last 5 minutes
    recent_errors = sum(e for t, e in _error_rate_history)

    return {
        "speed_per_minute": round(speed_per_minute, 2),
        "speed_per_hour": round(speed_per_minute * 60, 1),
        "recent_errors": recent_errors,
        "error_rate": round(recent_errors / 5, 2) if recent_errors > 0 else 0,  # per minute
        "data_points": len(_speed_history)
    }


# ===== ETA CALCULATION =====
def calculate_eta(progress, tasks, speed_metrics, oal_state=None, oal_workers=0):
    """Calculate estimated time remaining for each phase"""
    eta = {
        "lf_eta": None,
        "oal_eta": None,
        "total_eta": None,
        "lf_eta_formatted": "N/A",
        "oal_eta_formatted": "N/A",
        "total_eta_formatted": "N/A"
    }

    speed = speed_metrics.get("speed_per_minute", 0)
    if speed <= 0:
        return eta

    # LF ETA
    lf_remaining_tasks = tasks.get("total", 0) - tasks.get("done", 0)
    if lf_remaining_tasks > 0:
        lf_minutes = lf_remaining_tasks / speed
        eta["lf_eta"] = lf_minutes
        eta["lf_eta_formatted"] = format_duration(lf_minutes)
    else:
        eta["lf_eta_formatted"] = "Done"

    # OAL ETA (based on OAL state if available)
    if oal_workers > 0 and oal_state:
        total_ops = oal_state.get("total_operations", 0)
        completed_ops = oal_state.get("completed_operations", 0)
        remaining_ops = total_ops - completed_ops

        if remaining_ops > 0:
            # OAL typically processes slower - estimate based on route count
            routes_total = oal_state.get("routes_total_per_pass", 0)
            if routes_total > 0:
                # OAL processes ~1-2 routes per minute per worker
                oal_speed = oal_workers * 1.5  # estimated routes per minute
                oal_minutes = remaining_ops / oal_speed
                eta["oal_eta"] = oal_minutes
                eta["oal_eta_formatted"] = format_duration(oal_minutes)
        else:
            eta["oal_eta_formatted"] = "Done"
    elif oal_workers == 0:
        eta["oal_eta_formatted"] = "Disabled"

    # Total ETA
    total_minutes = 0
    if eta["lf_eta"]:
        total_minutes += eta["lf_eta"]
    if eta["oal_eta"]:
        total_minutes = max(total_minutes, eta["oal_eta"])  # Run in parallel

    if total_minutes > 0:
        eta["total_eta"] = total_minutes
        eta["total_eta_formatted"] = format_duration(total_minutes)
    elif eta["lf_eta_formatted"] == "Done" and (eta["oal_eta_formatted"] == "Done" or oal_workers == 0):
        eta["total_eta_formatted"] = "Done"

    return eta


def format_duration(minutes):
    """Format duration in minutes to human readable string"""
    if minutes < 1:
        return "< 1 min"
    elif minutes < 60:
        return f"{int(minutes)} min"
    else:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        if mins > 0:
            return f"{hours}h {mins}m"
        return f"{hours}h"


def get_config_from_checkpoint():
    """Get actual configuration from checkpoint files"""
    run_state = load_run_state()

    if not run_state:
        # Fallback to defaults
        return {
            "routes": [],
            "dates": [],
            "ports": [9222, 9223, 9224],
            "chunks_count": 0,
            "oal_workers": 0,
            "oal_passes": 0,
            "run_id": "unknown",
            "mode": "unknown",
            "started_at": None
        }

    return {
        "routes": run_state.get("routes", []),
        "dates": run_state.get("dates", []),
        "ports": run_state.get("ports", []),
        "chunks_count": run_state.get("chunks_count", 0),
        "oal_workers": run_state.get("oal_workers", 0),
        "oal_passes": run_state.get("oal_passes", 2),  # Default to 2 passes
        "run_id": run_state.get("run_id", "unknown"),
        "mode": run_state.get("mode", "unknown"),
        "started_at": run_state.get("started_at")
    }


def calculate_progress_from_tasks():
    """Calculate actual progress from tasks_state.json"""
    refresh_active_paths()

    if _sqlite_checkpoint_available():
        try:
            return _calculate_progress_from_sqlite(SQLITE_STATE_DB)
        except Exception as e:
            print(f"[WARN] SQLite progress read failed, falling back to JSON: {e}")

    tasks = load_tasks_state()

    if not tasks:
        return {
            "total": 0,
            "done": 0,
            "running": 0,
            "pending": 0,
            "failed": 0,
            "percent": 0,
            "tasks_detail": []
        }

    total = len(tasks)
    done = 0
    running = 0
    pending = 0
    failed = 0
    tasks_detail = []

    for task_id, task in tasks.items():
        status = task.get("status", "PENDING")

        if status == "DONE":
            done += 1
        elif status == "RUNNING":
            running += 1
        elif status == "FAILED":
            failed += 1
        else:
            pending += 1

        tasks_detail.append({
            "id": task_id,
            "route": task.get("route"),
            "chunk": task.get("chunk_idx"),
            "status": status,
            "worker": task.get("assigned_worker"),
            "dates_count": len(task.get("dates", [])),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at")
        })

    percent = (done / total * 100) if total > 0 else 0

    return {
        "total": total,
        "done": done,
        "running": running,
        "pending": pending,
        "failed": failed,
        "percent": round(percent, 1),
        "tasks_detail": sorted(tasks_detail, key=lambda x: x.get("id", ""))
    }


def get_worker_status_from_tasks():
    """Get worker status from tasks_state"""
    config = get_config_from_checkpoint()

    refresh_active_paths()

    if _sqlite_checkpoint_available():
        workers: Dict[str, Dict[str, Any]] = {}
        for port in config.get("ports", []):
            workers[str(port)] = {"status": "idle", "active_route": None, "active_task": None}

        conn = _sqlite_connect(SQLITE_STATE_DB)
        try:
            cur = conn.execute(
                """
                SELECT w.worker_id, w.status, w.task_id, t.route
                FROM worker_heartbeats w
                LEFT JOIN chunk_tasks t ON w.task_id = t.task_id
                """
            )
            for row in cur.fetchall():
                worker_id = row["worker_id"] or ""
                m = re.search(r"Worker_(\d+)", worker_id)
                if not m:
                    continue

                port = m.group(1)
                if port not in workers:
                    continue

                status = (row["status"] or "").upper()
                if status == "RUNNING" and row["task_id"]:
                    workers[port] = {
                        "status": "working",
                        "active_route": row["route"],
                        "active_task": row["task_id"],
                    }
                else:
                    workers[port] = {"status": "idle", "active_route": None, "active_task": None}
        finally:
            conn.close()

        return workers

    tasks = load_tasks_state()

    workers = {}
    for port in config.get("ports", []):
        workers[str(port)] = {
            "status": "idle",
            "active_route": None,
            "active_task": None
        }

    for task_id, task in tasks.items():
        if task.get("status") == "RUNNING":
            worker = task.get("assigned_worker", "")
            # Extract port from "Worker_9222"
            match = re.search(r'Worker_(\d+)', worker)
            if match:
                port = match.group(1)
                if port in workers:
                    workers[port] = {
                        "status": "working",
                        "active_route": task.get("route"),
                        "active_task": task_id
                    }

    return workers


def get_pending_routes_info():
    """Get detailed pending routes information"""
    refresh_active_paths()

    if _sqlite_checkpoint_available():
        pending_by_route: Dict[str, Dict[str, Any]] = {}

        conn = _sqlite_connect(SQLITE_STATE_DB)
        try:
            cur = conn.execute("SELECT route, state, dates FROM chunk_tasks")
            for row in cur.fetchall():
                route = row["route"]
                state = (row["state"] or "").lower()
                dates_raw = row["dates"] or "[]"

                if route not in pending_by_route:
                    pending_by_route[route] = {
                        "total_tasks": 0,
                        "done_tasks": 0,
                        "pending_dates": [],
                        "done_dates": [],
                    }

                pending_by_route[route]["total_tasks"] += 1

                if state == "done":
                    pending_by_route[route]["done_tasks"] += 1
                    continue

                try:
                    dates_list = json.loads(dates_raw) if isinstance(dates_raw, str) else (dates_raw or [])
                except Exception:
                    dates_list = []

                pending_by_route[route]["pending_dates"].extend(dates_list)
        finally:
            conn.close()

        return pending_by_route

    tasks = load_tasks_state()

    pending_by_route = {}

    for task_id, task in tasks.items():
        route = task.get("route")
        status = task.get("status")
        dates = task.get("dates", [])

        if route not in pending_by_route:
            pending_by_route[route] = {
                "total_tasks": 0,
                "done_tasks": 0,
                "pending_dates": [],
                "done_dates": []
            }

        pending_by_route[route]["total_tasks"] += 1

        if status == "DONE":
            pending_by_route[route]["done_tasks"] += 1
            pending_by_route[route]["done_dates"].extend(dates)
        else:
            pending_by_route[route]["pending_dates"].extend(dates)

    return pending_by_route


def count_excel_files(run_started_at=None):
    """Count Excel files created AFTER run started"""
    refresh_active_paths()
    pattern = str(ACTIVE_OUTPUT_DIR / "*.xlsx")
    files = glob.glob(pattern)

    # Parse run start time
    run_start_timestamp = 0
    if run_started_at:
        try:
            from datetime import datetime
            # Parse ISO format: 2025-12-18T06:21:01.123456
            dt = datetime.fromisoformat(run_started_at.replace('Z', '+00:00'))
            run_start_timestamp = dt.timestamp()
        except:
            pass

    # Get files created AFTER run started (not just in last 24 hours)
    current_run_files = []
    for f in files:
        try:
            mtime = os.path.getmtime(f)
            # Only count files modified AFTER run started
            if run_start_timestamp > 0 and mtime >= run_start_timestamp:
                current_run_files.append(os.path.basename(f))
        except:
            continue

    return current_run_files


def update_status():
    """Update status JSON with real data from checkpoints"""
    refresh_active_paths()
    config = get_config_from_checkpoint()
    progress = calculate_progress_from_tasks()
    workers = get_worker_status_from_tasks()
    pending_routes = get_pending_routes_info()
    # Pass run start time to only count Excel files from THIS run
    excel_files = count_excel_files(config.get("started_at"))

    # Calculate phase progress
    lf_percent = progress["percent"]

    # OAL progress - NOW USES REAL TRACKING from oal_state.json
    # Formula: routes × passes = total OAL operations
    # Progress % = (completed_operations / total_operations) × 100%
    oal_workers = config.get("oal_workers", 0)
    run_state_check = load_run_state()
    run_completed = run_state_check and run_state_check.get("shutdown_type") == "COMPLETED"

    # Load REAL OAL progress from checkpoint
    oal_state = load_oal_state()
    oal_is_estimated = False  # We now have REAL tracking!

    if oal_workers > 0:
        if oal_state:
            # REAL OAL progress from checkpoint file
            oal_percent = oal_state.get("percent", 0)
            oal_status = oal_state.get("status", "unknown")
            oal_current_pass = oal_state.get("current_pass", 0)
            oal_total_passes = oal_state.get("total_passes", 2)
            oal_routes_completed = oal_state.get("routes_completed_in_pass", 0)
            oal_routes_total = oal_state.get("routes_total_per_pass", 0)

            # If status is completed, ensure 100%
            if oal_status == "completed":
                oal_percent = 100
        else:
            # Fallback: oal_state.json not found
            # Use run_state config for expected values, show 0% until OAL starts
            oal_is_estimated = True
            routes_count = len(config.get("routes", []))
            oal_passes_count = config.get("oal_passes", 2)

            if run_completed:
                oal_percent = 100
                oal_status = "completed"
            elif progress["done"] == progress["total"] and progress["total"] > 0:
                # LF done but no OAL state - OAL might not have started yet
                oal_percent = 0
                oal_status = "waiting"
            else:
                # OAL hasn't started or not writing state - show 0%
                oal_percent = 0
                oal_status = "pending"

            oal_current_pass = 0
            oal_total_passes = oal_passes_count
            oal_routes_completed = 0
            oal_routes_total = routes_count
    else:
        oal_percent = 0
        oal_status = "disabled"
        oal_current_pass = 0
        oal_total_passes = 0
        oal_routes_completed = 0
        oal_routes_total = 0

    # Excel progress
    # BY_STATION mode creates 2-4 files, not one per route
    # Check run_state for actual completion status
    run_state = load_run_state()
    is_completed = run_state and run_state.get("shutdown_type") == "COMPLETED"

    if is_completed and len(excel_files) > 0:
        # Run completed and has Excel files = 100%
        excel_percent = 100.0
    else:
        # During run: BY_STATION creates ~4 files, not 44
        expected_excel = 4  # Realistic expectation for BY_STATION mode
        excel_percent = min(100, (len(excel_files) / expected_excel) * 100)

    # Overall progress
    # If LF and OAL are both complete, Overall should be 100%
    if lf_percent >= 100 and (oal_workers == 0 or oal_percent >= 100):
        overall = 100.0
    elif oal_workers > 0:
        overall = (lf_percent * 0.5) + (oal_percent * 0.35) + (excel_percent * 0.15)
    else:
        overall = (lf_percent * 0.85) + (excel_percent * 0.15)

    # Determine status
    if progress["running"] > 0:
        run_status = "RUNNING"
    elif progress["done"] == progress["total"] and progress["total"] > 0:
        run_status = "COMPLETED"
    elif progress["total"] == 0:
        run_status = "NO_DATA"
    else:
        run_status = "IDLE"

    # NEW: Calculate speed metrics
    tasks_for_speed = {
        "done": progress["done"],
        "total": progress["total"],
        "failed": progress["failed"]
    }
    speed_metrics = calculate_speed_metrics(tasks_for_speed)

    # NEW: Calculate ETA
    eta = calculate_eta(
        progress={"lf": lf_percent, "oal": oal_percent},
        tasks=tasks_for_speed,
        speed_metrics=speed_metrics,
        oal_state=oal_state,
        oal_workers=oal_workers
    )

    # NEW: Get live logs
    live_logs = get_live_logs(max_lines=20)

    status = {
        "timestamp": datetime.now().isoformat(),
        "status": run_status,
        "running": progress["running"] > 0,
        "active_workers": progress["running"],
        "paths": {
            "base_output_dirs": [str(p) for p in BASE_OUTPUT_DIRS],
            "active_output_dir": str(ACTIVE_OUTPUT_DIR),
            "active_checkpoint_dir": str(ACTIVE_CHECKPOINT_DIR),
            "active_logs_dir": str(ACTIVE_LOGS_DIR),
            "backend": "sqlite" if _sqlite_checkpoint_available() else "json",
        },

        # Configuration (from checkpoint)
        "config": {
            "run_id": config.get("run_id"),
            "mode": config.get("mode"),
            "started_at": config.get("started_at"),
            "routes": config.get("routes", []),
            "routes_count": len(config.get("routes", [])),
            "dates_count": len(config.get("dates", [])),
            "chunks_count": config.get("chunks_count"),
            "ports": config.get("ports", []),
            "ports_count": len(config.get("ports", [])),
            "oal_workers": oal_workers,
            "date_range": f"{config.get('dates', ['?'])[-1]} to {config.get('dates', ['?'])[0]}" if config.get('dates') else "N/A"
        },

        # Progress (from tasks_state and oal_state)
        "progress": {
            "lf": round(lf_percent, 1),
            "oal": round(oal_percent, 1),
            "oal_is_estimated": oal_is_estimated,  # False = REAL tracking!
            "oal_status": oal_status,
            "oal_current_pass": oal_current_pass,
            "oal_total_passes": oal_total_passes,
            "oal_routes_completed": oal_routes_completed,
            "oal_routes_total": oal_routes_total,
            "excel": round(excel_percent, 1),
            "overall": round(overall, 1),
            "run_completed": run_completed  # From run_state shutdown_type
        },

        # Task stats
        "tasks": {
            "total": progress["total"],
            "done": progress["done"],
            "running": progress["running"],
            "pending": progress["pending"],
            "failed": progress["failed"]
        },

        # Worker status
        "workers": workers,

        # Pending routes detail
        "pending_routes": pending_routes,

        # Running tasks detail
        "running_tasks": [
            t for t in progress["tasks_detail"]
            if t["status"] == "RUNNING"
        ],

        # Excel files
        "excel_files": excel_files,
        "excel_count": len(excel_files),

        # NEW: Speed & Performance Metrics
        "speed_metrics": speed_metrics,

        # NEW: ETA Calculations
        "eta": eta,

        # NEW: OAL Pass Details (expanded)
        "oal_details": {
            "current_pass": oal_current_pass,
            "total_passes": oal_total_passes,
            "routes_completed_in_pass": oal_routes_completed,
            "routes_total_per_pass": oal_routes_total,
            "is_estimated": oal_is_estimated,
            "status": oal_status if oal_workers > 0 else "disabled"
        },

        # NEW: Live Logs
        "live_logs": live_logs,

        # NEW: Flight Booking Data (for AI Chart real-time display)
        "flight_booking_data": load_flight_booking_data() or {"flights": [], "updated_at": None},

        # NEW: Validation Warnings (for critical alerts display)
        "validation": load_validation_warnings() or {"passed": True, "warnings": []}
    }

    # Write status file
    try:
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to write status: {e}")

    return status


def monitor_loop():
    """Continuous monitoring loop"""
    print("[MONITOR] Starting monitoring loop...")
    while True:
        try:
            status = update_status()
            tasks = status.get('tasks', {})
            prog = status.get('progress', {})

            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"{status['status']} | "
                  f"Tasks: {tasks.get('done', 0)}/{tasks.get('total', 0)} | "
                  f"LF: {prog.get('lf', 0):.1f}% | "
                  f"Running: {tasks.get('running', 0)}")
        except Exception as e:
            print(f"[ERROR] Monitor error: {e}")
        time.sleep(2)


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        # Strip query string for path matching
        path = urlparse(self.path).path
        if path in ('/status', '/api/status'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.end_headers()
            try:
                with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            except:
                self.wfile.write(b'{"error": "Status not available"}')
        elif path == '/' or path == '/dashboard':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.end_headers()
            try:
                with open(HTML_FILE, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            except Exception as e:
                self.wfile.write(f'<h1>Error loading dashboard: {e}</h1>'.encode())
        elif path == '/logo.png':
            # Serve the Air Cairo logo
            self._serve_logo('air_cairo-logo_brandlogos.net_uq6d7.png', 'image/png')
        elif path == '/logo.svg':
            # Serve the SVG logo
            self._serve_logo('Air Cairo logo - Brandlogos.net.svg', 'image/svg+xml')
        elif path == '/logo_white.svg':
            # Serve the white SVG logo (for dark backgrounds)
            self._serve_logo('logo_white.svg', 'image/svg+xml')
        else:
            # Serve static files from dashboard directory
            super().do_GET()

    def _serve_logo(self, filename, content_type):
        """Serve logo file"""
        logo_path = LOGO_DIR / filename
        if logo_path.exists():
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Cache-Control', 'max-age=86400')
            self.end_headers()
            with open(logo_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, f'Logo not found: {filename}')

    def log_message(self, format, *args):
        pass


def run_server(port=8081):
    """Run the HTTP server"""
    os.chdir(DASHBOARD_DIR)
    server = HTTPServer(('localhost', port), DashboardHandler)
    print(f"[SERVER] Dashboard running at http://localhost:{port}")
    print(f"[SERVER] Dashboard dir: {DASHBOARD_DIR}")

    config = get_config_from_checkpoint()
    print(f"[SERVER] Monitoring: {len(config.get('routes', []))} routes, {config.get('chunks_count', 0)} chunks")

    server.serve_forever()


if __name__ == "__main__":
    print("=" * 60)
    print("  MARKET INSIGHTS - LIVE DASHBOARD SERVER")
    print("  (Dynamic - reads from checkpoint files)")
    print("=" * 60)

    # Show current config
    config = get_config_from_checkpoint()
    if config.get("routes"):
        print(f"\n  Current Run: {config.get('run_id')}")
        print(f"  Routes: {config.get('routes')}")
        print(f"  Dates: {len(config.get('dates', []))} days")
        print(f"  Chunks: {config.get('chunks_count')}")
    else:
        print("\n  No active run detected")
    print()

    # Start monitor in background thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    # Run server
    run_server(8081)
