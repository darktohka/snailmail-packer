#!/usr/bin/env python3
"""Pack/unpack tools for Snail Mail game data files.

SnailMail.dat - archive containing game assets (music, textures, scripts, etc.)
SnailMail.cfg - 196-byte binary config (sound/music volume, fullscreen, etc.)

Usage:
    python3 snailmail_tools.py unpack-dat  [SnailMail.dat] [output_dir]
    python3 snailmail_tools.py pack-dat    [input_dir]     [SnailMail.dat]
    python3 snailmail_tools.py unpack-cfg  [SnailMail.cfg] [output.json]
    python3 snailmail_tools.py pack-cfg    [input.json]    [SnailMail.cfg]
"""

import argparse
import json
import os
import struct
import sys


# ---------------------------------------------------------------------------
# XOR cipher used by SnailMail.dat
# ---------------------------------------------------------------------------

def dat_xor_key(offset: int) -> int:
    """Return the XOR key byte for a given absolute file offset."""
    return ((3 * offset) & 0xFF) ^ ((offset * offset) & 0xFF)


def dat_crypt(data: bytes, file_offset: int = 0) -> bytearray:
    """XOR-encrypt/decrypt *data* as if it starts at *file_offset* in the .dat."""
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ dat_xor_key(file_offset + i)
    return out


# ---------------------------------------------------------------------------
# SnailMail.dat  -  unpack
# ---------------------------------------------------------------------------

def unpack_dat(dat_path: str, out_dir: str) -> None:
    with open(dat_path, "rb") as f:
        raw = f.read()

    # Decrypt the first 12 bytes to get num_entries and first entry's data_off
    # (which equals the header size).
    hdr_peek = dat_crypt(raw[:12], 0)
    num_entries = struct.unpack_from("<I", hdr_peek, 0)[0]
    header_size = struct.unpack_from("<I", hdr_peek, 8)[0]  # entry[0].data_off

    # Decrypt full header
    header = dat_crypt(raw[:header_size], 0)

    entries = []
    for i in range(num_entries):
        off = 4 + i * 12
        name_off, data_off, data_size = struct.unpack_from("<III", header, off)
        # name is a NUL-terminated string within the header
        name_end = header.index(0, name_off)
        name = header[name_off:name_end].decode("ascii")
        entries.append((name, data_off, data_size))

    print(f"Archive: {dat_path}")
    print(f"Entries: {num_entries}")
    print(f"Header size: {header_size}")
    print()

    manifest = []
    for name, data_off, data_size in entries:
        # Decrypt file data in-place
        file_data = dat_crypt(raw[data_off : data_off + data_size], data_off)

        dest = os.path.join(out_dir, name.replace("\\", "/"))
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as f:
            f.write(file_data)
        manifest.append(name)
        print(f"  {name}  ({data_size} bytes)")

    # Save manifest to preserve original file order for repacking
    manifest_path = os.path.join(out_dir, "_manifest.txt")
    with open(manifest_path, "w") as f:
        for m in manifest:
            f.write(m + "\n")

    print(f"\nExtracted {num_entries} files to {out_dir}")
    print(f"Manifest saved to {manifest_path}")


# ---------------------------------------------------------------------------
# SnailMail.dat  -  pack
# ---------------------------------------------------------------------------

ALIGN = 4  # data alignment (matches original behaviour)


