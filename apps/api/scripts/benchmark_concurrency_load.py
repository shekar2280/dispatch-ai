import asyncio
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
API_DIR = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "docs" / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

TARGET_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CONCURRENCY_TIERS = [1, 5, 10, 25]
REQUESTS_PER_USER = 20


def calculate_percentiles(values):
    if not values:
        return {"min": 0, "p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0, "mean": 0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "min": round(sorted_vals[0], 2),
        "p50": round(statistics.median(sorted_vals), 2),
        "p90": round(sorted_vals[max(0, math.ceil(n * 0.90) - 1)], 2),
        "p95": round(sorted_vals[max(0, math.ceil(n * 0.95) - 1)], 2),
        "p99": round(sorted_vals[max(0, math.ceil(n * 0.99) - 1)], 2),
        "max": round(sorted_vals[-1], 2),
        "mean": round(statistics.mean(sorted_vals), 2),
    }


async def run_worker(client: httpx.AsyncClient, worker_id: int, requests_count: int, latencies: list, errors: list):
    for i in range(requests_count):
        start = time.perf_counter()
        try:
            resp = await client.get("/health", timeout=5.0)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if resp.status_code == 200:
                latencies.append(elapsed_ms)
            else:
                errors.append(f"HTTP_{resp.status_code}")
        except Exception as exc:
            errors.append(str(exc.__class__.__name__))


async def execute_tier(concurrency: int):
    total_requests = concurrency * REQUESTS_PER_USER
    latencies = []
    errors = []

    limits = httpx.Limits(max_keepalive_connections=concurrency + 5, max_connections=concurrency + 10)
    async with httpx.AsyncClient(base_url=TARGET_BASE_URL, limits=limits, timeout=10.0) as client:
        start_time = time.perf_counter()
        tasks = [
            run_worker(client, worker_id, REQUESTS_PER_USER, latencies, errors)
            for worker_id in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    rps = round(len(latencies) / total_time, 2) if total_time > 0 else 0
    percentiles = calculate_percentiles(latencies)
    error_rate = round((len(errors) / total_requests) * 100, 2) if total_requests > 0 else 0

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "successful_requests": len(latencies),
        "error_count": len(errors),
        "error_rate_percent": error_rate,
        "total_duration_seconds": round(total_time, 3),
        "throughput_rps": rps,
        "latency_percentiles_ms": percentiles,
    }


async def main():
    print("\n==================================================================")
    print(" DISPATCH AI — CONCURRENCY & API THROUGHPUT BENCHMARK (1, 5, 10, 25)")
    print("==================================================================")
    print(f"Target: {TARGET_BASE_URL}/health and API pipeline under load")
    print(f"System: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    tier_results = []
    for tier in CONCURRENCY_TIERS:
        print(f"Testing Concurrency Tier: {tier:2d} simultaneous calls/users ... ", end="", flush=True)
        res = await execute_tier(tier)
        tier_results.append(res)
        print(f"Done in {res['total_duration_seconds']}s | RPS: {res['throughput_rps']:<6} | p95: {res['latency_percentiles_ms']['p95']} ms")

    print("\n" + "=" * 80)
    print(f"{'Concurrency':<12} | {'Requests':<9} | {'RPS':<8} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'p99 (ms)':<9} | {'Error %':<8}")
    print("-" * 80)
    for r in tier_results:
        p = r["latency_percentiles_ms"]
        print(f"{r['concurrency']:<12} | {r['total_requests']:<9} | {r['throughput_rps']:<8} | {p['p50']:<9} | {p['p95']:<9} | {p['p99']:<9} | {r['error_rate_percent']:<8}")
    print("=" * 80 + "\n")

    load_results_file = BENCHMARK_DIR / "load-test-results.json"
    existing_data = {}
    if load_results_file.exists():
        try:
            with open(load_results_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = {}

    existing_data["concurrency_load_benchmarks"] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "target_url": TARGET_BASE_URL,
        "tiers": tier_results
    }

    with open(load_results_file, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2)

    print(f"Concurrency results appended to: {load_results_file}\n")


if __name__ == "__main__":
    asyncio.run(main())
