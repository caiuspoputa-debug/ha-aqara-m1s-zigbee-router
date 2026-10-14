# Hub-local audio helper

`volume_ctl.c` and `sound.sh` are original MIT-licensed helper sources.
`volume_ctl` is the bundled static MIPS32 little-endian control executable,
not firmware. It only writes the dedicated USER mixer element
`M1S Media Volume` after verifying its type, count and range.
The statically linked musl runtime's license is in `MUSL_COPYRIGHT`.

Rebuild with Zig 0.13.0:

```sh
zig cc -target mipsel-linux-musl -mcpu=mips32 -static -Os -s -Wall -Wextra -Werror volume_ctl.c -o volume_ctl
```

The PCM config uses the existing hub ALSA library. No ALSA library or native
Aqara executable is redistributed. The config is selected per-player with
`ALSA_CONFIG_PATH`, not system-wide. The `plug` wrapper converts stored WAVs
to the canonical stream format. Timing and buffer arguments remain in the
Python transport modules. See `LOCAL_AUDIO_RO.md` for migration and test limits.
