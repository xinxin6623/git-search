---
repo: cyijun/hachimi
decision: maybe
question_match: voice-pipeline/Q3
license_detected: MIT
triaged_at: '2026-05-22'
---

# cyijun/hachimi → **maybe**

## Reasoning
The repo explicitly addresses barge-in interrupt functionality with detailed architecture description (e.g., "detects wake word during playback and immediately stops TTS"), directly mapping to Q3 requirements. However, it fails deepdive criteria: README describes behavior but lacks code-level implementation details for the interrupt state machine; last commit date (2026-01-31) is anomalous (future-dated) making recent activity assessment impossible; and while tests exist, core interrupt logic appears distributed across multiple files (voice_listener.py, tts.py) without clear evidence of <5-file canonical implementation. License MIT is acceptable but insufficient to override active signal and implementation detail gaps. Thus, it qualifies for inbox review.

## Evidence
- README explicitly states 'Barge-in / Interrupt Support: Users can interrupt the assistant while it's speaking. The system detects the wake word during playback and immediately stops TTS to listen to the new command.'
- File tree shows core interrupt components: src/voice_listener.py (wake word detection) and src/tts.py (playback control)
- tests directory exists with multiple test files (test_config.py, test_context_summary.py, test_logger.py)

## Concerns
- Future-dated last commit (2026-01-31) creates uncertainty about actual activity level
- README describes system behavior but lacks code snippets or state machine implementation details
- Core interrupt logic spans multiple files (voice_listener.py, tts.py) without clear evidence of <5-file minimal implementation
