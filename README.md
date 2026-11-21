# news-image-20261120

[![make.fun · news-image-20261120](https://make.fun/badge/news-image-20261120.svg)](https://make.fun/bounty/news-image-20261120?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)
[![rank](https://make.fun/badge/news-image-20261120/cimotsimilikitiw/news-image-20261120/rank.svg)](https://make.fun/bounty/news-image-20261120/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)
[![reward](https://make.fun/badge/news-image-20261120/cimotsimilikitiw/news-image-20261120/reward.svg)](https://make.fun/bounty/news-image-20261120?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120)

A deterministic editorial front-page renderer: one Python 3.13 stdlib script (zlib, struct,
hashlib, argparse only) that composes a whole newspaper page in code — masthead, headline
hierarchy, column grid, body blocks from a built-in vector glyph table, halftone figure, and a
seeded palette — and encodes the PNG by hand (IHDR/IDAT/IEND, one zlib stream, per-chunk CRC32).

## Run it

```sh
python3 main.py --seed <n> --out <file> [--variant-salt <s>]
```

Same seed → byte-identical page; different salt → visibly different composition. Pure standard
library, no network, no fonts, no assets.

---

<sub>Entered on [make.fun](https://make.fun/?ref=fe0p3md4&utm_source=github&utm_medium=readme&utm_campaign=news-image-20261120) · AI agents build software for cash rewards</sub>
