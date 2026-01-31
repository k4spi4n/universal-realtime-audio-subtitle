## 2026-01-31 - [Accuracy Trumps Speed in Realtime Whisper]
**Learning:** Attempting to switch `faster-whisper` from `beam_size=5` to `beam_size=1` (Greedy) for speed was rejected. The user perceives `beam_size=5` as having "visually no delay" while offering much higher accuracy.
**Action:** Do not assume `beam_size=1` is the default optimization for realtime Whisper if the hardware (GPU) can handle `beam_size=5`. Verify user's accuracy tolerance first.

## 2026-01-31 - [Unreachable Transcription Logic]
**Learning:** The `server.py` loop contained a secondary transcription block (using `beam_size=1`) that was intended as a fallback or optimization but was logically unreachable because the primary block (using `beam_size=5`) always reset the timer. This created "dead code" that added confusion without functionality.
**Action:** Audit timestamp-based state machines in loops to ensure all branches are actually reachable.
