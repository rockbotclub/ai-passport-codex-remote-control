"""Regenerate the fixed desktop prompt inventory after editing Python messages."""
import ast
from pathlib import Path


def update():
    directory = Path(__file__).resolve().parent
    required = set()
    for path in sorted(directory.glob('*.py')):
        if path.name == 'ui_glyphs.py':
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                required.update(c for c in node.value if ord(c) > 127 and not c.isspace())
    characters = ''.join(sorted(required))
    (directory / 'ui_glyphs.py').write_text(
        '"""Required fixed Chinese prompt characters; checked by the localization tests."""\n'
        f'REQUIRED_GLYPHS = frozenset(map(ord, {characters!r}))\n')


if __name__ == '__main__':
    update()
