# The Global Daily Dispatch — Friday, 20 November 2026

[![make.fun bounty](https://img.shields.io/badge/make.fun-news--image--20261120-14181F?style=flat-square)](https://make.fun/bounty/news-image-20261120)
[![Python 3.13](https://img.shields.io/badge/python-3.13%20stdlib-2B4C7E?style=flat-square)](https://make.fun/bounty/news-image-20261120)
[![License: MIT](https://img.shields.io/badge/license-MIT-8B261D?style=flat-square)](https://make.fun/bounty/news-image-20261120)

Archival `1024×1024` editorial broadsheet (`entry.png`) and deterministic Python 3.13 CLI (`main.py`) covering six global stories from **Friday, 20 November 2026**:

- **Europe · Security:** Russian Kh-101 cruise missile strikes a field near Nowy Lipowiec, Poland.
- **Middle East · Energy:** Commercial oil tanker ablaze off Khasab in the Strait of Hormuz; coalition strikes in Yemen.
- **Global Climate · COP31:** Antalya climate talks deadlocked over fossil-fuel phase-out language.
- **Americas · Markets & AI:** S&P 500 and Dow enter 10% correction; claimed Claude-assisted Riemann proof (unverified).
- **Africa · Disaster:** Vessel capsizing in Bayelsa State, Nigeria leaves at least 30 dead and ~300 missing.
- **Global Culture · Record:** *GTA 6* reaches $3.8bn in first-day sales with 32.5m pre-sold copies.

## Usage

```bash
python3 main.py --out /tmp/entry.png
```

When `--out` is omitted, `main.py` writes to `$MAKEFUN_OUTPUT_DIR/entry.png` or `/output/entry.png`, validating PNG signature, `IHDR` dimensions (`<= 1024×1024`), chunk CRC32 checksums, `IEND` termination, and payload size (`<= 1 MiB`).

## Verification

```bash
python3 -m unittest discover -s tests -v
```
