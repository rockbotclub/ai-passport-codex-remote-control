#!/usr/bin/env python3
"""Convert a locally supplied Codex v2 sheet into Flash-resident LVGL RGB565 frames."""
from messages import ChineseArgumentParser, system_error
import io
import json
import struct
from pathlib import Path
import sys

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
            raise ValueError('应找到一张 Codex v6 精灵图；其他应用版本请使用 --sheet 指定图片。')
        entry = matches[0]
        f.seek(8 + header[1] + int(entry['offset']))
        return f.read(entry['size'])

def status_bitmap(status, font=None):
    from dashboard import DashboardRenderer, EMPTY_LABELS, SUMMARY_SIZE, LIST_SIZE
    from interaction import Renderer
    renderer = Renderer(font)
    for text, _ in EMPTY_LABELS[status]:
        if any(ord(c) not in renderer.coverage for c in text):
            raise ValueError('状态提示需要支持中文的字体，请使用 --font 指定字体。')
    frame = DashboardRenderer(renderer).frame({'status': status, 'active': 0,
                                             'waiting': 0, 'remaining': 0, 'rows': []})
    start = 8 + SUMMARY_SIZE[0] * SUMMARY_SIZE[1] // 8
    return frame[start:start + LIST_SIZE[0] * LIST_SIZE[1] // 8]


def offline_bitmap(font=None):
    return status_bitmap('offline', font)


def generate(blob, destination, font=None):
    from PIL import Image
    labels = {status: status_bitmap(status, font) for status in ('offline', 'syncing')}
    sheet = Image.open(io.BytesIO(blob)).convert('RGBA')
    if sheet.size != (1536, 2288):
        raise ValueError('需要 Codex v2 精灵图：8 列、11 行，每格 192×208 像素。')
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
    for status, pixels in labels.items():
        with (destination / (status + '.inc')).open('w') as out:
            out.write('// Locally rendered CJK labels. Do not redistribute without permission.\n')
            out.write(f'static const uint8_t pet_{status}_pixels[] = {{\n')
            for start in range(0, len(pixels), 32):
                out.write(','.join(f'0x{x:02x}' for x in pixels[start:start+32]) + ',\n')
            out.write('};\n')
    print(f'已在 {destination} 生成 31 帧动画及 {sum(map(len, labels.values()))} 字节的状态提示位图')

def main():
    parser = ChineseArgumentParser(description='将本地 Codex 宠物精灵图转换为设备动画和中文状态提示。')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--asar', type=Path)
    source.add_argument('--sheet', type=Path)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[2] / 'assets/images/codex-pet')
    parser.add_argument('--font', type=Path, help='离线提示使用的本地中文字体（默认使用 macOS Arial Unicode）')
    args = parser.parse_args()
    generate(from_asar(args.asar) if args.asar else args.sheet.read_bytes(), args.out, args.font)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('操作已取消。', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, ImportError, KeyError, TypeError) as error:
        print(f'素材生成失败：{system_error(error)}。', file=sys.stderr)
        sys.exit(1)
