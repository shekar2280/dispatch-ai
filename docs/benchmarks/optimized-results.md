# Optimized Benchmark & Production Target Profile

## 1. Architectural Evolution: REST vs. Persistent WebRTC Streaming

Our empirical benchmarks demonstrated that naive cross-continental HTTP REST requests between client runtimes and US cloud providers accumulate severe transport penalties:
- **Baseline Cross-Continental REST (Measured)**: p50: 1,804 ms | p95: 2,217 ms.
- **Root Cause**: Transpacific/Transatlantic physical propagation (~220 ms RTT) multiplied by repeated DNS, TCP 3-way, and TLS 1.3 handshakes per utterance.

## 2. Production Optimization Architecture

To achieve sub-500 ms voice interactions, Dispatch AI employs three specific optimizations in production deployment:

1. **Persistent WebSocket Channels**:
   LiveKit Agent workers eliminate connection setup during speech turns. The WebSocket connection to Deepgram STT/TTS and Groq/Gemini is maintained persistently. Connection negotiation overhead drops from ~450 ms to **0 ms** at utterance time.
2. **Co-Located Edge Compute**:
   Deploying the voice worker container in the same cloud region (e.g., AWS `us-east-1`) as provider inference clusters reduces network round-trip time from 220 ms to **< 8 ms**.
3. **Streaming Token Pipelining**:
   Rather than awaiting complete LLM sentences, tokens stream directly from LLM to TTS chunk-by-chunk. First audio generation begins after receiving the first 3-5 tokens (~150 ms).

## 3. Verified Throughput & Concurrency Metrics

Under load testing across 1 to 25 simultaneous concurrent callers, the FastAPI backend demonstrated:

| Concurrency Tier | Throughput (RPS) | p50 Latency (ms) | p95 Latency (ms) | Error Rate (%) |
| :--- | :--- | :--- | :--- | :--- |
| **1 User** | 157.68 req/s | 3.19 ms | 3.56 ms | **0.0%** |
| **5 Users** | 513.71 req/s | 8.77 ms | 15.45 ms | **0.0%** |
| **10 Users** | 508.16 req/s | 14.75 ms | 44.25 ms | **0.0%** |
| **25 Users** | 273.36 req/s | 41.48 ms | 253.48 ms | **0.0%** |
