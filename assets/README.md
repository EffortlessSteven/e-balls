# Bundled font

`Aileron-Regular.ttf` is Pillow 12.3.0's embedded, limited-character-set
Aileron Regular font, extracted without further modification from
[`PIL.ImageFont.load_default()`](https://github.com/python-pillow/Pillow/blob/12.3.0/src/PIL/ImageFont.py#L1089).
It keeps text identical to the original prototype renderer.

Aileron is by **Sora Sagano** (dotcolon). The author's
[Aileron page](https://dotcolon.net/fonts/aileron) identifies its license as
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
The bundled font's name table identifies Sora Sagano as designer/manufacturer,
version `1.102`, and copyright text `No Rights Reserved.`

The complete CC0 legal text is in [Aileron-LICENSE.txt](Aileron-LICENSE.txt),
copied from the [Creative Commons legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt).
Pillow's separate license is retained in [Pillow-LICENSE.txt](Pillow-LICENSE.txt).

Provenance checked on 2026-09-20: the 12,676-byte file matches Pillow 12.3.0's
embedded font bytes exactly. SHA-256:
`69853909b940023570964e29cffe30da95aea8de3627736b5cd15ab30143169f`.

## e-balls typography and logo

The explicit e-balls theme bundles unmodified **IBM Plex Sans Regular** for
primary text and **IBM Plex Mono Regular** for dates, counts, and metadata.
Both are from the official [IBM/plex](https://github.com/IBM/plex) repository,
revision `763c36ef9117782905ae010056dfbe8fd2653a25`, under SIL OFL 1.1.
The upstream legacy theme retains its original font selection.

Exact download URLs and SHA-256 hashes for the fonts and licenses are recorded
in [plex-manifest.json](plex-manifest.json). Licenses are retained separately in
[IBMPlexSans-LICENSE.txt](IBMPlexSans-LICENSE.txt) and
[IBMPlexMono-LICENSE.txt](IBMPlexMono-LICENSE.txt).

The lowercase `e` in `logo.svg` is the Sans Regular `e` glyph converted to an
SVG path using fontTools 4.66.1. Its ink bounds are scaled to 76 units high,
flipped from font coordinates and centered at (150, 128). No SVG text or font
embedding is used. Palette: teal `#156b76`, cream `#f5f1e8`.
Font files belong in these source assets, never in example/evidence archives.
