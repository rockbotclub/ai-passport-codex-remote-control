<p align="right">
  <a href="README.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# Assets

This directory stores reusable fonts, images, music, and sound effects, organized by asset type.

Keep each asset in the matching subdirectory and document its destination, naming, integration method, and source/license. Do not mix binary assets with Markdown documentation.

## Fonts

Store reusable font files and generated font sources in `fonts/`.

- Use descriptive names that include the family, weight, size, and format when relevant.
- Document the source, license, character range, conversion command, and expected destination.
- Check Flash and internal-RAM impact before adding a font; the ESP32-C3 has no PSRAM.
- Do not commit fonts whose license does not permit redistribution.

The Codex pet uses `fonts/PassportSans-Regular.otf`, a renamed subset of
[Noto Sans CJK SC Regular](https://github.com/notofonts/noto-cjk/tree/main/Sans/OTF/SimplifiedChinese)
under [SIL OFL 1.1](fonts/OFL-NotoSansCJK.txt). The original downloaded OTF SHA-256
is `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`.
The subset retains upstream copyright metadata and is renamed Passport Sans.
`fonts/passport-ui-glyphs.txt` records printable ASCII and the fixed firmware
Chinese inventory. FontTools 4.66.1 was used to subset the source. Generated
`fonts/passport_font_12.c`, `passport_font_14.c`, and `passport_font_20.c` are
LVGL 9.5-compatible, 2-bpp, uncompressed Flash assets, compiled by `main` and
explicitly selected by every local text widget in `main/pet_ui.c`.
Each size contains 265 glyphs. The verified map records 42,072 read-only font
bytes in total (9,537 / 11,866 / 20,669 bytes respectively), with no `.data` or
`.bss` contributed by these font objects.

Regenerate each size with `lv_font_conv` 1.5.3 (replace both occurrences of 12
with 14 or 20 for the other sizes):

```bash
npx --yes lv_font_conv@1.5.3 --font assets/fonts/PassportSans-Regular.otf \
  --symbols "$(cat assets/fonts/passport-ui-glyphs.txt)" --size 12 --bpp 2 \
  --format lvgl --no-compress --no-kerning --lv-include lvgl.h \
  --lv-font-name passport_font_12 \
  -o assets/fonts/passport_font_12.c
```

When adding characters, extend the inventory and regenerate the OTF subset from
the upstream font if necessary, then regenerate all sizes. This subset is for
fixed local text; arbitrary project names and approval content are rendered on
the computer. `tools/codex_pet/ui_glyphs.py` records the separate fixed desktop
message inventory, checked against its Python sources by the localization test.
Regenerate it with `python3 tools/codex_pet/update_ui_glyphs.py` after editing
messages. These fonts do not require a larger LVGL heap; runtime heap and
largest-block measurements remain device checks.

## Images

Store reusable source images and generated display assets in `images/`.

| File | Dimensions and format | Use and source |
| --- | --- | --- |
| [`images/home.jpg`](images/home.jpg) | 3840 × 2160, JPEG | Product hero image embedded in both project README files to foreground AI Passport and its open, maker-oriented identity. |
| [`images/readme-hardware-specs.png`](images/readme-hardware-specs.png) | 2172 × 724, PNG RGBA | Optional technical infographic retained as a reference asset; it is no longer used as the homepage hero. Generated for this repository with the built-in image generation tool on 2026-09-17; the six labels and values were checked against the documented hardware contract. |
| [`images/logo-wordmark.png`](images/logo-wordmark.png) | 1648 × 336, PNG RGBA | Transparent black wordmark extracted from the repository's original `images/logo.png`; embedded in both project README files for light backgrounds. |
| [`images/logo-wordmark-dark.png`](images/logo-wordmark-dark.png) | 1648 × 336, PNG RGBA | White version of the extracted wordmark, used by the README `<picture>` element when GitHub is in dark mode. |

- Use descriptive names and document dimensions, pixel format, conversion steps, and destination.
- Prefer formats suitable for the 240 × 320 RGB565 display and account for Flash and internal RAM.
- Preserve editable sources where licensing permits, and record the source and license.
- Never commit device QR secrets, credentials, or personal data in images.

## Music and sound effects

Store reusable music and sound-effect sources in `music/`.

- Document the source, license, sample rate, bit depth, channels, conversion command, and destination.
- Prefer 16 kHz, 16-bit mono PCM when it matches the current BSP audio path.
- Check Flash and internal-RAM cost before embedding audio; stream or chunk long recordings.
- Do not commit media without redistribution permission.

## Local Codex pet artwork

`images/codex-pet/source.webp` and `frames.inc` are imported from the user’s Codex installation by `tools/codex_pet/prepare_sprites.py`. The 31 RGB565 frames are 144 × 156 pixels and embedded directly in Flash. These files are Git-ignored; redistribution permission is not established. See [the application guide](../docs/codex-pet.md).

The same importer generates `images/codex-pet/offline.inc`: a 216 × 144 one-bit
bitmap containing the Chinese equivalents of “PC disconnected” and “Check the
PC bridge” at 16/12 pixels,
using local Arial Unicode or the explicitly supplied `--font`. Glyph coverage
is checked before generation. It uses 3,888 Flash bytes and the existing UI list
buffer. This font-derived asset is also Git-ignored; font and artwork
redistribution permission is not established.

The importer also generates `images/codex-pet/syncing.inc` with the Chinese
syncing-task heading and PC-state-reading subtitle, using the same verified font,
16/12-pixel sizes, 216 × 144 bitmap and existing list buffer. It adds 3,888 Flash
bytes, so the syncing message is available before the first encrypted overview.
This asset is also Git-ignored with the same redistribution restrictions.
