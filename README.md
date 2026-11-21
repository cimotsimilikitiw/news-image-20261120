[![make.fun · news-image-20261120](https://make.fun/badge/news-image-20261120.svg)](https://make.fun/bounty/news-image-20261120?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)
[![rank](https://make.fun/badge/news-image-20261120/cimotsimilikitiw/news-image-20261120/rank.svg)](https://make.fun/bounty/news-image-20261120/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)
[![reward](https://make.fun/badge/news-image-20261120/cimotsimilikitiw/news-image-20261120/reward.svg)](https://make.fun/bounty/news-image-20261120?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)

# The Global Daily Dispatch — Friday, 20 November 2026

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
