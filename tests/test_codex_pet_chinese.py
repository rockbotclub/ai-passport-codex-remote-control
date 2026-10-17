"""Chinese prompts, native failure reasons, font coverage and screen bounds."""
import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/codex_pet'))
from messages import ChineseArgumentParser, REASONS, reason_text, system_error
from ui_glyphs import REQUIRED_GLYPHS


class ChineseMessagesTests(unittest.TestCase):
    def test_all_native_error_codes_have_chinese_descriptions(self):
        from doubao_dictation import REASONS as native_reasons, DoubaoError
        from interaction import ComposerActionError
        source = ast.parse((ROOT / 'tools/codex_pet/interaction.py').read_text())
        codes = set(native_reasons.values())
        for node in ast.walk(source):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'reasons' for t in node.targets):
                codes.update(ast.literal_eval(node.value).values())
        self.assertFalse(codes - REASONS.keys())
        for code in codes:
            for error in (ComposerActionError(code), DoubaoError(code)):
                self.assertEqual(error.reason, code)
                self.assertIn(reason_text(code), str(error))
                self.assertNotIn(code, str(error))

    def test_argparse_help_and_failures_are_chinese(self):
        for args, expected in ((['--help'], '显示帮助信息'), ([], '缺少必需参数'),
                               (['--choice', 'wrong'], '无效选项'),
                               (['--choice'], '需要一个参数值'),
                               (['--choice', 'yes', '--unknown'], '无法识别的参数')):
            with self.subTest(args=args):
                parser = ChineseArgumentParser(prog='bridge')
                parser.add_argument('--choice', choices=['yes', 'no'], required=True)
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output), self.assertRaises(SystemExit):
                    parser.parse_args(args)
                self.assertIn(expected, output.getvalue())
                self.assertNotIn('usage:', output.getvalue())
                self.assertNotIn('error:', output.getvalue())

        parser = ChineseArgumentParser(prog='bridge')
        sub = parser.add_subparsers(dest='command', required=True)
        run = sub.add_parser('run')
        run.add_argument('--host', required=True)
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit):
            parser.parse_args(['run'])
        self.assertIn('用法：bridge run', output.getvalue())
        self.assertNotIn('用法：用法：', output.getvalue())

    def test_os_diagnostics_do_not_leak_untranslated_private_text(self):
        text = system_error(OSError(13, 'Permission denied: /private/user-file'))
        self.assertEqual(text, '权限不足')
        self.assertNotIn('/private', text)
        self.assertRegex(system_error(RuntimeError('unknown external message')), r'[\u4e00-\u9fff]')

    def test_malformed_pairing_files_show_chinese_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'pairing.json'
            for value in ([], {}, {'host': '127.0.0.1', 'key': 123}):
                with self.subTest(value=value):
                    config.write_text(json.dumps(value))
                    result = subprocess.run([sys.executable, str(ROOT / 'tools/codex_pet/bridge.py'),
                                             'run', '--config', str(config)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('请重新配对', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_python_inventory_covers_every_fixed_chinese_message(self):
        for path in (ROOT / 'tools/codex_pet').glob('*.py'):
            if path.name == 'ui_glyphs.py':
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    required = {ord(c) for c in node.value if ord(c) > 127 and not c.isspace()}
                    self.assertFalse(required - REQUIRED_GLYPHS, f'{path.name}: {required - REQUIRED_GLYPHS}')

    def test_firmware_font_cmaps_and_widget_bindings(self):
        inventory = set(map(ord, (ROOT / 'assets/fonts/passport-ui-glyphs.txt').read_text().strip('\n')))
        ui = (ROOT / 'main/pet_ui.c').read_text()
        self.assertNotIn('&lv_font_montserrat_', ui)
        # These strings draw locally; logs and static build diagnostics do not.
        for line in ui.splitlines():
            if 'ESP_LOG' in line or '_Static_assert' in line:
                continue
            for literal in re.findall(r'"(?:[^"\\]|\\.)*"', line):
                value = ast.literal_eval(literal)
                self.assertFalse({ord(c) for c in value if ord(c) > 127} - inventory)
        for size in (12, 14, 20):
            source = (ROOT / f'assets/fonts/passport_font_{size}.c').read_text()
            coverage = set()
            for start, length, glyph, list_name in re.findall(
                    r'\.range_start = (\d+), \.range_length = (\d+), \.glyph_id_start = (\d+),\s*\.unicode_list = (\w+)', source):
                start, length, glyph = int(start), int(length), int(glyph)
                self.assertGreater(glyph, 0)  # Glyph zero is the missing-glyph sentinel.
                if list_name == 'NULL':
                    coverage.update(range(start, start + length))
                else:
                    body = re.search(rf'{list_name}\[\] = \{{(.*?)\}};', source, re.S)[1]
                    offsets = [int(value, 16) for value in re.findall(r'0x[0-9a-f]+', body)]
                    self.assertTrue(all(offset < length for offset in offsets))
                    coverage.update(start + offset for offset in offsets)
            self.assertTrue(inventory <= coverage, size)
            self.assertNotIn(0x10ffff, coverage)
            self.assertIn('.bitmap_format = 0', source)
            self.assertIn('.fallback = NULL', source)

    def test_error_pages_and_device_footer_widths(self):
        try:
            from PIL import ImageFont
            from interaction import Renderer, UnsupportedText
        except ImportError:
            self.skipTest('Pillow/fontTools not installed')
        try:
            renderer = Renderer()
        except OSError:
            self.skipTest('Requires the local desktop CJK font')
        with self.assertRaisesRegex(ValueError, '字体缺少中文'):
            Renderer('/System/Library/Fonts/Supplemental/Arial.ttf')
        with self.assertRaises(UnsupportedText):
            renderer.pages('\U0010ffff')
        source = ast.parse((ROOT / 'tools/codex_pet/interaction.py').read_text())
        review = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'Review')
        for node in ast.walk(review):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r'[\u4e00-\u9fff]', node.value):
                self.assertEqual(len(renderer.pages(node.value)), 1, node.value)
        font = ImageFont.truetype(str(ROOT / 'assets/fonts/PassportSans-Regular.otf'), 12)
        ui = (ROOT / 'main/pet_ui.c').read_text().split('const char *footers[13] = {')[1].split('};')[0]
        for literal in re.findall(r'"(?:[^"\\]|\\.)*"', ui):
            for line in ast.literal_eval(literal).splitlines():
                self.assertLessEqual(font.getlength(line), 216, line)


if __name__ == '__main__':
    unittest.main()
