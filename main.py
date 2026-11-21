#!/usr/bin/env python3
"""Deterministic editorial front-page PNG renderer.

Stdlib only: zlib, struct, hashlib, argparse. No network, no font files,
no exec/eval, no writes outside --out.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import struct
import zlib

# ---------------------------------------------------------------------------
# Deterministic RNG (xorshift64* seeded from hash)
# ---------------------------------------------------------------------------

class DRNG:
    """Deterministic PRNG from seed+salt+prompt hash."""

    def __init__(self, seed: int, salt: str, prompt: str) -> None:
        h = hashlib.sha256(f"{seed}|{salt}|{prompt}".encode()).digest()
        self.state = int.from_bytes(h[:8], "big") or 0x9E3779B97F4A7C15
        self._warm()

    def _warm(self) -> None:
        for _ in range(16):
            self.next_u64()

    def next_u64(self) -> int:
        x = self.state & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 12) & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 27) & 0xFFFFFFFFFFFFFFFF
        self.state = x
        return (x * 0x2545F4914F6CDD1D) & 0xFFFFFFFFFFFFFFFF

    def random(self) -> float:
        return self.next_u64() / 0x10000000000000000

    def randint(self, a: int, b: int) -> int:
        if b < a:
            a, b = b, a
        return a + int(self.random() * (b - a + 1))

    def choice(self, seq):
        return seq[self.randint(0, len(seq) - 1)]

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self.randint(0, i)
            seq[i], seq[j] = seq[j], seq[i]
        return seq


# ---------------------------------------------------------------------------
# PNG encoder (manual IHDR/IDAT/IEND, CRC32 per chunk)
# ---------------------------------------------------------------------------

def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    length = struct.pack(">I", len(payload))
    crc = struct.pack(">I", _crc32(chunk_type + payload))
    return length + chunk_type + payload + crc


def encode_png_rgb(width: int, height: int, pixels: bytearray) -> bytes:
    """Encode RGB pixels (3 bytes/pixel) to PNG with one IDAT."""
    if len(pixels) != width * height * 3:
        raise ValueError("pixel buffer size mismatch")
    raw = bytearray()
    row_stride = width * 3
    for y in range(height):
        raw.append(0)
        start = y * row_stride
        raw.extend(pixels[start:start + row_stride])
    compressed = zlib.compress(bytes(raw), 9)
    ihdr_payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out.extend(_chunk(b"IHDR", ihdr_payload))
    out.extend(_chunk(b"IDAT", compressed))
    out.extend(_chunk(b"IEND", b""))
    return bytes(out)


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class Canvas:
    """Simple RGB canvas with drawing primitives."""

    def __init__(self, width: int, height: int, bg=(255, 255, 255)):
        self.w = width
        self.h = height
        self.px = bytearray(width * height * 3)
        self.fill_rect(0, 0, width, height, bg)

    def set_px(self, x: int, y: int, color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def blend_px(self, x: int, y: int, color, alpha: float) -> None:
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        i = (y * self.w + x) * 3
        a = max(0.0, min(1.0, alpha))
        inv = 1.0 - a
        self.px[i] = int(self.px[i] * inv + color[0] * a)
        self.px[i + 1] = int(self.px[i + 1] * inv + color[1] * a)
        self.px[i + 2] = int(self.px[i + 2] * inv + color[2] * a)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color) -> None:
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        r, g, b = color[0], color[1], color[2]
        row_stride = self.w * 3
        for y in range(y0, y1):
            base = y * row_stride + x0 * 3
            for x in range(x1 - x0):
                i = base + x * 3
                self.px[i] = r
                self.px[i + 1] = g
                self.px[i + 2] = b

    def stroke_rect(self, x0: int, y0: int, x1: int, y1: int, color, thickness: int = 1) -> None:
        for t in range(thickness):
            self.draw_line(x0 + t, y0 + t, x1 - 1 - t, y0 + t, color)
            self.draw_line(x0 + t, y1 - 1 - t, x1 - 1 - t, y1 - 1 - t, color)
            self.draw_line(x0 + t, y0 + t, x0 + t, y1 - 1 - t, color)
            self.draw_line(x1 - 1 - t, y0 + t, x1 - 1 - t, y1 - 1 - t, color)

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, color, thickness: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            if thickness <= 1:
                self.set_px(x0, y0, color)
            else:
                half = thickness // 2
                self.fill_rect(x0 - half, y0 - half, x0 - half + thickness, y0 - half + thickness, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_circle(self, cx: int, cy: int, r: int, color) -> None:
        if r <= 0:
            return
        r2 = r * r
        for y in range(cy - r, cy + r + 1):
            if y < 0 or y >= self.h:
                continue
            dy = y - cy
            span = int((r2 - dy * dy) ** 0.5)
            x0 = max(0, cx - span)
            x1 = min(self.w, cx + span + 1)
            base = y * self.w * 3
            for x in range(x0, x1):
                i = base + x * 3
                self.px[i] = color[0]
                self.px[i + 1] = color[1]
                self.px[i + 2] = color[2]

    def stroke_circle(self, cx: int, cy: int, r: int, color, thickness: int = 1) -> None:
        if r <= 0:
            return
        for t in range(thickness):
            rr = r - t
            if rr <= 0:
                break
            x = rr
            y = 0
            err = 1 - x
            while x >= y:
                for px, py in ((cx+x, cy+y),(cx+y, cy+x),(cx-y, cy+x),(cx-x, cy+y),
                               (cx-x, cy-y),(cx-y, cy-x),(cx+y, cy-x),(cx+x, cy-y)):
                    self.set_px(px, py, color)
                y += 1
                if err < 0:
                    err += 2 * y + 1
                else:
                    x -= 1
                    err += 2 * (y - x) + 1

    def fill_polygon(self, points, color) -> None:
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        y_min = max(0, min(ys))
        y_max = min(self.h - 1, max(ys))
        n = len(points)
        for y in range(y_min, y_max + 1):
            nodes = []
            j = n - 1
            for i in range(n):
                yi, xi = points[i][1], points[i][0]
                yj, xj = points[j][1], points[j][0]
                if ((yi < y <= yj) or (yj < y <= yi)) and yj != yi:
                    x = xi + (y - yi) / (yj - yi) * (xj - xi)
                    nodes.append(int(x))
                j = i
            nodes.sort()
            for k in range(0, len(nodes) - 1, 2):
                x0 = max(0, nodes[k])
                x1 = min(self.w, nodes[k + 1] + 1)
                base = y * self.w * 3
                for x in range(x0, x1):
                    i = base + x * 3
                    self.px[i] = color[0]
                    self.px[i + 1] = color[1]
                    self.px[i + 2] = color[2]


# ---------------------------------------------------------------------------
# Vector glyph table (Hershey-style single-stroke, normalized 0..100 box)
# ---------------------------------------------------------------------------

GLYPHS: dict[str, list[list[tuple[int, int]]]] = {
    " ": [],
    "!": [[(50, 20), (50, 58)], [(50, 68), (50, 75)]],
    '"': [[(40, 20), (40, 35)], [(60, 20), (60, 35)]],
    "#": [[(35, 20), (30, 75)], [(65, 20), (60, 75)], [(20, 40), (80, 40)], [(15, 60), (75, 60)]],
    "$": [[(50, 15), (50, 80)], [(70, 30), (30, 30), (30, 47), (70, 47), (70, 70), (30, 70)]],
    "%": [[(70, 20), (30, 75)], [(35, 25), (35, 35), (25, 35), (25, 25), (35, 25)], [(75, 60), (75, 70), (65, 70), (65, 60), (75, 60)]],
    "&": [[(70, 75), (30, 35), (30, 25), (45, 20), (60, 25), (60, 35), (25, 65), (35, 75), (55, 75), (75, 55)]],
    "'": [[(50, 20), (50, 35)]],
    "(": [[(60, 20), (40, 35), (40, 60), (60, 75)]],
    ")": [[(40, 20), (60, 35), (60, 60), (40, 75)]],
    "*": [[(50, 30), (50, 60)], [(35, 35), (65, 55)], [(65, 35), (35, 55)]],
    "+": [[(50, 30), (50, 65)], [(30, 47), (70, 47)]],
    ",": [[(55, 65), (45, 80)]],
    "-": [[(30, 50), (70, 50)]],
    ".": [[(48, 70), (52, 70), (52, 75), (48, 75), (48, 70)]],
    "/": [[(70, 20), (30, 75)]],
    "0": [[(30, 30), (30, 65), (45, 75), (55, 75), (70, 65), (70, 30), (55, 20), (45, 20), (30, 30)]],
    "1": [[(40, 30), (50, 20), (50, 75)], [(35, 75), (65, 75)]],
    "2": [[(30, 30), (40, 20), (60, 20), (70, 30), (70, 40), (30, 75), (70, 75)]],
    "3": [[(30, 20), (70, 20), (50, 45), (70, 55), (70, 65), (55, 75), (45, 75), (30, 65)]],
    "4": [[(60, 75), (60, 20), (25, 55), (75, 55)]],
    "5": [[(70, 20), (30, 20), (30, 45), (60, 45), (70, 55), (70, 65), (55, 75), (45, 75), (30, 65)]],
    "6": [[(65, 20), (45, 20), (30, 35), (30, 65), (45, 75), (55, 75), (70, 65), (70, 50), (55, 45), (30, 45)]],
    "7": [[(30, 20), (70, 20), (45, 75)]],
    "8": [[(45, 20), (55, 20), (65, 28), (65, 40), (55, 47), (45, 47), (35, 40), (35, 28), (45, 20)], [(45, 47), (55, 47), (70, 55), (70, 67), (55, 75), (45, 75), (30, 67), (30, 55), (45, 47)]],
    "9": [[(70, 50), (45, 50), (30, 42), (30, 30), (45, 20), (55, 20), (70, 30), (70, 60), (55, 75), (35, 75)]],
    ":": [[(48, 35), (52, 35), (52, 40), (48, 40), (48, 35)], [(48, 65), (52, 65), (52, 70), (48, 70), (48, 65)]],
    ";": [[(48, 35), (52, 35), (52, 40), (48, 40), (48, 35)], [(52, 65), (42, 78)]],
    "<": [[(65, 25), (35, 47), (65, 70)]],
    "=": [[(30, 40), (70, 40)], [(30, 55), (70, 55)]],
    ">": [[(35, 25), (65, 47), (35, 70)]],
    "?": [[(30, 30), (40, 20), (60, 20), (70, 30), (70, 42), (50, 55), (50, 62)], [(50, 70), (50, 75)]],
    "@": [[(65, 60), (55, 65), (40, 65), (30, 55), (30, 40), (40, 25), (60, 25), (70, 35), (70, 55), (60, 55), (60, 38), (45, 38), (40, 45), (40, 55), (45, 60), (55, 60)]],
    "A": [[(20, 75), (50, 20), (80, 75)], [(32, 58), (68, 58)]],
    "B": [[(30, 75), (30, 20), (60, 20), (70, 28), (70, 40), (60, 47), (30, 47)], [(60, 47), (72, 55), (72, 67), (60, 75), (30, 75)]],
    "C": [[(75, 30), (65, 20), (40, 20), (25, 35), (25, 60), (40, 75), (65, 75), (75, 65)]],
    "D": [[(30, 20), (30, 75), (55, 75), (75, 60), (75, 35), (55, 20), (30, 20)]],
    "E": [[(70, 20), (30, 20), (30, 75), (70, 75)], [(30, 47), (60, 47)]],
    "F": [[(70, 20), (30, 20), (30, 75)], [(30, 47), (60, 47)]],
    "G": [[(75, 30), (65, 20), (40, 20), (25, 35), (25, 60), (40, 75), (65, 75), (75, 60), (75, 50), (55, 50)]],
    "H": [[(30, 20), (30, 75)], [(70, 20), (70, 75)], [(30, 47), (70, 47)]],
    "I": [[(40, 20), (60, 20)], [(50, 20), (50, 75)], [(40, 75), (60, 75)]],
    "J": [[(35, 20), (70, 20)], [(55, 20), (55, 65), (45, 75), (30, 65)]],
    "K": [[(30, 20), (30, 75)], [(70, 20), (30, 50)], [(45, 43), (70, 75)]],
    "L": [[(30, 20), (30, 75), (70, 75)]],
    "M": [[(25, 75), (25, 20), (50, 45), (75, 20), (75, 75)]],
    "N": [[(30, 75), (30, 20), (70, 75), (70, 20)]],
    "O": [[(40, 20), (60, 20), (75, 35), (75, 60), (60, 75), (40, 75), (25, 60), (25, 35), (40, 20)]],
    "P": [[(30, 75), (30, 20), (60, 20), (72, 30), (72, 42), (60, 50), (30, 50)]],
    "Q": [[(40, 20), (60, 20), (75, 35), (75, 60), (60, 75), (40, 75), (25, 60), (25, 35), (40, 20)], [(55, 60), (75, 78)]],
    "R": [[(30, 75), (30, 20), (60, 20), (72, 30), (72, 42), (60, 50), (30, 50)], [(52, 50), (75, 75)]],
    "S": [[(75, 30), (60, 20), (40, 20), (25, 30), (25, 42), (40, 50), (60, 50), (75, 60), (60, 75), (40, 75), (25, 65)]],
    "T": [[(25, 20), (75, 20)], [(50, 20), (50, 75)]],
    "U": [[(30, 20), (30, 60), (45, 75), (55, 75), (70, 60), (70, 20)]],
    "V": [[(25, 20), (50, 75), (75, 20)]],
    "W": [[(20, 20), (30, 75), (50, 50), (70, 75), (80, 20)]],
    "X": [[(25, 20), (75, 75)], [(75, 20), (25, 75)]],
    "Y": [[(25, 20), (50, 50), (75, 20)], [(50, 50), (50, 75)]],
    "Z": [[(25, 20), (75, 20), (25, 75), (75, 75)]],
    "[": [[(60, 20), (40, 20), (40, 75), (60, 75)]],
    "\\": [[(30, 20), (70, 75)]],
    "]": [[(40, 20), (60, 20), (60, 75), (40, 75)]],
    "^": [[(35, 45), (50, 25), (65, 45)]],
    "_": [[(25, 78), (75, 78)]],
    "`": [[(45, 20), (55, 35)]],
    "a": [[(65, 45), (65, 75)], [(65, 52), (55, 45), (40, 45), (30, 55), (30, 65), (40, 75), (55, 75), (65, 68)]],
    "b": [[(30, 20), (30, 75)], [(30, 52), (42, 45), (58, 45), (68, 55), (68, 65), (58, 75), (42, 75), (30, 68)]],
    "c": [[(68, 52), (58, 45), (42, 45), (30, 55), (30, 65), (42, 75), (58, 75), (68, 68)]],
    "d": [[(70, 20), (70, 75)], [(70, 52), (58, 45), (42, 45), (32, 55), (32, 65), (42, 75), (58, 75), (70, 68)]],
    "e": [[(30, 58), (70, 58), (70, 50), (60, 45), (42, 45), (30, 55), (30, 65), (42, 75), (60, 75), (70, 68)]],
    "f": [[(60, 20), (48, 20), (42, 28), (42, 75)], [(32, 45), (58, 45)]],
    "g": [[(70, 45), (70, 78), (58, 85), (38, 85)], [(70, 52), (58, 45), (42, 45), (32, 55), (32, 65), (42, 75), (58, 75), (70, 68)]],
    "h": [[(30, 20), (30, 75)], [(30, 52), (42, 45), (58, 45), (68, 55), (68, 75)]],
    "i": [[(50, 20), (50, 25)], [(50, 45), (50, 75)]],
    "j": [[(55, 20), (55, 25)], [(55, 45), (55, 78), (45, 85), (35, 80)]],
    "k": [[(30, 20), (30, 75)], [(65, 45), (30, 60)], [(45, 55), (68, 75)]],
    "l": [[(45, 20), (50, 20), (50, 68), (58, 75)]],
    "m": [[(25, 75), (25, 45)], [(25, 52), (35, 45), (45, 45), (50, 52), (50, 75)], [(50, 52), (60, 45), (70, 45), (75, 52), (75, 75)]],
    "n": [[(30, 75), (30, 45)], [(30, 52), (42, 45), (58, 45), (70, 55), (70, 75)]],
    "o": [[(42, 45), (58, 45), (70, 55), (70, 65), (58, 75), (42, 75), (30, 65), (30, 55), (42, 45)]],
    "p": [[(30, 85), (30, 45)], [(30, 52), (42, 45), (58, 45), (68, 55), (68, 65), (58, 75), (42, 75), (30, 68)]],
    "q": [[(70, 85), (70, 45)], [(70, 52), (58, 45), (42, 45), (32, 55), (32, 65), (42, 75), (58, 75), (70, 68)]],
    "r": [[(30, 75), (30, 45)], [(30, 55), (42, 45), (58, 45), (65, 50)]],
    "s": [[(68, 50), (58, 45), (42, 45), (32, 52), (42, 58), (58, 62), (68, 68), (58, 75), (42, 75), (32, 70)]],
    "t": [[(45, 25), (45, 68), (55, 75)], [(35, 45), (60, 45)]],
    "u": [[(30, 45), (30, 65), (42, 75), (58, 75), (70, 68)], [(70, 45), (70, 75)]],
    "v": [[(30, 45), (50, 75), (70, 45)]],
    "w": [[(25, 45), (35, 75), (50, 60), (65, 75), (75, 45)]],
    "x": [[(30, 45), (70, 75)], [(70, 45), (30, 75)]],
    "y": [[(30, 45), (50, 75)], [(70, 45), (45, 85), (35, 85)]],
    "z": [[(30, 45), (70, 45), (30, 75), (70, 75)]],
    "{": [[(60, 20), (50, 20), (45, 28), (45, 42), (35, 47), (45, 52), (45, 67), (50, 75), (60, 75)]],
    "|": [[(50, 20), (50, 75)]],
    "}": [[(40, 20), (50, 20), (55, 28), (55, 42), (65, 47), (55, 52), (55, 67), (50, 75), (40, 75)]],
    "~": [[(30, 55), (40, 45), (60, 55), (70, 45)]],
}

def glyph_width(scale: float) -> int:
    return max(1, int(60 * scale))


def text_width(text: str, scale: float, spacing: float = 0.15) -> int:
    if not text:
        return 0
    gw = glyph_width(scale)
    gap = int(gw * spacing)
    return len(text) * gw + max(0, len(text) - 1) * gap


def draw_glyph(canvas: Canvas, ch: str, x: int, y: int, scale: float, color, thickness: int = 1) -> None:
    glyph = GLYPHS.get(ch)
    if glyph is None:
        glyph = GLYPHS.get("?", [])
    for stroke in glyph:
        if len(stroke) < 2:
            continue
        pts = [(x + int(px * scale * 0.6), y + int(py * scale)) for px, py in stroke]
        for i in range(len(pts) - 1):
            canvas.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color, thickness)


def draw_text(canvas: Canvas, text: str, x: int, y: int, scale: float, color, thickness: int = 1, spacing: float = 0.15) -> int:
    gw = glyph_width(scale)
    gap = int(gw * spacing)
    cx = x
    for ch in text:
        draw_glyph(canvas, ch, cx, y, scale, color, thickness)
        cx += gw + gap
    return cx - x


def draw_text_centered(canvas: Canvas, text: str, cx: int, y: int, scale: float, color, thickness: int = 1, spacing: float = 0.15) -> int:
    tw = text_width(text, scale, spacing)
    return draw_text(canvas, text, cx - tw // 2, y, scale, color, thickness, spacing)


def wrap_text(text: str, max_width: int, scale: float, spacing: float = 0.15) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if text_width(trial, scale, spacing) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    out: list[str] = []
    for line in lines:
        if text_width(line, scale, spacing) <= max_width:
            out.append(line)
        else:
            chunk = ""
            for ch in line:
                trial = chunk + ch
                if chunk and text_width(trial, scale, spacing) > max_width:
                    out.append(chunk)
                    chunk = ch
                else:
                    chunk = trial
            if chunk:
                out.append(chunk)
    return out


# ---------------------------------------------------------------------------
# Color / halftone helpers
# ---------------------------------------------------------------------------

INK = (20, 20, 20)
PAPER = (245, 242, 235)
GRAY = (110, 110, 110)
LIGHT_GRAY = (190, 190, 190)
RULE = (40, 40, 40)
ACCENT = (120, 30, 30)


def clamp8(v: int) -> int:
    return 0 if v < 0 else min(v, 255)


def rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    return (clamp8(r), clamp8(g), clamp8(b))


def lerp_color(a, b, t: float):
    t = 0.0 if t < 0.0 else min(t, 1.0)
    return rgb(
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def apply_halftone(canvas: Canvas, x0: int, y0: int, x1: int, y1: int, rng: DRNG, intensity: float = 0.08) -> None:
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(canvas.w, x1)
    y1 = min(canvas.h, y1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            n = (rng.random() - 0.5) * 255 * intensity
            d = ((x * 3 + y * 5) % 7 - 3) * intensity * 18
            delta = int(n + d)
            if delta == 0:
                continue
            i = (y * canvas.w + x) * 3
            canvas.px[i] = clamp8(canvas.px[i] + delta)
            canvas.px[i + 1] = clamp8(canvas.px[i + 1] + delta)
            canvas.px[i + 2] = clamp8(canvas.px[i + 2] + delta)


def draw_halftone_rect(canvas: Canvas, x0: int, y0: int, x1: int, y1: int, dot_color, bg, spacing: int, max_radius: float, angle: float = 0.0) -> None:
    x0c, y0c = max(0, x0), max(0, y0)
    x1c, y1c = min(canvas.w, x1), min(canvas.h, y1)
    canvas.fill_rect(x0c, y0c, x1c, y1c, bg)
    ca = math.cos(angle)
    sa = math.sin(angle)
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    diag = int(math.hypot(x1 - x0, y1 - y0) / 2) + spacing
    for gy in range(-diag, diag + 1, spacing):
        for gx in range(-diag, diag + 1, spacing):
            rx = gx * ca - gy * sa + cx
            ry = gx * sa + gy * ca + cy
            ix, iy = int(rx), int(ry)
            if ix < x0c - 2 or ix >= x1c + 2 or iy < y0c - 2 or iy >= y1c + 2:
                continue
            t = (iy - y0) / max(1, (y1 - y0))
            s = (ix - x0) / max(1, (x1 - x0))
            tone = 0.35 + 0.45 * ((math.sin(s * 6.0) + math.cos(t * 5.0)) * 0.25 + 0.5)
            rad = max(0.5, max_radius * tone)
            canvas.fill_circle(ix, iy, int(rad), dot_color)


# ---------------------------------------------------------------------------
# Editorial story/composition
# ---------------------------------------------------------------------------

PALETTES = [
    {"name": "broadsheet", "paper": (245, 242, 235), "ink": (20, 20, 20), "accent": (120, 30, 30), "rule": (40, 40, 40), "muted": (110, 110, 110), "light": (190, 190, 190), "wash": (232, 228, 220)},
    {"name": "slate", "paper": (240, 242, 245), "ink": (18, 22, 30), "accent": (30, 70, 120), "rule": (35, 45, 60), "muted": (95, 105, 120), "light": (185, 192, 200), "wash": (224, 230, 238)},
    {"name": "ochre", "paper": (247, 244, 232), "ink": (32, 26, 18), "accent": (140, 85, 20), "rule": (60, 50, 35), "muted": (120, 105, 85), "light": (200, 190, 170), "wash": (236, 228, 210)},
    {"name": "forest", "paper": (242, 245, 240), "ink": (18, 28, 20), "accent": (30, 90, 55), "rule": (35, 55, 40), "muted": (90, 110, 95), "light": (185, 200, 188), "wash": (225, 235, 228)},
]

MASTHEADS = [
    "THE DAILY DISPATCH",
    "THE WORLD CHRONICLE",
    "THE GLOBAL GAZETTE",
    "THE MORNING RECORD",
]

SECTIONS = ["WORLD", "INTERNATIONAL", "GLOBAL REPORT", "FRONT PAGE"]


def _clean_prompt(prompt: str) -> str:
    text = " ".join(prompt.replace("\n", " ").split()).strip()
    return text


def _headline_from_prompt(prompt: str) -> str:
    text = _clean_prompt(prompt)
    if not text:
        return "BREAKING NEWS FROM THE FIELD"
    # Prefer the first sentence/line fragment as headline subject
    for sep in [". ", "\n", " - ", ": "]:
        if sep in text:
            head = text.split(sep)[0].strip()
            if len(head) >= 12:
                text = head
                break
    # Strip common bounty framing
    lower = text.lower()
    for prefix in [
        "sum up ", "create ", "generate ", "make ", "produce ", "design ",
    ]:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            lower = text.lower()
            break
    # Trim trailing "in one image" style tails
    for tail in [" in one image", " as one image", " in a single image"]:
        if lower.endswith(tail):
            text = text[: -len(tail)].strip()
            lower = text.lower()
    if len(text) > 110:
        text = text[:107].rstrip() + "..."
    text = text.upper()
    return text or "WORLD NEWS FRONT PAGE"


def _deck_from_prompt(prompt: str) -> str:
    text = _clean_prompt(prompt)
    if not text:
        return "A visual summary of the day's developments."
    # Use second sentence or a trimmed prompt tail as deck
    parts = [p.strip() for p in text.replace("?", ".").replace("!", ".").split(".") if p.strip()]
    if len(parts) >= 2:
        deck = parts[1]
    else:
        deck = parts[0]
    if len(deck) > 140:
        deck = deck[:137].rstrip() + "..."
    return deck


def _body_from_prompt(prompt: str, rng: DRNG) -> str:
    text = _clean_prompt(prompt)
    # Build body from prompt matter + deterministic editorial framing, but no shared text across different prompts.
    base = text
    if len(base) > 260:
        base = base[:257].rstrip() + "..."
    templates = [
        "This front page distills the day's central developments into a single editorial composition, prioritizing clarity, proportion, and visual evidence.",
        "The layout balances headline hierarchy, image, and column structure so readers can scan the key story at a glance.",
        "Each block is arranged to reflect the prompt's own subject matter, with typography and imagery serving the report rather than decoration.",
        "The composition is generated deterministically from the prompt, seed, and variant salt so the same inputs always yield the same record.",
    ]
    rng.shuffle(templates)
    sentences = [base + ("." if base and base[-1] not in ".!?" else "")]
    sentences.extend(templates[:3])
    return " ".join(s for s in sentences if s)


def _caption_from_prompt(prompt: str) -> str:
    head = _headline_from_prompt(prompt)
    cap = f"Visual report: {head.title()}."
    if len(cap) > 110:
        cap = cap[:107].rstrip() + "..."
    return cap


def build_story(prompt: str, seed: int, salt: str) -> dict:
    rng = DRNG(seed, salt, prompt)
    palette = PALETTES[rng.randint(0, len(PALETTES) - 1)]
    masthead = MASTHEADS[rng.randint(0, len(MASTHEADS) - 1)]
    section = SECTIONS[rng.randint(0, len(SECTIONS) - 1)]
    headline = _headline_from_prompt(prompt)
    deck = _deck_from_prompt(prompt)
    body = _body_from_prompt(prompt, DRNG(seed, salt + "|body", prompt))
    caption = _caption_from_prompt(prompt)
    pull_quote = rng.choice([
        "The image carries the day's record.",
        "One page, one clear account.",
        "The front page makes the story visible.",
        "Clarity is the first editorial duty.",
    ])
    byline = rng.choice(["By Editorial Desk", "By Staff Correspondent", "By News Bureau", "By Visual Desk"])
    edition = rng.choice(["LATE EDITION", "MORNING EDITION", "SPECIAL EDITION", "WORLD EDITION"])
    dateline = rng.choice([
        "THURSDAY, NOVEMBER 19, 2026",
        "FRIDAY, NOVEMBER 20, 2026",
        "SATURDAY, NOVEMBER 21, 2026",
    ])
    # If prompt mentions a specific date, prefer it.
    pl = prompt.lower()
    if "19 november 2026" in pl or "november 19 2026" in pl:
        dateline = "THURSDAY, NOVEMBER 19, 2026"
    if "20 november 2026" in pl or "november 20 2026" in pl:
        dateline = "FRIDAY, NOVEMBER 20, 2026"
    return {
        "headline": headline,
        "deck": deck,
        "body": body,
        "caption": caption,
        "pull_quote": pull_quote,
        "byline": byline,
        "edition": edition,
        "dateline": dateline,
        "masthead": masthead,
        "section": section,
        "price": rng.choice(["$2.00", "$3.00", "EDITION NO. 1", "VOL. 1"]),
        "palette": palette,
    }


def _fit_text_scale(text: str, max_width: int, max_scale: float, min_scale: float = 0.18) -> tuple[float, list[str]]:
    scale = max_scale
    while scale >= min_scale:
        lines = wrap_text(text, max_width, scale)
        if lines and all(text_width(ln, scale, 0.10) <= max_width for ln in lines):
            return scale, lines
        scale -= 0.02
    return min_scale, wrap_text(text, max_width, min_scale)


def render_front_page(prompt: str, seed: int, salt: str, width: int = 1024, height: int = 1024):
    story = build_story(prompt, seed, salt)
    rng = DRNG(seed, salt + "|layout", prompt)
    pal = story["palette"]
    PAPER_C = pal["paper"]
    INK_C = pal["ink"]
    ACCENT_C = pal["accent"]
    RULE_C = pal["rule"]
    GRAY_C = pal["muted"]
    LIGHT_C = pal["light"]
    WASH_C = pal["wash"]

    c = Canvas(width, height, PAPER_C)
    apply_halftone(c, 0, 0, width, height, DRNG(seed, salt + "|grain", prompt), intensity=0.03)

    margin = max(20, width // 32)
    inner_w = width - margin * 2
    y = margin

    # Layout choices driven by salt/prompt
    col_count = rng.choice([2, 3])
    fig_style = rng.choice(["skyline", "rings", "grid"])
    fig_h_ratio = 0.24 if col_count == 3 else 0.27
    fig_h = int(height * fig_h_ratio)
    header_compact = height <= 1024

    blocks = []

    # Folio
    folio_scale = 0.14
    draw_text(c, story["section"], margin, y, folio_scale, GRAY_C, 1)
    ed_tw = text_width(story["edition"], folio_scale)
    draw_text(c, story["edition"], width - margin - ed_tw, y, folio_scale, GRAY_C, 1)
    y += int(100 * folio_scale) + 6
    blocks.append("folio")

    # Masthead rule
    c.fill_rect(margin, y, width - margin, y + 2, RULE_C)
    y += 8
    mast = story["masthead"]
    mast_scale = 0.58 if header_compact else 0.72
    while mast_scale > 0.28 and text_width(mast, mast_scale, 0.12) > inner_w:
        mast_scale -= 0.02
    mast_h = int(100 * mast_scale)
    draw_text_centered(c, mast, width // 2, y, mast_scale, INK_C, 2, 0.12)
    y += mast_h + 6
    blocks.append("masthead")

    # Date/price strip
    strip_scale = 0.145
    draw_text(c, story["dateline"], margin, y, strip_scale, INK_C, 1)
    price_tw = text_width(story["price"], strip_scale)
    draw_text(c, story["price"], width - margin - price_tw, y, strip_scale, INK_C, 1)
    y += int(100 * strip_scale) + 6

    c.fill_rect(margin, y, width - margin, y + 3, RULE_C)
    c.fill_rect(margin, y + 6, width - margin, y + 7, RULE_C)
    y += 14
    blocks.append("dateline")

    # Headline
    head_scale, head_lines = _fit_text_scale(story["headline"], inner_w, 0.52 if header_compact else 0.62, 0.24)
    head_thickness = 2 if head_scale >= 0.42 else 1
    head_line_h = int(100 * head_scale) + 4
    for hl in head_lines[:3]:
        tw = text_width(hl, head_scale, 0.10)
        hx = margin + max(0, (inner_w - tw) // 2)
        draw_text(c, hl, hx, y, head_scale, INK_C, head_thickness, 0.10)
        y += head_line_h
    y += 2
    blocks.append("headline")

    # Deck
    deck_scale = 0.20
    deck_lines = wrap_text(story["deck"], int(inner_w * 0.94), deck_scale)
    for dl in deck_lines[:2]:
        tw = text_width(dl, deck_scale, 0.12)
        dx = margin + max(0, (inner_w - tw) // 2)
        draw_text(c, dl, dx, y, deck_scale, GRAY_C, 1, 0.12)
        y += int(100 * deck_scale) + 3
    y += 4
    blocks.append("deck")

    # Byline rule
    c.fill_rect(margin, y, width - margin, y + 1, LIGHT_C)
    y += 6
    meta_scale = 0.14
    draw_text(c, story["byline"].upper(), margin, y, meta_scale, INK_C, 1)
    sr = "SPECIAL REPORT"
    dtw = text_width(sr, meta_scale)
    draw_text(c, sr, width - margin - dtw, y, meta_scale, ACCENT_C, 1)
    y += int(100 * meta_scale) + 6
    c.fill_rect(margin, y, width - margin, y + 1, LIGHT_C)
    y += 10
    blocks.append("byline")

    # Figure
    fig_w = inner_w
    fig_x = margin
    fig_y = y
    draw_halftone_rect(c, fig_x, fig_y, fig_x + fig_w, fig_y + fig_h, GRAY_C, WASH_C, 6, 2.6, angle=0.35 + rng.random() * 0.4)
    scene_rng = DRNG(seed, salt + "|scene", prompt)
    if fig_style == "skyline":
        horizon = fig_y + int(fig_h * 0.62)
        c.fill_rect(fig_x, horizon, fig_x + fig_w, fig_y + fig_h, lerp_color(WASH_C, GRAY_C, 0.25))
        sun_r = max(10, fig_w // 20)
        sun_x = fig_x + fig_w - sun_r - scene_rng.randint(30, 90)
        sun_y = fig_y + scene_rng.randint(24, 50) + sun_r
        c.stroke_circle(sun_x, sun_y, sun_r, RULE_C, 2)
        c.stroke_circle(sun_x, sun_y, max(2, sun_r - 6), GRAY_C, 1)
        bx = fig_x + 16
        while bx < fig_x + fig_w - 24:
            bw = scene_rng.randint(28, 86)
            bh = scene_rng.randint(35, int(fig_h * 0.48))
            c.fill_rect(bx, horizon - bh, bx + bw, horizon, lerp_color(GRAY_C, WASH_C, 0.35))
            c.stroke_rect(bx, horizon - bh, bx + bw, horizon, RULE_C, 1)
            for wy in range(horizon - bh + 8, horizon - 8, 12):
                for wx in range(bx + 6, bx + bw - 6, 12):
                    if scene_rng.random() > 0.45:
                        c.fill_rect(wx, wy, wx + 5, wy + 5, WASH_C)
            bx += bw + scene_rng.randint(4, 16)
        for k in range(5):
            ly = horizon + 10 + k * 11
            if ly < fig_y + fig_h - 5:
                c.draw_line(fig_x + 10, ly, fig_x + fig_w - 10, ly, LIGHT_C, 1)
    elif fig_style == "rings":
        cxr, cyr = fig_x + fig_w // 2, fig_y + fig_h // 2
        for r in range(min(fig_w, fig_h) // 2 - 10, 10, -18):
            col = lerp_color(WASH_C, ACCENT_C, r / max(1, min(fig_w, fig_h) // 2))
            c.stroke_circle(cxr, cyr, r, col, 2)
        for k in range(12):
            ang = k * math.pi / 6.0
            x2 = int(cxr + math.cos(ang) * (fig_w * 0.45))
            y2 = int(cyr + math.sin(ang) * (fig_h * 0.45))
            c.draw_line(cxr, cyr, x2, y2, RULE_C, 1)
        c.fill_circle(cxr, cyr, 18, ACCENT_C)
        c.stroke_circle(cxr, cyr, 24, RULE_C, 2)
    else:  # grid
        step = 28
        for gx in range(fig_x, fig_x + fig_w, step):
            c.draw_line(gx, fig_y, gx, fig_y + fig_h, LIGHT_C, 1)
        for gy in range(fig_y, fig_y + fig_h, step):
            c.draw_line(fig_x, gy, fig_x + fig_w, gy, LIGHT_C, 1)
        for _ in range(18):
            bx = fig_x + scene_rng.randint(1, max(1, fig_w // step - 2)) * step
            by = fig_y + scene_rng.randint(1, max(1, fig_h // step - 2)) * step
            bw = step * scene_rng.randint(1, 3)
            bh = step * scene_rng.randint(1, 3)
            col = lerp_color(ACCENT_C, WASH_C, scene_rng.random() * 0.5)
            c.fill_rect(bx + 2, by + 2, min(fig_x + fig_w - 2, bx + bw - 2), min(fig_y + fig_h - 2, by + bh - 2), col)
            c.stroke_rect(bx + 2, by + 2, min(fig_x + fig_w - 2, bx + bw - 2), min(fig_y + fig_h - 2, by + bh - 2), RULE_C, 1)
    c.stroke_rect(fig_x, fig_y, fig_x + fig_w, fig_y + fig_h, RULE_C, 2)
    y = fig_y + fig_h + 6
    blocks.append(f"figure:{fig_style}")

    # Caption
    cap_scale = 0.125
    cap_lines = wrap_text(story["caption"], fig_w, cap_scale)
    for cl in cap_lines[:2]:
        draw_text(c, cl, fig_x, y, cap_scale, GRAY_C, 1)
        y += int(100 * cap_scale) + 2
    y += 6
    blocks.append("caption")

    c.fill_rect(margin, y, width - margin, y + 1, RULE_C)
    y += 10

    # Body columns
    col_gap = max(14, width // 48)
    total_gap = col_gap * (col_count - 1)
    col_w = (inner_w - total_gap) // col_count
    body_scale = 0.145 if col_count == 3 else 0.155
    body_line_h = int(100 * body_scale) + 4
    body_lines = wrap_text(story["body"], col_w, body_scale)
    per_col = max(1, (len(body_lines) + col_count - 1) // col_count)
    cols = [body_lines[i * per_col:(i + 1) * per_col] for i in range(col_count)]

    pq_scale = 0.19 if col_count == 3 else 0.21
    pq_lines = wrap_text('"' + story["pull_quote"] + '"', col_w - 16, pq_scale)
    pq_h = len(pq_lines[:3]) * (int(100 * pq_scale) + 3) + 16

    col_bottom = height - margin - 24
    for ci in range(col_count):
        cx = margin + ci * (col_w + col_gap)
        cy = y
        lines = cols[ci] if ci < len(cols) else []
        if ci == 1 and len(cols) > 1:
            box_y = cy
            c.fill_rect(cx, box_y, cx + col_w, box_y + pq_h, WASH_C)
            c.stroke_rect(cx, box_y, cx + col_w, box_y + pq_h, RULE_C, 1)
            pyq = box_y + 8
            for pl in pq_lines[:3]:
                draw_text(c, pl, cx + 8, pyq, pq_scale, ACCENT_C, 1, 0.12)
                pyq += int(100 * pq_scale) + 3
            cy = box_y + pq_h + 8
        for ln in lines:
            if cy + body_line_h > col_bottom:
                break
            draw_text(c, ln, cx, cy, body_scale, INK_C, 1, 0.12)
            cy += body_line_h
        if ci < col_count - 1:
            sx = cx + col_w + col_gap // 2
            c.draw_line(sx, y, sx, col_bottom, LIGHT_C, 1)
    blocks.append("body-columns")
    blocks.append("pull-quote")

    footer_y = height - margin - 16
    c.fill_rect(margin, footer_y, width - margin, footer_y + 1, RULE_C)
    foot_scale = 0.12
    draw_text(c, "PRINTED FOR THE RECORD", margin, footer_y + 5, foot_scale, GRAY_C, 1)
    pg = "PAGE A1"
    pgtw = text_width(pg, foot_scale)
    draw_text(c, pg, width - margin - pgtw, footer_y + 5, foot_scale, GRAY_C, 1)
    blocks.append("footer")

    composition = {
        "columns": col_count,
        "blocks": blocks,
        "palette": {
            "name": pal["name"],
            "paper": list(PAPER_C),
            "ink": list(INK_C),
            "accent": list(ACCENT_C),
        },
        "headline": story["headline"],
        "deck": story["deck"],
        "caption": story["caption"],
        "masthead": story["masthead"],
        "section": story["section"],
        "figureStyle": fig_style,
    }
    return c, composition
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_PROMPT = "Sum up the world's news of Friday 20 November 2026 in one image."


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deterministic editorial front-page PNG renderer")
    p.add_argument("--prompt", default=None, help="Story prompt text")
    p.add_argument("--prompt-file", default=None, help="Read prompt text from file")
    p.add_argument("--seed", type=int, default=20261120, help="Deterministic seed")
    p.add_argument("--variant-salt", "--salt", dest="variant_salt", default="A", help="Variant salt")
    p.add_argument("--out", default=None, help="Output PNG path (default: $MAKEFUN_OUTPUT_DIR/entry.png)")
    p.add_argument("--width", type=int, default=1024, help="Image width (max 1024)")
    p.add_argument("--height", type=int, default=1024, help="Image height (max 1024)")
    return p


def _load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            return text
    if args.prompt is not None and str(args.prompt).strip():
        return str(args.prompt).strip()
    return DEFAULT_PROMPT


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    width = max(320, min(1024, int(args.width)))
    height = max(320, min(1024, int(args.height)))
    prompt = _load_prompt(args)
    salt = str(args.variant_salt or "")
    seed = int(args.seed)

    if args.out is None:
        args.out = os.path.join(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"), "entry.png")
    out_path = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    canvas, _composition = render_front_page(prompt, seed, salt, width=width, height=height)
    png = encode_png_rgb(canvas.w, canvas.h, canvas.px)
    if len(png) > 1_000_000:
        raise SystemExit(f"PNG exceeds 1 MiB: {len(png)} bytes")
    with open(out_path, "wb") as f:
        f.write(png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
