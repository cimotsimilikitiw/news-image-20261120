#!/usr/bin/env python3
import argparse
import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 1_048_576
MAX_DIMENSION = 1024


class PngValidationError(ValueError):
    pass


def _validate_ihdr(chunk_type: bytes, chunk_data: bytes) -> tuple[int, int]:
    if chunk_type != b"IHDR" or len(chunk_data) != 13:
        raise PngValidationError("First chunk must be 13-byte IHDR")
    width, height = struct.unpack(">II", chunk_data[:8])
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise PngValidationError(f"Invalid dimensions: {width}x{height}")
    return width, height


def _read_chunk(data: bytes, offset: int) -> tuple[bytes, bytes, int]:
    if offset + 12 > len(data):
        raise PngValidationError("Truncated PNG chunk header")
    length, chunk_type = struct.unpack(">I4s", data[offset : offset + 8])
    chunk_start = offset + 8
    chunk_end = chunk_start + length
    crc_end = chunk_end + 4
    if crc_end > len(data):
        raise PngValidationError("Truncated PNG chunk payload")
    chunk_data = data[chunk_start:chunk_end]
    expected_crc = struct.unpack(">I", data[chunk_end:crc_end])[0]
    actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise PngValidationError(f"CRC32 mismatch in chunk {chunk_type!r}")
    return chunk_type, chunk_data, crc_end


def validate_png_bytes(data: bytes) -> tuple[int, int]:
    if not data:
        raise PngValidationError("PNG payload is empty")
    if len(data) > MAX_PNG_BYTES:
        raise PngValidationError(f"PNG exceeds {MAX_PNG_BYTES} bytes: {len(data)}")
    if data[:8] != PNG_SIGNATURE:
        raise PngValidationError("Invalid PNG signature")

    offset = 8
    width = 0
    height = 0
    saw_ihdr = False
    saw_iend = False

    while offset < len(data):
        chunk_type, chunk_data, offset = _read_chunk(data, offset)
        if not saw_ihdr:
            width, height = _validate_ihdr(chunk_type, chunk_data)
            saw_ihdr = True
        if chunk_type == b"IEND":
            if chunk_data:
                raise PngValidationError("IEND chunk must be empty")
            saw_iend = True
            break

    if not saw_ihdr or not saw_iend or offset != len(data):
        raise PngValidationError("Incomplete or trailing PNG data")

    return width, height


def resolve_output_path(cli_out: str | None) -> Path:
    if cli_out:
        return Path(cli_out)
    env_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "").strip()
    if env_dir:
        return Path(env_dir) / "entry.png"
    return Path("/output/entry.png")


def write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(f".{dest.name}.tmp.{os.getpid()}")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, dest)
    except OSError:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and emit the 20 November 2026 global news broadsheet PNG."
    )
    parser.add_argument(
        "--out",
        help="Destination file path (overrides MAKEFUN_OUTPUT_DIR and /output/entry.png).",
    )
    args = parser.parse_args(argv)

    source_path = Path(__file__).resolve().parent / "entry.png"
    try:
        payload = source_path.read_bytes()
        width, height = validate_png_bytes(payload)
        dest_path = resolve_output_path(args.out)
        write_atomic(dest_path, payload)
    except (OSError, PngValidationError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    print(f"wrote {dest_path} ({width}x{height}, {len(payload)} bytes, sha256={digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
