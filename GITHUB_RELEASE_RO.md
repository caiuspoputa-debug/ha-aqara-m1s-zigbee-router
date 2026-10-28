# 0.37.21 — Continuous Cast source wait preserves buffered endings

Fix the confirmed destructive rebuffer path used by individual M1S players
when a continuous YouTube Cast stream temporarily runs out of decoded PCM.
Flush the existing partial PCM batch, retain the TCP writer and hub receiver,
and await real PCM using the existing 35 ms period and 5-second stall limit.
Do not discard buffered tail audio, restart the receiver, add silence frames,
prefill a new transport or add playback-position offsets for this source gap.

Recognition is limited to continuous Cast WAV URLs. Normal radio behavior and
actual transport-fault recovery are unchanged. Explicit Stop/source replacement
still cancels the old session. Buffer constants, normal pacing, receiver shell
commands and group synchronization are preserved.

The user's existing 0.37.20 HA warning confirms action=stop_receiver occurred.
The upstream reason for source starvation remains unverified. Current local
regression results are saved with the release; physical playback is not claimed.

Install integration 0.37.21 and restart HA. Add-on 1.0.30 separately fixes
obsolete manual selections publishing STOPPED for the newly selected song.
