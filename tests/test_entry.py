import ast
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import main as entry_cli

ROOT = Path(__file__).resolve().parent.parent


def _make_ihdr_chunk(width: int, height: int) -> bytes:
    payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    crc = zlib.crc32(b"IHDR" + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + b"IHDR" + payload + struct.pack(">I", crc)


def _make_iend_chunk() -> bytes:
    crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    return struct.pack(">I", 0) + b"IEND" + struct.pack(">I", crc)


class EntryTests(unittest.TestCase):
    def test_valid_entry_png(self) -> None:
        png_path = ROOT / "entry.png"
        data = png_path.read_bytes()
        self.assertLessEqual(len(data), entry_cli.MAX_PNG_BYTES)
        width, height = entry_cli.validate_png_bytes(data)
        self.assertEqual((width, height), (1024, 1024))

    def test_corrupted_crc32_rejected(self) -> None:
        data = bytearray((ROOT / "entry.png").read_bytes())
        data[29] ^= 0xFF
        with self.assertRaises(entry_cli.PngValidationError):
            entry_cli.validate_png_bytes(bytes(data))

    def test_oversized_payload_rejected(self) -> None:
        oversized = entry_cli.PNG_SIGNATURE + b"\x00" * entry_cli.MAX_PNG_BYTES
        with self.assertRaises(entry_cli.PngValidationError):
            entry_cli.validate_png_bytes(oversized)

    def test_over_dimensioned_ihdr_rejected(self) -> None:
        bad_png = entry_cli.PNG_SIGNATURE + _make_ihdr_chunk(1025, 1024) + _make_iend_chunk()
        with self.assertRaises(entry_cli.PngValidationError):
            entry_cli.validate_png_bytes(bad_png)

    def test_cli_help_flag(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--out", proc.stdout)

    def test_two_run_byte_identical_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "env_out"
            cli_out = Path(tmpdir) / "cli_out" / "custom.png"

            env = dict(os.environ)
            env["MAKEFUN_OUTPUT_DIR"] = str(env_dir)

            res1 = subprocess.run(
                [sys.executable, str(ROOT / "main.py")],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res1.returncode, 0, res1.stderr)

            res2 = subprocess.run(
                [sys.executable, str(ROOT / "main.py"), "--out", str(cli_out)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res2.returncode, 0, res2.stderr)

            bytes1 = (env_dir / "entry.png").read_bytes()
            bytes2 = cli_out.read_bytes()
            self.assertEqual(
                hashlib.sha256(bytes1).hexdigest(),
                hashlib.sha256(bytes2).hexdigest(),
            )
            self.assertEqual(bytes1, bytes2)

    def test_zero_network_imports(self) -> None:
        allowed = {"argparse", "hashlib", "os", "pathlib", "struct", "sys", "zlib"}
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.issubset(allowed), f"Unexpected imports: {imported - allowed}")


if __name__ == "__main__":
    unittest.main()
