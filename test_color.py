#!/usr/bin/env python3
"""
Test script for extended color support in FixedHistoryScreen.

Run this standalone to verify 256-color and true color parsing works
before integrating into VelociTermQt.
"""

import sys

# Minimal imports to test just the color parsing
try:
    import pyte
    from pyte.screens import Char
except ImportError:
    print("ERROR: pyte not installed. Run: pip install pyte")
    sys.exit(1)


class FixedHistoryScreen(pyte.HistoryScreen):
    """Test version of the patched screen."""

    def select_graphic_rendition(self, *attrs, **kwargs):
        kwargs.pop('private', None)
        attrs = list(attrs)
        i = 0

        while i < len(attrs):
            attr = attrs[i]

            # 256 color foreground: 38;5;N
            if attr == 38 and i + 2 < len(attrs) and attrs[i + 1] == 5:
                color_idx = attrs[i + 2]
                if 0 <= color_idx <= 255:
                    self._set_fg_color(color_idx)
                i += 3
                continue

            # 256 color background: 48;5;N
            if attr == 48 and i + 2 < len(attrs) and attrs[i + 1] == 5:
                color_idx = attrs[i + 2]
                if 0 <= color_idx <= 255:
                    self._set_bg_color(color_idx)
                i += 3
                continue

            # True color foreground: 38;2;R;G;B
            if attr == 38 and i + 4 < len(attrs) and attrs[i + 1] == 2:
                r, g, b = attrs[i + 2], attrs[i + 3], attrs[i + 4]
                if all(0 <= c <= 255 for c in (r, g, b)):
                    self._set_fg_color((r, g, b))
                i += 5
                continue

            # True color background: 48;2;R;G;B
            if attr == 48 and i + 4 < len(attrs) and attrs[i + 1] == 2:
                r, g, b = attrs[i + 2], attrs[i + 3], attrs[i + 4]
                if all(0 <= c <= 255 for c in (r, g, b)):
                    self._set_bg_color((r, g, b))
                i += 5
                continue

            # Standard attr - let pyte handle immediately (preserves order)
            super().select_graphic_rendition(attr)
            i += 1

    def _set_fg_color(self, color):
        self.cursor.attrs = self.cursor.attrs._replace(fg=color)

    def _set_bg_color(self, color):
        self.cursor.attrs = self.cursor.attrs._replace(bg=color)


def test_colors():
    """Test various color escape sequences."""

    screen = FixedHistoryScreen(80, 24)
    stream = pyte.ByteStream(screen)

    tests = [
        # (description, escape_sequence, expected_fg, expected_bg)
        ("Basic red foreground", b"\x1b[31mX", "red", "default"),
        ("Basic green background", b"\x1b[42mX", "default", "green"),
        ("256 color foreground (196=bright red)", b"\x1b[38;5;196mX", 196, "default"),
        ("256 color background (82=bright green)", b"\x1b[48;5;82mX", "default", 82),
        ("True color foreground (255,128,0=orange)", b"\x1b[38;2;255;128;0mX", (255, 128, 0), "default"),
        ("True color background (0,255,255=cyan)", b"\x1b[48;2;0;255;255mX", "default", (0, 255, 255)),
        ("Combined: 256 fg + 256 bg", b"\x1b[38;5;196;48;5;82mX", 196, 82),
        ("Combined: true fg + true bg", b"\x1b[38;2;255;0;0;48;2;0;0;255mX", (255, 0, 0), (0, 0, 255)),
        ("256 fg + bold", b"\x1b[1;38;5;208mX", 208, "default"),  # Bold + orange
        ("Reset then 256", b"\x1b[0;38;5;51mX", 51, "default"),  # Reset + cyan
    ]

    print("=" * 70)
    print("Extended Color Support Test")
    print("=" * 70)
    print()

    passed = 0
    failed = 0

    for desc, seq, expected_fg, expected_bg in tests:
        # Reset screen
        screen.reset()

        # Feed the sequence
        stream.feed(seq)

        # Check what got written
        char = screen.buffer[0][0]

        fg_ok = char.fg == expected_fg
        bg_ok = char.bg == expected_bg

        status = "✓" if (fg_ok and bg_ok) else "✗"

        if fg_ok and bg_ok:
            passed += 1
            print(f"{status} {desc}")
            print(f"    fg={char.fg} bg={char.bg}")
        else:
            failed += 1
            print(f"{status} {desc}")
            print(f"    Expected: fg={expected_fg}, bg={expected_bg}")
            print(f"    Got:      fg={char.fg}, bg={char.bg}")
        print()

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


def test_256_palette_rendering():
    """Visual test - print what the 256 color grid should look like."""

    screen = FixedHistoryScreen(80, 24)
    stream = pyte.ByteStream(screen)

    print()
    print("256 Color Palette Parse Test")
    print("(Shows color indices stored in char.bg)")
    print()

    # Feed all 256 background colors
    for i in range(256):
        seq = f"\x1b[48;5;{i}m ".encode()
        stream.feed(seq)

    # Check a few samples
    samples = [0, 15, 16, 51, 196, 231, 232, 255]
    print("Sample background colors stored:")
    for idx in samples:
        row = idx // 80
        col = idx % 80
        char = screen.buffer[row][col]
        print(f"  Color {idx:3d}: bg={char.bg}")

    # Verify all are integers
    all_int = True
    for row in range(4):  # 256 colors = ~3.2 rows
        for col in range(80):
            idx = row * 80 + col
            if idx >= 256:
                break
            char = screen.buffer[row][col]
            if not isinstance(char.bg, int):
                print(f"  ERROR: Color {idx} bg is {type(char.bg)}, not int")
                all_int = False

    if all_int:
        print("  ✓ All 256 colors stored as integers")

    return all_int


def test_true_color_gradient():
    """Test true color gradient storage."""

    screen = FixedHistoryScreen(80, 24)
    stream = pyte.ByteStream(screen)

    print()
    print("True Color Gradient Parse Test")
    print()

    # Red gradient
    for i in range(80):
        r = int(i * 255 / 79)
        seq = f"\x1b[48;2;{r};0;0m ".encode()
        stream.feed(seq)

    # Check samples
    samples = [0, 20, 40, 60, 79]
    print("Red gradient samples (should be tuples):")
    for col in samples:
        char = screen.buffer[0][col]
        print(f"  Col {col:2d}: bg={char.bg}")

    # Verify they're tuples
    all_tuple = all(
        isinstance(screen.buffer[0][col].bg, tuple)
        for col in range(80)
    )

    if all_tuple:
        print("  ✓ All true colors stored as (R,G,B) tuples")
    else:
        print("  ✗ Some colors not stored as tuples")

    return all_tuple


if __name__ == "__main__":
    print()

    ok1 = test_colors()
    ok2 = test_256_palette_rendering()
    ok3 = test_true_color_gradient()

    print()
    if ok1 and ok2 and ok3:
        print("All tests passed! Drop pyte_buffer.py into vtqt/ and test.")
    else:
        print("Some tests failed - check output above.")

    sys.exit(0 if (ok1 and ok2 and ok3) else 1)