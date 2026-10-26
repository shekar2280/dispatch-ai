# Benchmark Methodology & Latency Definitions

## 1. Metric Definition: Turn-to-Speech Latency (TTSL)

Latency in Dispatch AI is defined strictly as **End of Patient Speech to First Audible Audio Byte**:

$$\text{Latency} = \Delta t(\text{VAD End-of-Utterance}) + \text{LLM TTFT} + \text{TTS TTFB}$$

Where:
- **$\Delta t(\text{VAD End-of-Utterance})$**: Duration between physical cessation of vocal audio and emission of the VAD/STT endpoint signal.
- **$\text{LLM TTFT}$**: Time to First Token from the LLM after receiving the user transcript.
- **$\text{TTS TTFB}$**: Time to First Byte from the speech synthesis engine before initial audio packet playback begins.

## 2. Benchmark Environment & Reproduction

| Parameter | Specification |
| :--- | :--- |
| **Operating System** | Windows 11 Pro (x86_64) |
| **Python Runtime** | Python 3.12.14 Virtualenv (`.venv`) |
| **Geographic Location** | Asia/Kolkata (UTC+05:30) |
| **External Providers** | Groq (`openai/gpt-oss-20b`), Deepgram (`aura-asteria-en`), Silero VAD |
| **Dataset** | 100 representative clinical patient utterances (general inquiry, doctor slot search, rescheduling, acute triage deflection, edge cases) |

### Reproduction Command
```powershell
Set-Location apps/api
python scripts/benchmark_voice_latency.py 100
```
Outputs: `docs/benchmarks/load-test-results.json`
