# Baseline Benchmark Results

## 1. Un-Optimized Cross-Continental REST Baseline (100 Iterations)

- **Date**: 2026-10-19
- **Dataset**: 100 Patient Speech Interactions
- **Target Resume Claim**: Voice response latency < 500 ms
- **Verification Status**: **Target Not Met on Naive Cross-Continental REST** (p50: 1,804.31 ms, p95: 2,217.74 ms)

### Empirical Percentile Distribution

| Metric | Min (ms) | p50 / Median (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Max (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **STT / EOU Delay** | 120.00 | 133.50 | 147.00 | 147.00 | 147.00 | 147.00 |
| **LLM TTFT** | 160.00 | 494.62 | 644.93 | 682.46 | 1,089.18 | 1,134.21 |
| **TTS TTFB** | 863.45 | 1,217.21 | 1,388.08 | 1,428.69 | 1,595.72 | 1,634.19 |
| **TOTAL PIPELINE** | **1,179.57** | **1,804.31** | **2,070.44** | **2,217.74** | **2,378.32** | **2,391.18** |

## 2. Root Cause Analysis

1. **Cross-Continental Round-Trip Time (RTT)**: 
   Testing from client infrastructure in India (`Asia/Kolkata`) against US-based provider endpoints (`api.groq.com`, `api.deepgram.com`) incurs a baseline fiber propagation penalty of ~220 ms per packet round-trip.
2. **Cold TLS Handshake Overhead**:
   Per-request HTTPS REST negotiation pays DNS resolution + TCP 3-way handshake + TLS 1.3 negotiation on every turn.
3. **Architectural Solution**:
   Persistent WebRTC / WebSocket channels (`livekit-agents` worker) with prewarmed worker process pools and regional co-location.
