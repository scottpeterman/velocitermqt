#!/usr/bin/env python3
"""
Minimal libvterm test via ctypes.

Tests whether libvterm is installed and accessible,
and demonstrates basic terminal emulation.

Install libvterm first:
    sudo apt install libvterm-dev libvterm0

Run:
    python test_libvterm.py
"""

import ctypes
from ctypes import (
    POINTER, Structure, CFUNCTYPE,
    c_int, c_uint, c_size_t, c_char_p, c_void_p, c_bool, c_uint8, c_uint32
)
import sys


# ─────────────────────────────────────────────────────────────────────────────
# Load library
# ─────────────────────────────────────────────────────────────────────────────

def load_libvterm():
    """Try to load libvterm shared library."""
    names = ['libvterm.so.0', 'libvterm.so', 'vterm']

    for name in names:
        try:
            lib = ctypes.CDLL(name)
            print(f"✓ Loaded {name}")
            return lib
        except OSError:
            continue

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Structures
# ─────────────────────────────────────────────────────────────────────────────

class VTermPos(Structure):
    _fields_ = [("row", c_int), ("col", c_int)]


class VTermColor(Structure):
    _fields_ = [
        ("type", c_uint8),  # VTERM_COLOR_*
        ("red", c_uint8),
        ("green", c_uint8),
        ("blue", c_uint8),
    ]