def pack_dat(in_dir: str, dat_path: str) -> None:
    # Collect files - use manifest for ordering if available, else walk+sort.
    manifest_path = os.path.join(in_dir, "_manifest.txt")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            names = [line.strip() for line in f if line.strip()]
        file_list = []
        for name in names:
            full = os.path.join(in_dir, name.replace("/", os.sep))
            if os.path.isfile(full):
                file_list.append((name, full))
            else:
                print(f"WARNING: manifest entry not found on disk: {name}",
                      file=sys.stderr)
    else:
        file_list = []
        for dirpath, _dirs, filenames in os.walk(in_dir):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, in_dir).replace(os.sep, "/")
                archive_name = rel.upper()
                file_list.append((archive_name, full))
        file_list.sort(key=lambda x: x[0])

    num_entries = len(file_list)

    # --- Build name block (NUL-terminated strings) ---
    toc_size = 4 + num_entries * 12  # num_entries DWORD + 12 bytes per entry
    name_block = bytearray()
    name_offsets = []
    for archive_name, _ in file_list:
        name_offsets.append(toc_size + len(name_block))
        name_block.extend(archive_name.encode("ascii") + b"\x00")

    header_size = toc_size + len(name_block)
    # Align header size
    header_size = (header_size + ALIGN - 1) & ~(ALIGN - 1)

    # --- Compute data offsets ---
    data_offset = header_size
    entries_info = []  # (name_off, data_off, data_size, full_path)
    for idx, (archive_name, full_path) in enumerate(file_list):
        fsize = os.path.getsize(full_path)
        entries_info.append((name_offsets[idx], data_offset, fsize, full_path))
        data_offset += fsize
        # Align next entry
        data_offset = (data_offset + ALIGN - 1) & ~(ALIGN - 1)

    # --- Build header ---
    header = bytearray(header_size)
    struct.pack_into("<I", header, 0, num_entries)
    for i, (name_off, d_off, d_size, _) in enumerate(entries_info):
        struct.pack_into("<III", header, 4 + i * 12, name_off, d_off, d_size)
    # Copy name block
    header[toc_size : toc_size + len(name_block)] = name_block

    # --- Build full file ---
    total_size = data_offset
    output = bytearray(total_size)
    output[:header_size] = dat_crypt(header, 0)

    for name_off, d_off, d_size, full_path in entries_info:
        with open(full_path, "rb") as f:
            fdata = f.read()
        output[d_off : d_off + d_size] = dat_crypt(fdata, d_off)

    with open(dat_path, "wb") as f:
        f.write(output)

    print(f"Packed {num_entries} files into {dat_path} ({total_size} bytes)")


# ---------------------------------------------------------------------------
# SnailMail.cfg  -  field definitions
# ---------------------------------------------------------------------------

CFG_SIZE = 196  # 0xC4 bytes

