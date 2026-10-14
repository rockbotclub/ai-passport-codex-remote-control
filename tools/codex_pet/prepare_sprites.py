#!/usr/bin/env python3
"""Convert a locally supplied Codex v2 sheet into Flash-resident LVGL RGB565 frames."""
import argparse
import io
import json
import struct
from pathlib import Path
from PIL import Image

ROWS = [(0, 6), (7, 6), (6, 6), (4, 5), (5, 8)]
WIDTH, HEIGHT = 144, 156
BACKGROUND = (16, 24, 38)

def from_asar(path):
    with path.open('rb') as f:
        header = struct.unpack('<4I', f.read(16))
        tree = json.loads(f.read(header[3]))
        assets = tree['files']['webview']['files']['assets']['files']
        matches = [v for k, v in assets.items() if k.startswith('codex-spritesheet-v6-') and k.endswith('.webp')]
        if len(matches) != 1:
            raise ValueError('Expected exactly one Codex v6 sheet; supply --sheet for another app version.')
        entry = matches[0]
        f.seek(8 + header[1] + int(entry['offset']))
        return f.read(entry['size'])

def offline_bitmap(font=None):
    from dashboard import DashboardRenderer, EMPTY_LABELS, SUMMARY_SIZE, LIST_SIZE
    from interaction import Renderer
    renderer = Renderer(font)
    for text, _ in EMPTY_LABELS['offline']:
        if any(ord(c) not in renderer.coverage for c in text):
            raise ValueError('Offline labels require a CJK font; supply --font.')
    frame = DashboardRenderer(renderer).frame({'status': 'offline', 'active': 0,
                                             'waiting': 0, 'remaining': 0, 'rows': []})
    start = 8 + SUMMARY_SIZE[0] * SUMMARY_SIZE[1] // 8
    return frame[start:start + LIST_SIZE[0] * LIST_SIZE[1] // 8]


def generate(blob, destination, font=None):
    offline = offline_bitmap(font)
    sheet = Image.open(io.BytesIO(blob)).convert('RGBA')
    if sheet.size != (1536, 2288):
        raise ValueError('Expected the Codex v2 8-column / 11-row, 192x208-cell sheet.')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'source.webp').write_bytes(blob)
    with (destination / 'frames.inc').open('w') as out:
        out.write('// Locally imported Codex artwork. Do not redistribute without permission.\n')
        for row, count in ROWS:
            for column in range(count):
                image = sheet.crop((column*192, row*208, (column+1)*192, (row+1)*208))
                image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
                frame = Image.new('RGB', image.size, BACKGROUND)
                frame.paste(image, mask=image.getchannel('A'))
                pixels = bytearray()
                for r, g, b in frame.getdata():
                    pixels.extend(struct.pack('<H', (r >> 3) << 11 | (g >> 2) << 5 | b >> 3))
                name = f'pet_{row}_{column}'
                out.write(f'static const uint8_t {name}_data[] = {{\n')
                for start in range(0, len(pixels), 32):
                    out.write(','.join(f'0x{x:02x}' for x in pixels[start:start+32]) + ',\n')
                out.write('};\n')
                out.write(f'static const lv_image_dsc_t {name} = {{.header = {{.magic = LV_IMAGE_HEADER_MAGIC, .cf = LV_COLOR_FORMAT_RGB565, .w = {WIDTH}, .h = {HEIGHT}, .stride = {WIDTH*2}}}, .data_size = sizeof({name}_data), .data = {name}_data}};\n')
        for row, count in ROWS:
            out.write(f'static const lv_image_dsc_t *const row_{row}[] = {{' + ','.join(f'&pet_{row}_{c}' for c in range(count)) + '};\n')
    with (destination / 'offline.inc').open('w') as out:
        out.write('// Locally rendered CJK labels. Do not redistribute without permission.\n')
        out.write('static const uint8_t pet_offline_pixels[] = {\n')
        for start in range(0, len(offline), 32):
            out.write(','.join(f'0x{x:02x}' for x in offline[start:start+32]) + ',\n')
        out.write('};\n')
    print(f'Generated 31 frames and {len(offline)} offline-label bytes in {destination}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--asar', type=Path)
    source.add_argument('--sheet', type=Path)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[2] / 'assets/images/codex-pet')
    parser.add_argument('--font', type=Path, help='Local CJK font for offline labels (defaults to macOS Arial Unicode)')
    args = parser.parse_args()
    generate(from_asar(args.asar) if args.asar else args.sheet.read_bytes(), args.out, args.font)