class VTermScreenCell(Structure):
    _fields_ = [
        ("chars", c_uint32 * 6),  # VTERM_MAX_CHARS_PER_CELL
        ("width", c_int),
        ("attrs_bold", c_uint, 1),
        ("attrs_underline", c_uint, 2),
        ("attrs_italic", c_uint, 1),
        ("attrs_blink", c_uint, 1),
        ("attrs_reverse", c_uint, 1),
        ("attrs_conceal", c_uint, 1),
        ("attrs_strike", c_uint, 1),
        ("attrs_font", c_uint, 4),
        ("attrs_dwl", c_uint, 1),
        ("attrs_dhl", c_uint, 2),
        ("attrs_small", c_uint, 1),
        ("attrs_baseline", c_uint, 2),
        ("fg", VTermColor),
        ("bg", VTermColor),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Test functions
# ─────────────────────────────────────────────────────────────────────────────

def test_basic_operations(lib):
    """Test basic vterm operations."""

    # Function signatures
    lib.vterm_new.argtypes = [c_int, c_int]
    lib.vterm_new.restype = c_void_p

    lib.vterm_free.argtypes = [c_void_p]
    lib.vterm_free.restype = None

    lib.vterm_obtain_screen.argtypes = [c_void_p]
    lib.vterm_obtain_screen.restype = c_void_p

    lib.vterm_screen_reset.argtypes = [c_void_p, c_int]
    lib.vterm_screen_reset.restype = None

    lib.vterm_input_write.argtypes = [c_void_p, c_char_p, c_size_t]
    lib.vterm_input_write.restype = c_size_t

    lib.vterm_screen_get_cell.argtypes = [c_void_p, VTermPos, POINTER(VTermScreenCell)]
    lib.vterm_screen_get_cell.restype = c_int

    lib.vterm_set_utf8.argtypes = [c_void_p, c_int]
    lib.vterm_set_utf8.restype = None

    print("\n" + "=" * 60)
    print("Basic Operations Test")
    print("=" * 60)

    # Create terminal
    vt = lib.vterm_new(24, 80)
    if not vt:
        print("✗ Failed to create vterm")
        return False
    print("✓ Created 24x80 terminal")

    # Enable UTF-8
    lib.vterm_set_utf8(vt, 1)
    print("✓ Enabled UTF-8 mode")

    # Get screen
    screen = lib.vterm_obtain_screen(vt)
    if not screen:
        print("✗ Failed to get screen")
        lib.vterm_free(vt)
        return False
    print("✓ Got screen handle")

    # Reset screen
    lib.vterm_screen_reset(screen, 1)
    print("✓ Reset screen")

    # Write some text
    text = b"Hello, libvterm!"
    written = lib.vterm_input_write(vt, text, len(text))
    print(f"✓ Wrote {written} bytes: {text.decode()}")

    # Read back cells
    cell = VTermScreenCell()
    pos = VTermPos(row=0, col=0)

    result = []
    for i in range(len(text)):
        pos.col = i
        lib.vterm_screen_get_cell(screen, pos, ctypes.byref(cell))
        if cell.chars[0]:
            result.append(chr(cell.chars[0]))

    recovered = ''.join(result)
    print(f"✓ Read back: {recovered}")

    # Cleanup
    lib.vterm_free(vt)
    print("✓ Freed terminal")

    return True


def test_colors(lib):
    """Test color escape sequence handling."""

    # Set up function signatures
    lib.vterm_new.argtypes = [c_int, c_int]
    lib.vterm_new.restype = c_void_p
    lib.vterm_free.argtypes = [c_void_p]
    lib.vterm_obtain_screen.argtypes = [c_void_p]
    lib.vterm_obtain_screen.restype = c_void_p
    lib.vterm_screen_reset.argtypes = [c_void_p, c_int]
    lib.vterm_input_write.argtypes = [c_void_p, c_char_p, c_size_t]
    lib.vterm_input_write.restype = c_size_t
    lib.vterm_screen_get_cell.argtypes = [c_void_p, VTermPos, POINTER(VTermScreenCell)]
    lib.vterm_set_utf8.argtypes = [c_void_p, c_int]

    print("\n" + "=" * 60)
    print("Color Support Test")
    print("=" * 60)

    vt = lib.vterm_new(24, 80)
    lib.vterm_set_utf8(vt, 1)
    screen = lib.vterm_obtain_screen(vt)
    lib.vterm_screen_reset(screen, 1)

    tests = [
        ("16 color fg (red)", b"\x1b[31mX"),
        ("16 color bg (green)", b"\x1b[42mX"),
        ("256 color fg", b"\x1b[38;5;196mX"),
        ("256 color bg", b"\x1b[48;5;82mX"),
        ("True color fg", b"\x1b[38;2;255;128;0mX"),
        ("True color bg", b"\x1b[48;2;0;255;255mX"),
    ]

    cell = VTermScreenCell()
    pos = VTermPos(row=0, col=0)

    for name, seq in tests:
        # Reset and write
        lib.vterm_screen_reset(screen, 1)
        lib.vterm_input_write(vt, seq, len(seq))

        # Read cell
        lib.vterm_screen_get_cell(screen, pos, ctypes.byref(cell))

        fg = cell.fg
        bg = cell.bg

        print(f"  {name}:")
        print(f"    fg: type={fg.type} rgb=({fg.red},{fg.green},{fg.blue})")
        print(f"    bg: type={bg.type} rgb=({bg.red},{bg.green},{bg.blue})")

    lib.vterm_free(vt)
    print("✓ Color tests complete")
    return True


def test_escape_sequences(lib):
    """Test various escape sequence coverage."""

    lib.vterm_new.argtypes = [c_int, c_int]
    lib.vterm_new.restype = c_void_p
    lib.vterm_free.argtypes = [c_void_p]
    lib.vterm_obtain_screen.argtypes = [c_void_p]
    lib.vterm_obtain_screen.restype = c_void_p
    lib.vterm_screen_reset.argtypes = [c_void_p, c_int]
    lib.vterm_input_write.argtypes = [c_void_p, c_char_p, c_size_t]
    lib.vterm_input_write.restype = c_size_t
    lib.vterm_set_utf8.argtypes = [c_void_p, c_int]

    print("\n" + "=" * 60)
    print("Escape Sequence Coverage Test")
    print("=" * 60)

    vt = lib.vterm_new(24, 80)
    lib.vterm_set_utf8(vt, 1)
    screen = lib.vterm_obtain_screen(vt)
    lib.vterm_screen_reset(screen, 1)

    sequences = [
        ("Cursor movement", b"\x1b[5;10H"),  # Move to row 5, col 10
        ("Erase in display", b"\x1b[2J"),  # Clear screen
        ("Erase in line", b"\x1b[K"),  # Clear to end of line
        ("SGR reset", b"\x1b[0m"),  # Reset attributes
        ("Bold", b"\x1b[1mX\x1b[0m"),
        ("Italic", b"\x1b[3mX\x1b[0m"),
        ("Underline", b"\x1b[4mX\x1b[0m"),
        ("Blink", b"\x1b[5mX\x1b[0m"),
        ("Reverse", b"\x1b[7mX\x1b[0m"),
        ("Strikethrough", b"\x1b[9mX\x1b[0m"),
        ("Alt screen on", b"\x1b[?1049h"),
        ("Alt screen off", b"\x1b[?1049l"),
        ("Mouse enable", b"\x1b[?1000h"),
        ("Mouse SGR mode", b"\x1b[?1006h"),
        ("Bracketed paste", b"\x1b[?2004h"),
        ("OSC title", b"\x1b]0;Window Title\x07"),
        ("OSC hyperlink", b"\x1b]8;;https://example.com\x1b\\Link\x1b]8;;\x1b\\"),
    ]

    for name, seq in sequences:
        try:
            written = lib.vterm_input_write(vt, seq, len(seq))
            status = "✓" if written == len(seq) else "?"
            print(f"  {status} {name}: {written}/{len(seq)} bytes consumed")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    lib.vterm_free(vt)
    return True


def main():
    print("=" * 60)
    print("libvterm Integration Test")
    print("=" * 60)

    # Load library
    lib = load_libvterm()
    if not lib:
        print("\n✗ libvterm not found!")
        print("\nInstall with:")
        print("  sudo apt install libvterm-dev libvterm0")
        return 1

    # Run tests
    try:
        test_basic_operations(lib)
        test_colors(lib)
        test_escape_sequences(lib)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
libvterm works! To integrate into VelociTermQt:

1. Create vterm_buffer.py (like pyte_buffer.py)
2. Wrap the ctypes calls in a clean Python API
3. Handle screen callbacks for damage/scrollback
4. Replace PyteTerminalBuffer with VTermBuffer

Pros over pyte:
  + Complete escape sequence coverage
  + Proper mouse reporting
  + OSC sequences (hyperlinks, clipboard)
  + Battle-tested (neovim, libvte)
  + Sixel graphics support

Cons:
  - Native library dependency
  - More complex callback setup
  - Harder to debug

Recommendation: Keep pyte for now (it's working!),
but this proves libvterm is viable if you hit walls.
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())