# (offset, type, name)
# Types: 'f' = float32, 'I' = uint32, 'B' = uint8
#
# Field map - reverse-engineered from SnailMailActual.exe:
#
#  +0x00  float   sound_volume          SFX volume (0.0–1.0, default 0.6)
#  +0x04  float   music_volume          Music volume (0.0–1.0, default 0.6)
#  +0x08  byte    fullscreen            1 = fullscreen, 0 = windowed (default 1)
#  +0x0C  u32     _pad_0C               Initialised to 0, no code refs
#  +0x10  u32     _pad_10               Initialised to 0, no code refs
#  +0x14  u32     _pad_14               Initialised to 0, no code refs
#  +0x18  u32     _pad_18               Initialised to 0, no code refs
#  +0x1C  u32     level_flags           Bitfield (default 0x5FE). Bits:
#                                         0x001 – enable feature set A
#                                         0x004 – starfield enabled
#                                         0x010 – particle effects enabled
#                                         0x020 – extra level feature
#                                         0x080 – unknown feature
#                                         0x100 – text layout flag
#                                         0x400 – 32-bit colour (else 16-bit)
#                                       Saved/restored from per-level data.
#  +0x20  byte    _pad_20               Initialised to 0, set from launcher
#  +0x24  u32     _pad_24               Initialised to 0, no code refs
#  +0x28  u32     _pad_28               Initialised to 0, no code refs
#  +0x2C  u32     _pad_2C               Initialised to 0, no code refs
#  +0x30  u32     _pad_30               Initialised to 0, no code refs
#  +0x31  byte    _pad_31               Initialised to 1 (overlaps +0x30 dword)
#  +0x34  u32     resolution            Display resolution index (default 1):
#                                         0=320x240, 1=640x480, 2=800x600,
#                                         3=1024x768, 4=1600x1200
#  +0x38  float   mouse_sensitivity_x   Cursor sensitivity X (default 0.75)
#  +0x3C  float   mouse_sensitivity_y   Cursor sensitivity Y (default 0.75)
#  +0x40  u32     challenge_speed       Challenge-mode speed % (default 40)
#  +0x44  float   challenge_difficulty  Challenge-mode difficulty (default 0.3)
#  +0x48  u32     challenge_difficulty_pct  Challenge diff as int % (default 40)
#  +0x4C  byte    _pad_4C               Initialised to 0
#  +0x4D  byte    _pad_4D               Initialised to 0
#  +0x50  u32     _pad_50               Initialised to 0, no code refs
#  +0x54  u32     _pad_54               Initialised to 0, no code refs
#  +0x58  u32     _pad_58               Initialised to 0, no code refs
#  +0x5C  u32     _pad_5C               Initialised to 0, no code refs
#  +0x60  byte    player_name           16-byte NUL-terminated ASCII player name
#                                       for high-score entry (default empty)
#  --- 0x60..0x87 is the 16-byte name + remaining padding ---
#  +0x88  u32     last_highscore_type   Last viewed high-score table type
#                                         0 = postal, 1 = challenge (default 1)
#  +0x8C  u32     _pad_8C               Initialised to 0, no code refs
#  +0x90  u32     _pad_90               Initialised to 0, no code refs
#  +0x94  u32     _pad_94               Initialised to 0, no code refs
#  +0x98  u32     _pad_98               Initialised to 0, no code refs
#  +0x9C  u32     _pad_9C               Initialised to 0, no code refs
#  +0xA0  u32     starmap_current_level Current star-map level index (default -1.5f
#                                       as raw int - but set at runtime as int)
#  +0xA4  u32     starmap_initial_level Initially-selected star-map level (default
#                                       -1.0f as raw int - set at runtime as int)
#  +0xA8  u32     tutorial_completed    Set to 1 after tutorial played; controls
#                                       whether Postal/Time-Trial/Challenge modes
#                                       are unlocked on the main menu (default 0)
#  +0xAC  u32     sprite_cache_size     Sprite texture cache size in bytes
#                                       (default 1276, set at startup)
#  +0xB0  float   camera_distance       Camera distance (default 10.0)
#  +0xB4  float   camera_height         Camera height (default 2.5)
#  +0xB8  float   camera_angle_x        Camera angle X (default -1.5)
#  +0xBC  float   camera_angle_y        Camera angle Y (default -1.0)
#  +0xC0  byte    modes_unlocked        Set to 1 after tutorial; same gate as
#                                       tutorial_completed (default 0)
#
CFG_FIELDS = [
    (0x00, "f", "sound_volume"),
    (0x04, "f", "music_volume"),
    (0x08, "B", "fullscreen"),
    # 0x09-0x0B: alignment padding
    (0x0C, "I", "_pad_0C"),
    (0x10, "I", "_pad_10"),
    (0x14, "I", "_pad_14"),
    (0x18, "I", "_pad_18"),
    (0x1C, "I", "level_flags"),
    (0x20, "B", "_pad_20"),
    # 0x21-0x23: alignment padding
    (0x24, "I", "_pad_24"),
    (0x28, "I", "_pad_28"),
    (0x2C, "I", "_pad_2C"),
    (0x30, "I", "_pad_30"),
    (0x34, "I", "resolution"),
    (0x38, "f", "mouse_sensitivity_x"),
    (0x3C, "f", "mouse_sensitivity_y"),
    (0x40, "I", "challenge_speed"),
    (0x44, "f", "challenge_difficulty"),
    (0x48, "I", "challenge_difficulty_pct"),
    (0x4C, "B", "_pad_4C"),
    (0x4D, "B", "_pad_4D"),
    # 0x4E-0x4F: alignment padding
    (0x50, "I", "_pad_50"),
    (0x54, "I", "_pad_54"),
    (0x58, "I", "_pad_58"),
    (0x5C, "I", "_pad_5C"),
    (0x60, "I", "player_name_0"),
    (0x64, "I", "player_name_4"),
    (0x68, "I", "player_name_8"),
    (0x6C, "I", "player_name_C"),
    (0x70, "I", "_pad_70"),
    (0x74, "I", "_pad_74"),
    (0x78, "I", "_pad_78"),
    (0x7C, "I", "_pad_7C"),
    (0x80, "I", "_pad_80"),
    (0x84, "I", "_pad_84"),
    (0x88, "I", "last_highscore_type"),
    (0x8C, "I", "_pad_8C"),
    (0x90, "I", "_pad_90"),
    (0x94, "I", "_pad_94"),
    (0x98, "I", "_pad_98"),
    (0x9C, "I", "_pad_9C"),
    (0xA0, "I", "starmap_current_level"),
    (0xA4, "I", "starmap_initial_level"),
    (0xA8, "I", "tutorial_completed"),
    (0xAC, "I", "sprite_cache_size"),
    (0xB0, "f", "camera_distance"),
    (0xB4, "f", "camera_height"),
    (0xB8, "f", "camera_angle_x"),
    (0xBC, "f", "camera_angle_y"),
    (0xC0, "B", "modes_unlocked"),
]


