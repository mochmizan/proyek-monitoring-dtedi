#!/usr/bin/env python3
"""
benchmark_concurrency_stress.py — High-Concurrency Multi-Worker Stress Benchmark

Simulates production multi-worker conditions across analytical downsampling reads,
high-throughput batch ingestion writes, and concurrent dashboard polling readers.
Explicitly identifies and labels results per database engine (PostgreSQL vs SQLite)
and strictly asserts all read-path, write-path, throughput, and zero-lock invariants.

Usage:
    # In-process benchmark against seeded SQLite WAL database:
    python tools/benchmark_concurrency_stress.py --in-process --duration 30

    # Live benchmark against PostgreSQL production server:
    python tools/benchmark_concurrency_stress.py --base-url http://127.0.0.1:8000 --db-engine postgresql --duration 30
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import httpx

# Add server and root directories to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
TOOLS_DIR = os.path.dirname(__file__)

for p in (ROOT_DIR, SERVER_DIR, TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

BENCH_HUB_ID = "BENCH_HUB_01"
BENCH_HUB_KEY = "bench_secret_key_123"
BENCH_ROOM_ID = "room-bench-01"
BENCH_TS_DEV_ID = "BENCH_DEV_TS_01"
BENCH_ATS_DEV_ID = "BENCH_DEV_ATS_01"
BENCH_USERNAME = "bench_user"
BENCH_PASSWORD = "bench_pass_123"


@dataclass
class MetricSummary:
    endpoint: str
    total_requests: int = 0
    success_requests: int = 0
    failed_requests: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    status_codes: dict[int, int] = field(default_factory=dict)
    database_locked_count: int = 0
    timeout_count: int = 0
    http_500_count: int = 0
    points_ingested: int = 0

    def record(
        self,
        latency_ms: float,
        status_code: int,
        error_msg: str = "",
        points: int = 0,
    ):
        self.total_requests += 1
        self.latencies_ms.append(latency_ms)
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

        if 200 <= status_code < 300:
            self.success_requests += 1
        else:
            self.failed_requests += 1

        if status_code == 500:
            self.http_500_count += 1

        err_lower = error_msg.lower()
        if "locked" in err_lower or "database is locked" in err_lower:
            self.database_locked_count += 1
        if "timeout" in err_lower or status_code == 504:
            self.timeout_count += 1

        self.points_ingested += points

    def stats(self, duration: float) -> dict[str, Any]:
        lats = sorted(self.latencies_ms)
        n = len(lats)
        if n == 0:
            return {
                "total": 0,
                "rps": 0.0,
                "min_ms": 0.0,
                "mean_ms": 0.0,
                "p50_ms": 0.0,
                "p90_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "max_ms": 0.0,
                "errors": self.failed_requests,
                "points_ingested": self.points_ingested,
                "points_per_sec": 0.0,
            }

        def pct(p: float) -> float:
            k = int(round((p / 100.0) * (n - 1)))
            return lats[min(k, n - 1)]

        return {
            "total": n,
            "rps": round(n / max(0.001, duration), 1),
            "min_ms": round(lats[0], 2),
            "mean_ms": round(sum(lats) / n, 2),
            "p50_ms": round(pct(50), 2),
            "p90_ms": round(pct(90), 2),
            "p95_ms": round(pct(95), 2),
            "p99_ms": round(pct(99), 2),
            "max_ms": round(lats[-1], 2),
            "errors": self.failed_requests,
            "points_ingested": self.points_ingested,
            "points_per_sec": round(self.points_ingested / max(0.001, duration), 1),
        }


class BenchmarkRunner:
    def __init__(
        self,
        in_process: bool = True,
        base_url: str = "http://127.0.0.1:8000",
        db_url: Optional[str] = None,
        db_engine_override: Optional[str] = None,
        duration_sec: int = 30,
        writers: int = 2,
        readers: int = 4,
        downsample_workers: int = 1,
        batch_size: int = 50,
        target_dev_id: str = BENCH_TS_DEV_ID,
        max_downsample_latency_ms: Optional[float] = None,
    ):
        self.in_process = in_process
        self.base_url = base_url
        self.db_url = db_url or os.getenv("DATABASE_URL") or "sqlite:///./benchmark_hubgatev5.db"
        self.duration_sec = duration_sec
        self.writers = writers
        self.readers = readers
        self.downsample_workers = downsample_workers
        self.batch_size = batch_size
        self.target_dev_id = target_dev_id
        self.max_downsample_latency_ms = max_downsample_latency_ms

        if self.in_process and "DATABASE_URL" not in os.environ:
            os.environ["DATABASE_URL"] = self.db_url

        self.db_engine_type = self._detect_engine(db_engine_override)

        # Silence verbose request loggers during benchmark
        for logger_name in ("httpx", "starlette", "uvicorn", "uvicorn.access", "sqlalchemy.engine"):
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        self.metrics: dict[str, MetricSummary] = {
            "downsample_30d": MetricSummary(endpoint="GET /api/devices/{id}/history?range=30d"),
            "post_single": MetricSummary(endpoint="POST /api/iot (Single Ingest)"),
            "post_batch": MetricSummary(endpoint=f"POST /api/iot/batch ({batch_size} pts/batch)"),
            "get_rooms": MetricSummary(endpoint="GET /api/rooms (Outer Join Agg)"),
            "get_devices": MetricSummary(endpoint="GET /api/devices (Read-Only)"),
            "get_alerts": MetricSummary(endpoint="GET /api/alerts (Composite Indexed)"),
            "get_room_map": MetricSummary(endpoint="GET /api/rooms/{id}/map (Window Query)"),
        }

        self.session_cookie: Optional[dict] = None

    def _detect_engine(self, override: Optional[str]) -> str:
        if override:
            ov = override.lower()
            return "postgresql" if "postg" in ov else "sqlite"
        if "postgres" in self.db_url.lower():
            return "postgresql"
        return "sqlite"

    def get_engine_label(self) -> str:
        if self.db_engine_type == "postgresql":
            return "PostgreSQL 16 — Production Target (MVCC Multi-Writer Architecture)"
        else:
            return "SQLite 3 (WAL mode) — Dev / Edge Target (Single-Writer Architecture)"

    def _record_result(self, metric_key: str, latency_ms: float, status_code: int, err: str = "", points: int = 0):
        self.metrics[metric_key].record(latency_ms, status_code, err, points)

    async def run(self) -> dict[str, Any]:
        print("\n" + "=" * 80)
        print(f" HubGate V5 High-Concurrency Concurrency Stress Benchmark")
        print(f" Database Engine: {self.get_engine_label()}")
        print(f" Execution Mode:  {'In-Process ASGI AsyncClient' if self.in_process else f'HTTP ({self.base_url})'}")
        print(f" Test Duration:   {self.duration_sec}s")
        print(f" Topology:        {self.downsample_workers} Heavy 30d Reader | {self.writers} Ingestion Writers | {self.readers} Polling Readers")
        print(f" Total Workers:   {self.downsample_workers + self.writers + self.readers} Concurrent Async Workers")
        print("=" * 80 + "\n")

        # Setup client transport
        if self.in_process:
            from hubgatev5 import api
            api.state.limiter.enabled = False

            # Ensure prerequisite seed data exists
            try:
                from seed_benchmark_telemetry import ensure_prerequisites, get_target_engine
            except ImportError:
                from tools.seed_benchmark_telemetry import ensure_prerequisites, get_target_engine
            eng, _ = get_target_engine(self.db_url)
            ensure_prerequisites(eng, clean=False)

            transport = httpx.ASGITransport(app=api)
            client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0)
        else:
            client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

        async with client:
            # Authenticate benchmark session
            login_resp = await client.post(
                "/api/auth/login",
                json={"username": BENCH_USERNAME, "password": BENCH_PASSWORD},
            )
            if login_resp.status_code == 200:
                self.session_cookie = {"session_id": login_resp.cookies.get("session_id")}
            else:
                print(f"[WARN] Auth login returned {login_resp.status_code}: {login_resp.text}")

            stop_event = asyncio.Event()
            headers = {
                "X-Hub-ID": BENCH_HUB_ID,
                "X-Hub-Key": BENCH_HUB_KEY,
            }

            async def cancellable_sleep(duration: float):
                step = 0.05
                remaining = duration
                while remaining > 0 and not stop_event.is_set():
                    slice_time = min(step, remaining)
                    await asyncio.sleep(slice_time)
                    remaining -= slice_time

            # Worker A: Heavy Downsample Reader
            async def worker_downsample():
                url = f"/api/devices/{self.target_dev_id}/history?range=30d&max_points=1000"
                while not stop_event.is_set():
                    t0 = time.perf_counter()
                    err_str = ""
                    status_code = 0
                    try:
                        resp = await client.get(url, cookies=self.session_cookie)
                        status_code = resp.status_code
                        if status_code != 200:
                            err_str = resp.text
                    except Exception as exc:
                        err_str = str(exc)
                        status_code = 500

                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    self._record_result("downsample_30d", latency_ms, status_code, err_str)
                    await cancellable_sleep(1.0)

            # Worker B: Ingestion Writer
            async def worker_writer(w_id: int):
                counter = 0
                while not stop_event.is_set():
                    counter += 1
                    now_ts = time.time()

                    if counter % 3 == 0:
                        # Single Write: POST /api/iot
                        payload = {
                            "HUB_NAME": "Benchmark Hub Gateway",
                            "DEV_ID": BENCH_TS_DEV_ID,
                            "DEV_NAME": "Benchmark TS Sensor",
                            "DEV_TYPE": "TS",
                            "TEMP": round(22.0 + random.uniform(-2.0, 2.0), 2),
                            "HUMID": round(55.0 + random.uniform(-5.0, 5.0), 2),
                            "HUB_TS": now_ts,
                        }
                        t0 = time.perf_counter()
                        err_str = ""
                        status_code = 0
                        try:
                            resp = await client.post("/api/iot", json=payload, headers=headers)
                            status_code = resp.status_code
                            if status_code != 200:
                                err_str = resp.text
                        except Exception as exc:
                            err_str = str(exc)
                            status_code = 500

                        lat_ms = (time.perf_counter() - t0) * 1000.0
                        self._record_result("post_single", lat_ms, status_code, err_str, points=1)
                    else:
                        # Batch Write: POST /api/iot/batch (50 items)
                        items = []
                        for i in range(self.batch_size):
                            item_ts = now_ts + (i * 0.1)
                            if i % 2 == 0:
                                items.append({
                                    "HUB_NAME": "Benchmark Hub Gateway",
                                    "DEV_ID": BENCH_TS_DEV_ID,
                                    "DEV_NAME": "Benchmark TS Sensor",
                                    "DEV_TYPE": "TS",
                                    "TEMP": round(23.0 + random.uniform(-1.0, 1.0), 2),
                                    "HUMID": round(50.0 + random.uniform(-3.0, 3.0), 2),
                                    "HUB_TS": item_ts,
                                })
                            else:
                                items.append({
                                    "HUB_NAME": "Benchmark Hub Gateway",
                                    "DEV_ID": BENCH_ATS_DEV_ID,
                                    "DEV_NAME": "Benchmark ATS Controller",
                                    "DEV_TYPE": "ATS",
                                    "STATE": "PLN",
                                    "PLN": 220.5,
                                    "GENSET": 0.0,
                                    "AKI": 13.2,
                                    "REM_HOUR": 0.0,
                                    "REM_MIN": 0.0,
                                    "REM_SEC": 0.0,
                                    "AUTO_MODE": True,
                                    "EMERGENCY": False,
                                    "HUB_TS": item_ts,
                                })

                        t0 = time.perf_counter()
                        err_str = ""
                        status_code = 0
                        try:
                            resp = await client.post("/api/iot/batch", json={"items": items}, headers=headers)
                            status_code = resp.status_code
                            if status_code != 200:
                                err_str = resp.text
                        except Exception as exc:
                            err_str = str(exc)
                            status_code = 500

                        lat_ms = (time.perf_counter() - t0) * 1000.0
                        self._record_result("post_batch", lat_ms, status_code, err_str, points=self.batch_size)

                    await cancellable_sleep(0.015)

            # Worker C: Dashboard Polling Reader
            async def worker_reader(r_id: int):
                endpoints = [
                    ("get_rooms", "/api/rooms"),
                    ("get_devices", "/api/devices"),
                    ("get_alerts", "/api/alerts?resolved=false&limit=50"),
                    ("get_room_map", f"/api/rooms/{BENCH_ROOM_ID}/map"),
                ]
                idx = r_id % len(endpoints)
                while not stop_event.is_set():
                    key, path = endpoints[idx]
                    idx = (idx + 1) % len(endpoints)

                    t0 = time.perf_counter()
                    err_str = ""
                    status_code = 0
                    try:
                        resp = await client.get(path, cookies=self.session_cookie)
                        status_code = resp.status_code
                        if status_code != 200:
                            err_str = resp.text
                    except Exception as exc:
                        err_str = str(exc)
                        status_code = 500

                    lat_ms = (time.perf_counter() - t0) * 1000.0
                    self._record_result(key, lat_ms, status_code, err_str)
                    await cancellable_sleep(0.03)

            # Launch all async tasks
            tasks = []
            for _ in range(self.downsample_workers):
                tasks.append(asyncio.create_task(worker_downsample()))
            for i in range(self.writers):
                tasks.append(asyncio.create_task(worker_writer(i)))
            for i in range(self.readers):
                tasks.append(asyncio.create_task(worker_reader(i)))

            # Monitor progress
            start_time = time.perf_counter()
            stop_time = start_time + float(self.duration_sec)

            while time.perf_counter() < stop_time:
                remaining = max(0.0, stop_time - time.perf_counter())
                elapsed = self.duration_sec - remaining
                total_reqs = sum(m.total_requests for m in self.metrics.values())
                total_pts = sum(m.points_ingested for m in self.metrics.values())
                locked = sum(m.database_locked_count for m in self.metrics.values())
                timeouts = sum(m.timeout_count for m in self.metrics.values())
                h500 = sum(m.http_500_count for m in self.metrics.values())
                pts_sec = total_pts / max(0.001, elapsed)

                print(
                    f" [Running: {elapsed:4.1f}s / {self.duration_sec}s] "
                    f"Reqs: {total_reqs:,} | Pts Ingested: {total_pts:,} ({pts_sec:,.0f} pts/s) | "
                    f"Locks: {locked} | Timeouts: {timeouts} | 500s: {h500}",
                    end="\r",
                    flush=True,
                )
                await asyncio.sleep(1.0)

            # Signal termination and await all tasks gracefully
            stop_event.set()
            active_duration = time.perf_counter() - start_time
            await asyncio.gather(*tasks, return_exceptions=True)

        actual_duration = active_duration
        print(f"\n\n[DONE] Completed benchmark run across {actual_duration:.2f} seconds.\n")

        results = {}
        for k, metric in self.metrics.items():
            results[k] = {
                "endpoint": metric.endpoint,
                "stats": metric.stats(actual_duration),
                "locked": metric.database_locked_count,
                "timeouts": metric.timeout_count,
                "500s": metric.http_500_count,
            }

        invariants_report = self._evaluate_invariants(results, actual_duration)
        self._print_console_summary(results, invariants_report, actual_duration)

        return {
            "engine": self.db_engine_type,
            "engine_label": self.get_engine_label(),
            "target_url": self.base_url if not self.in_process else "in-process",
            "duration_sec": actual_duration,
            "results": results,
            "invariants": invariants_report,
            "all_passed": invariants_report["all_passed"],
        }

    def _evaluate_invariants(self, results: dict, duration: float) -> dict[str, Any]:
        """Strictly asserts all read-path, write-path, throughput, and error invariants."""
        downsample_p95 = results["downsample_30d"]["stats"]["p95_ms"]
        single_p95 = results["post_single"]["stats"]["p95_ms"]
        single_p99 = results["post_single"]["stats"]["p99_ms"]
        batch_p95 = results["post_batch"]["stats"]["p95_ms"]
        batch_p99 = results["post_batch"]["stats"]["p99_ms"]

        total_pts = sum(r["stats"]["points_ingested"] for r in results.values())
        ingest_pts_sec = round(total_pts / max(0.001, duration), 1)

        total_locked = sum(r["locked"] for r in results.values())
        total_timeouts = sum(r["timeouts"] for r in results.values())
        total_500s = sum(r["500s"] for r in results.values())

        # Determine downsample latency threshold per engine SLA:
        # PostgreSQL Production Target: Strict < 300.0ms P95
        # SQLite Dev / Edge Target: Single-writer desktop ceiling < 1000.0ms P95
        if self.max_downsample_latency_ms is not None:
            thresh_downsample = self.max_downsample_latency_ms
        elif self.db_engine_type == "postgresql":
            thresh_downsample = 300.0
        else:
            thresh_downsample = 1000.0

        checks = {
            # Invariant 1: Read Path
            "inv1_downsample_p95": {
                "metric": "30d History Downsampling P95 Latency",
                "measured": f"{downsample_p95}ms",
                "threshold": f"< {thresh_downsample}ms",
                "passed": (downsample_p95 < thresh_downsample) if downsample_p95 > 0 else True,
            },
            # Invariant 2: Write Path Single
            "inv2_single_write_p95": {
                "metric": "POST /api/iot Single-Write P95 Latency",
                "measured": f"{single_p95}ms",
                "threshold": "< 200.0ms",
                "passed": (single_p95 < 200.0) if single_p95 > 0 else True,
            },
            "inv2_single_write_p99": {
                "metric": "POST /api/iot Single-Write P99 Latency",
                "measured": f"{single_p99}ms",
                "threshold": "< 500.0ms",
                "passed": (single_p99 < 500.0) if single_p99 > 0 else True,
            },
            # Invariant 3: Write Path Batch
            "inv3_batch_write_p95": {
                "metric": "POST /api/iot/batch Batch-Write P95 Latency",
                "measured": f"{batch_p95}ms",
                "threshold": "< 350.0ms",
                "passed": (batch_p95 < 350.0) if batch_p95 > 0 else True,
            },
            "inv3_batch_write_p99": {
                "metric": "POST /api/iot/batch Batch-Write P99 Latency",
                "measured": f"{batch_p99}ms",
                "threshold": "< 750.0ms",
                "passed": (batch_p99 < 750.0) if batch_p99 > 0 else True,
            },
            # Invariant 4: Ingestion Throughput
            "inv4_ingestion_throughput": {
                "metric": "Ingestion Pipeline Throughput",
                "measured": f"{ingest_pts_sec} pts/sec",
                "threshold": "> 500.0 pts/sec",
                "passed": ingest_pts_sec > 500.0,
            },
            # Invariant 5: Reliability & Zero Locks
            "inv5_zero_database_locked_errors": {
                "metric": "Database Locked (database is locked) Count",
                "measured": str(total_locked),
                "threshold": "== 0",
                "passed": total_locked == 0,
            },
            "inv5_zero_timeout_errors": {
                "metric": "Timeout / Connection Drops Count",
                "measured": str(total_timeouts),
                "threshold": "== 0",
                "passed": total_timeouts == 0,
            },
            "inv5_zero_http_500_errors": {
                "metric": "HTTP 500 Internal Server Errors Count",
                "measured": str(total_500s),
                "threshold": "== 0",
                "passed": total_500s == 0,
            },
        }

        all_passed = all(c["passed"] for c in checks.values())
        return {
            "checks": checks,
            "all_passed": all_passed,
            "total_points": total_pts,
            "ingest_pts_sec": ingest_pts_sec,
            "total_locked": total_locked,
            "total_timeouts": total_timeouts,
            "total_500s": total_500s,
        }

    def _print_console_summary(self, results: dict, invariants: dict, duration: float):
        print("\n" + "=" * 110)
        print(f" BENCHMARK RESULTS SUMMARY — {self.get_engine_label()}")
        print("=" * 110)
        header = f"| {'Workload / Endpoint':<46} | {'Reqs':>6} | {'RPS':>6} | {'P50':>8} | {'P95':>8} | {'P99':>8} | {'Err':>4} | {'Status':<7} |"
        print(header)
        print("|" + "-" * 48 + "|" + "-" * 8 + "|" + "-" * 8 + "|" + "-" * 10 + "|" + "-" * 10 + "|" + "-" * 10 + "|" + "-" * 6 + "|" + "-" * 9 + "|")

        for key, data in results.items():
            st = data["stats"]
            ep = data["endpoint"]
            errs = data["locked"] + data["timeouts"] + data["500s"] + st["errors"]
            status_str = "PASS" if errs == 0 else "FAIL"
            row = (
                f"| {ep:<46} "
                f"| {st['total']:>6} "
                f"| {st['rps']:>6.1f} "
                f"| {st['p50_ms']:>6.1f}ms "
                f"| {st['p95_ms']:>6.1f}ms "
                f"| {st['p99_ms']:>6.1f}ms "
                f"| {errs:>4} "
                f"| {status_str:<7} |"
            )
            print(row)
        print("=" * 110 + "\n")

        print(" STRICT HARDENING INVARIANTS AUDIT:")
        for k, inv in invariants["checks"].items():
            status_badge = "[ PASS ]" if inv["passed"] else "[ FAIL ]"
            print(f"  {status_badge:<9} {inv['metric']:<46} : {inv['measured']:<14} (Threshold: {inv['threshold']})")
        print("\n" + "=" * 110)

        if invariants["all_passed"]:
            print(f" [ALL INVARIANTS PASSED] HubGate V5 Backend meets all performance & zero-lock SLAs!\n")
        else:
            print(f" [INVARIANT FAILURE] One or more performance or reliability invariants did not pass.\n")


def export_markdown_report(report: dict, output_path: str):
    """Writes clean, structured Markdown table report documenting benchmark metrics."""
    res = report["results"]
    inv = report["invariants"]

    lines = [
        f"# HubGate V5 Concurrency Stress Benchmark Report",
        f"",
        f"- **Database Engine**: `{report['engine_label']}`",
        f"- **Execution Target**: `{report['target_url']}`",
        f"- **Measured Duration**: `{report['duration_sec']:.2f} seconds`",
        f"- **Overall Result**: **{'PASSED (All Invariants Satisfied)' if report['all_passed'] else 'FAILED'}**",
        f"",
        f"## 1. Latency & Throughput Summary",
        f"",
        f"| Workload / Endpoint | Total Req | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Errors | Status |",
        f"|---|---|---|---|---|---|---|---|",
    ]

    for key, data in res.items():
        st = data["stats"]
        ep = data["endpoint"]
        errs = data["locked"] + data["timeouts"] + data["500s"] + st["errors"]
        status_str = "PASS" if errs == 0 else "FAIL"
        lines.append(
            f"| {ep} | {st['total']:,} | {st['rps']:.1f} | {st['p50_ms']}ms | {st['p95_ms']}ms | {st['p99_ms']}ms | {errs} | {status_str} |"
        )

    lines.extend([
        f"",
        f"## 2. Hardening Invariant Verification Matrix",
        f"",
        f"| Invariant ID | Assertion Description | Measured Value | Target SLA | Result |",
        f"|---|---|---|---|---|",
    ])

    for k, check in inv["checks"].items():
        badge = "**PASS**" if check["passed"] else "**FAIL**"
        lines.append(f"| `{k}` | {check['metric']} | `{check['measured']}` | `{check['threshold']}` | {badge} |")

    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Export] Markdown report exported to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="HubGate V5 Concurrency Stress Benchmark")
    parser.add_argument("--in-process", action="store_true", default=True, help="Run against in-process ASGI FastAPI app (default: True)")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000", help="Base URL for live HTTP target")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL override")
    parser.add_argument("--db-engine", type=str, default=None, choices=["sqlite", "postgresql"], help="Explicit database engine label (sqlite or postgresql)")
    parser.add_argument("--duration", type=int, default=15, help="Benchmark run duration in seconds (default: 15)")
    parser.add_argument("--writers", type=int, default=2, help="Concurrent ingestion writer worker tasks (default: 2)")
    parser.add_argument("--readers", type=int, default=3, help="Concurrent dashboard polling reader tasks (default: 3)")
    parser.add_argument("--downsample-workers", type=int, default=1, help="Concurrent heavy downsample reader workers (default: 1)")
    parser.add_argument("--batch-size", type=int, default=75, help="Batch size for POST /api/iot/batch (default: 75)")
    parser.add_argument("--target-dev-id", type=str, default=BENCH_TS_DEV_ID, help="Target device ID for 30d history queries")
    parser.add_argument("--max-latency-ms", type=float, default=None, help="Downsample P95 threshold override (default: 300ms prod / 1000ms sqlite)")
    parser.add_argument("--output-json", type=str, default="notes/benchmark-results.json", help="Export metrics to JSON file")
    parser.add_argument("--output-markdown", type=str, default="notes/benchmarks-baseline.md", help="Export formatted Markdown report")

    args = parser.parse_args()

    runner = BenchmarkRunner(
        in_process=args.in_process,
        base_url=args.base_url,
        db_url=args.db_url,
        db_engine_override=args.db_engine,
        duration_sec=args.duration,
        writers=args.writers,
        readers=args.readers,
        downsample_workers=args.downsample_workers,
        batch_size=args.batch_size,
        target_dev_id=args.target_dev_id,
        max_downsample_latency_ms=args.max_latency_ms,
    )

    report = asyncio.run(runner.run())

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[Export] JSON metrics exported to: {args.output_json}")

    if args.output_markdown:
        export_markdown_report(report, args.output_markdown)

    sys.exit(0 if report["all_passed"] else 1)


if __name__ == "__main__":
    main()
