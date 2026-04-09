# Snail Mail Packer

Pack and unpack tools for **Snail Mail** game data files.

Supports two file formats:

- **SnailMail.dat** - Game assets archive (music, textures, level layouts)
- **SnailMail.cfg** - Config file (sound/music volume, resolution, fullscreen, camera settings, etc.)

## Requirements

- Python 3.7

## Usage

### Unpack the data archive

```sh
python3 snailmail_tools.py unpack-dat [SnailMail.dat] [output_dir]
```

Extracts all assets into `output_dir` (default: `dat_unpacked/`) and writes a `_manifest.txt` to preserve the original file order for repacking.

### Repack the data archive

```sh
python3 snailmail_tools.py pack-dat [input_dir] [SnailMail.dat]
```

Reads files from `input_dir` (default: `dat_unpacked/`).

If a `_manifest.txt` is present, it is used to preserve the original entry order.

### Dump config to JSON

```sh
python3 snailmail_tools.py unpack-cfg [SnailMail.cfg] [output.json]
```

Converts the binary config into a human-readable JSON file (default: `SnailMail.cfg.json`).

### Build config from JSON

```sh
python3 snailmail_tools.py pack-cfg [input.json] [SnailMail.cfg]
```

Converts an edited JSON file back into the binary config format.

## Config fields

| Field | Type | Description |
|---|---|---|
| `sound_volume` | float | SFX volume (0.0–1.0) |
| `music_volume` | float | Music volume (0.0–1.0) |
| `fullscreen` | byte | 1 = fullscreen, 0 = windowed |
| `level_flags` | u32 | Bitfield controlling starfield, particles, colour depth, etc. |
| `resolution` | u32 | Display resolution index (0=320×240, 1=640×480, 2=800×600, 3=1024×768, 4=1600×1200) |
| `mouse_sensitivity_x` | float | Cursor sensitivity X |
| `mouse_sensitivity_y` | float | Cursor sensitivity Y |
| `challenge_speed` | u32 | Challenge-mode speed % |
| `challenge_difficulty` | float | Challenge-mode difficulty |
| `camera_distance` | float | Camera distance |
| `camera_height` | float | Camera height |
| `camera_angle_x` | float | Camera angle X |
| `camera_angle_y` | float | Camera angle Y |
| `tutorial_completed` | u32 | 1 after tutorial is played; unlocks additional game modes |
| `modes_unlocked` | byte | 1 after tutorial; same gate as `tutorial_completed` |