def _cfg_type_size(t: str) -> int:
    return {"f": 4, "I": 4, "B": 1, "h": 2}[t]


def _cfg_type_struct(t: str) -> str:
    return {"f": "<f", "I": "<I", "B": "B", "h": "<h"}[t]


# ---------------------------------------------------------------------------
# SnailMail.cfg  -  unpack (binary → JSON)
# ---------------------------------------------------------------------------

def unpack_cfg(cfg_path: str, json_path: str) -> None:
    with open(cfg_path, "rb") as f:
        data = f.read()

    if len(data) != CFG_SIZE:
        print(f"WARNING: expected {CFG_SIZE} bytes, got {len(data)}", file=sys.stderr)

    obj: dict = {}
    for offset, typ, name in CFG_FIELDS:
        size = _cfg_type_size(typ)
        if offset + size > len(data):
            break
        val = struct.unpack_from(_cfg_type_struct(typ), data, offset)[0]
        # Round floats to avoid noise
        if typ == "f":
            val = round(val, 8)
        obj[name] = val

    with open(json_path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")

    print(f"Unpacked {cfg_path} → {json_path}")


# ---------------------------------------------------------------------------
# SnailMail.cfg  -  pack (JSON → binary)
# ---------------------------------------------------------------------------

def pack_cfg(json_path: str, cfg_path: str) -> None:
    with open(json_path, "r") as f:
        obj = json.load(f)

    data = bytearray(CFG_SIZE)
    for offset, typ, name in CFG_FIELDS:
        if name not in obj:
            continue
        struct.pack_into(_cfg_type_struct(typ), data, offset, obj[name])

    with open(cfg_path, "wb") as f:
        f.write(data)

    print(f"Packed {json_path} → {cfg_path} ({CFG_SIZE} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snail Mail .dat / .cfg pack/unpack tools"
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("unpack-dat", help="Extract files from SnailMail.dat")
    p.add_argument("dat", nargs="?", default="SnailMail.dat")
    p.add_argument("outdir", nargs="?", default="dat_unpacked")

    p = sub.add_parser("pack-dat", help="Create SnailMail.dat from a directory")
    p.add_argument("indir", nargs="?", default="dat_unpacked")
    p.add_argument("dat", nargs="?", default="SnailMail.dat")

    p = sub.add_parser("unpack-cfg", help="Dump SnailMail.cfg to JSON")
    p.add_argument("cfg", nargs="?", default="SnailMail.cfg")
    p.add_argument("json", nargs="?", default="SnailMail.cfg.json")

    p = sub.add_parser("pack-cfg", help="Build SnailMail.cfg from JSON")
    p.add_argument("json", nargs="?", default="SnailMail.cfg.json")
    p.add_argument("cfg", nargs="?", default="SnailMail.cfg")

    args = parser.parse_args()
    if args.command == "unpack-dat":
        unpack_dat(args.dat, args.outdir)
    elif args.command == "pack-dat":
        pack_dat(args.indir, args.dat)
    elif args.command == "unpack-cfg":
        unpack_cfg(args.cfg, args.json)
    elif args.command == "pack-cfg":
        pack_cfg(args.json, args.cfg)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
