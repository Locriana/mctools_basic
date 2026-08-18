# mctools_basic
MC-101, MC-707, MV-1 basic SysEx communication tools using their USB interface

In this project I updated several things, including a better communication implementation and I briefly tested it with MV-1 (I intended the initial version to work with MC-101 and MC-707).

Here is the link to the initial version: https://github.com/Locriana/mcpoker

And here is the related youtube video in which I talk about this project: https://youtu.be/rf3axWltGYk

## 4-Layer SysEx address model

The SysEx address top byte is a **layer selector**, not just a namespace tag.
Probing the same base address under different top bytes returns different data layers:

| Top byte | Layer | Returns | Field size |
|----------|-------|---------|------------|
| `0x10` | Project name | Project/pattern name (ASCII, space-padded) | 16 bytes |
| `0x20` | Clip/scene names | Per-clip name in the 8×16 clip grid (ASCII, space-padded) | 12 bytes |
| `0x30` | Tone names + params | Per-clip tone name + partial data | (existing) |
| `0x40` | System metadata | Project-level info (tempo, time signature, etc.) | ~60 bytes |

Previously, only the `0x30` (tone) layer was used. The `0x20` and `0x10` layers
enable **reading and writing the full project structure over SysEx** — clip names,
scene names, and the project name — without the `.mpj` file.

### Usage

```python
zcore = ZenCoreTools(comm)

# Read the project name
print(zcore.project_name_read())

# Write the project name
zcore.project_name_write("My Project")

# Read a clip name (track 1, clip 0)
print(zcore.clip_name_read(0, 0))

# Write a clip name
zcore.clip_name_write(0, 0, "INTRO")

# Print the full 8×16 clip/scene name grid
zcore.disp_clip_grid()
```

### Notes

- DT1 writes to the `0x20` and `0x10` layers are **not acknowledged** by the device,
  but are verifiable by RQ1 read-back after ~300ms.
- Writes are surgical: only the name field is overwritten, surrounding binary data
  is preserved.
- The `hack_tools.py` `dump_settings` function already dumps `0x10000000`–`0x10001000`
  (the `0x10` layer) — the data is there, this PR adds the interpretation.

### Verified on

- MC-101 v1.82 (live RQ1 + DT1, 2026-08-16)
- See: https://github.com/soobrosa/mc101-firmware-re — REPORT.md §12.4

