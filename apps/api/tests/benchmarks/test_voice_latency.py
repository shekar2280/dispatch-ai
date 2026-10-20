import math
import statistics
import pytest
from app.services.voice.telemetry import VoiceTelemetry, benchmark_summary


def test_telemetry_records_and_aggregates_percentiles():
    telemetry = VoiceTelemetry()
    for i in range(1, 101):
        telemetry.record(type("Metric", (), {
            "type": "eou_metrics",
            "speech_id": f"turn-{i}",
            "request_id": f"req-eou-{i}",
            "transcription_delay": 0.12,
            "end_of_utterance_delay": 0.13,
            "cancelled": False,
        }))
        telemetry.record(type("Metric", (), {
            "type": "llm_metrics",
            "speech_id": f"turn-{i}",
            "request_id": f"req-llm-{i}",
            "ttft": 0.18,
            "prompt_tokens": 150,
            "completion_tokens": 25,
            "cancelled": False,
        }))
        telemetry.record(type("Metric", (), {
            "type": "tts_metrics",
            "speech_id": f"turn-{i}",
            "request_id": f"req-tts-{i}",
            "ttfb": 0.11,
            "characters_count": 80,
            "audio_duration": 2.5,
            "cancelled": False,
        }))

    payload = telemetry.payload()
    benchmarks = payload["benchmarks"]

    assert len(payload["turns"]) == 100
    assert benchmarks["total_latency_ms"]["sample_count"] == 100
    assert benchmarks["total_latency_ms"]["median_ms"] == 420
    assert benchmarks["total_latency_ms"]["p95_ms"] == 420
    assert benchmarks["total_latency_ms"]["p95_ms"] < 500


def test_benchmark_summary_handles_tail_latency_spikes():
    turns = []
    for i in range(1, 101):
        latency = 380 if i <= 95 else 550
        turns.append({"total_latency_ms": latency})

    summary = benchmark_summary(turns)
    metric = summary["total_latency_ms"]

    assert metric["sample_count"] == 100
    assert metric["median_ms"] == 380
    assert metric["p95_ms"] == 380
