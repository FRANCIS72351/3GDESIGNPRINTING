#!/usr/bin/env python3
"""Copy Ethnocentric into static/fonts/ if installed on this machine."""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(ROOT, 'static', 'fonts')
TARGETS = (
    os.path.join(FONTS_DIR, 'Ethnocentric.otf'),
    os.path.join(FONTS_DIR, 'Ethnocentric.ttf'),
)
SEARCH_DIRS = [
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
    FONTS_DIR,
]
NAMES = (
    'Ethnocentric.otf',
    'Ethnocentric.ttf',
    'ethnocentric.ttf',
    'Ethnocentric-Regular.otf',
    'Ethnocentric Reg.ttf',
    'EthnocentricRg.ttf',
)


def _copy(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    print(f'Installed: {dest}')


def main():
    os.makedirs(FONTS_DIR, exist_ok=True)
    if os.path.isfile(TARGETS[0]) or os.path.isfile(TARGETS[1]):
        print('Ethnocentric already present in static/fonts/.')
        return 0

    for folder in SEARCH_DIRS:
        if not folder or not os.path.isdir(folder):
            continue
        for name in NAMES:
            src = os.path.join(folder, name)
            if not os.path.isfile(src):
                continue
            ext = os.path.splitext(name)[1].lower()
            dest = TARGETS[0] if ext == '.otf' else TARGETS[1]
            _copy(src, dest)
            return 0
        for entry in os.listdir(folder):
            lower = entry.lower()
            if 'ethnocentric' in lower and lower.endswith(('.ttf', '.otf')):
                src = os.path.join(folder, entry)
                dest = TARGETS[0] if lower.endswith('.otf') else TARGETS[1]
                _copy(src, dest)
                return 0

    print('Ethnocentric not found. Place Ethnocentric.otf in static/fonts/ and restart.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
