"""
Pyte Terminal Buffer - Terminal emulation backed by pyte library.

Handles the tricky integration between:
- pyte's HistoryScreen (escape sequence parsing, screen state)
- Our scrollback management (unified history + active view)
- Selection across history/active boundary
- GPU render array generation
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np

import pyte
from pyte.screens import Char

from .terminal_buffer import CellAttr, Selection


class FixedHistoryScreen(pyte.HistoryScreen):
    """
    Patched HistoryScreen that handles pyte's CSI dispatch bug.
    
    Pyte incorrectly passes private=True to some handlers that don't
    accept it (like select_graphic_rendition). This fixes that.
    """
    
    def select_graphic_rendition(self, *attrs, **kwargs):
        """Handle SGR - ignore private flag if passed."""
        kwargs.pop('private', None)
        return super().select_graphic_rendition(*attrs, **kwargs)
    
    def report_device_attributes(self, *args, **kwargs):
        """Handle DA - ignore private flag."""
        kwargs.pop('private', None)
        return super().report_device_attributes(*args, **kwargs)
    
    def erase_in_display(self, how=0, **kwargs):
        """Handle ED - ignore private flag."""
        kwargs.pop('private', None)
        return super().erase_in_display(how, **kwargs)
    
    def erase_in_line(self, how=0, **kwargs):
        """Handle EL - ignore private flag."""
        kwargs.pop('private', None)
        return super().erase_in_line(how, **kwargs)
    
    def cursor_position(self, *args, **kwargs):
        """Handle CUP - ignore private flag."""
        kwargs.pop('private', None)
        return super().cursor_position(*args, **kwargs)
    
    def set_mode(self, *args, **kwargs):
        """Handle SM - already handles private but ensure compatibility."""
        return super().set_mode(*args, **kwargs)
    
    def reset_mode(self, *args, **kwargs):
        """Handle RM - already handles private but ensure compatibility."""
        return super().reset_mode(*args, **kwargs)


# Default colors (pyte uses names, we need RGB)
PYTE_COLORS = {
    "default": 0xD4D4D4,
    "black": 0x000000,
    "red": 0xCD3131,
    "green": 0x0DBC79,
    "yellow": 0xE5E510,
    "blue": 0x2472C8,
    "magenta": 0xBC3FBC,
    "cyan": 0x11A8CD,
    "white": 0xE5E5E5,
    # Bright variants
    "brightblack": 0x666666,
    "brightred": 0xF14C4C,
    "brightgreen": 0x23D18B,
    "brightyellow": 0xF5F543,
    "brightblue": 0x3B8EEA,
    "brightmagenta": 0xD670D6,
    "brightcyan": 0x29B8DB,
    "brightwhite": 0xFFFFFF,
}

# 256-color palette (standard xterm)
XTERM_256 = None  # Lazy init

def get_256_color(index: int) -> int:
    """Get RGB for xterm 256-color palette index."""
    global XTERM_256
    if XTERM_256 is None:
        XTERM_256 = _build_256_palette()
    return XTERM_256.get(index, 0xD4D4D4)

def _build_256_palette() -> dict:
    """Build xterm 256-color palette."""
    palette = {}
    
    # 0-15: Standard colors (handled by name)
    standard = [
        0x000000, 0xCD3131, 0x0DBC79, 0xE5E510,
        0x2472C8, 0xBC3FBC, 0x11A8CD, 0xE5E5E5,
        0x666666, 0xF14C4C, 0x23D18B, 0xF5F543,
        0x3B8EEA, 0xD670D6, 0x29B8DB, 0xFFFFFF,
    ]
    for i, c in enumerate(standard):
        palette[i] = c
    
    # 16-231: 6x6x6 color cube
    for i in range(216):
        r = (i // 36) % 6
        g = (i // 6) % 6
        b = i % 6
        palette[16 + i] = (
            (0 if r == 0 else 55 + r * 40) << 16 |
            (0 if g == 0 else 55 + g * 40) << 8 |
            (0 if b == 0 else 55 + b * 40)
        )
    
    # 232-255: Grayscale
    for i in range(24):
        v = 8 + i * 10
        palette[232 + i] = (v << 16) | (v << 8) | v
    
    return palette


def pyte_color_to_rgb(color, default: int = 0xD4D4D4) -> int:
    """Convert pyte color specification to RGB integer."""
    if color is None or color == "default":
        return default
    
    if isinstance(color, str):
        # Named color
        return PYTE_COLORS.get(color.lower(), default)
    
    if isinstance(color, int):
        # 256-color index
        return get_256_color(color)
    
    if isinstance(color, (tuple, list)) and len(color) == 3:
        # True color (r, g, b)
        r, g, b = color
        return (r << 16) | (g << 8) | b
    
    return default


@dataclass
class HistoryLine:
    """A line stored in scrollback history."""
    chars: List[Char]  # pyte Char objects
    

class PyteTerminalBuffer:
    """
    Terminal buffer backed by pyte for escape sequence handling.
    
    Maintains:
    - pyte.HistoryScreen for terminal emulation
    - Unified line numbering across history + active screen
    - Selection state in absolute coordinates
    - Viewport (scroll offset)
    
    Line numbering:
    - Line 0 = oldest line in history
    - Line (history_size - 1) = newest history line
    - Line history_size = first line of active screen
    - Line (history_size + screen_rows - 1) = last line of active screen
    """
    
    def __init__(self, rows: int, cols: int, scrollback_limit: int = 10000):
        self.visible_rows = rows
        self.cols = cols
        self.scrollback_limit = scrollback_limit
        
        # Pyte screen with history (using our patched version)
        self.screen = FixedHistoryScreen(cols, rows, history=scrollback_limit)
        self.stream = pyte.ByteStream(self.screen)
        
        # Selection in absolute line coordinates
        self.selection = Selection()
        
        # Viewport offset (0 = showing oldest history)
        # Default: scroll to bottom (show active screen)
        self._scroll_offset = 0
        self._auto_scroll = True
        
        # Colors
        self.default_fg = 0xD4D4D4
        self.default_bg = 0x1E1E1E
        self.selection_bg = 0x264F78
        
        # Dirty tracking
        self._dirty = True
    
    @property
    def history_size(self) -> int:
        """Number of lines in scrollback history."""
        return len(self.screen.history.top)
    
    @property
    def total_lines(self) -> int:
        """Total lines (history + active screen)."""
        return self.history_size + self.screen.lines
    
    @property
    def max_scroll(self) -> int:
        """Maximum scroll offset."""
        return max(0, self.total_lines - self.visible_rows)
    
    @property
    def scroll_offset(self) -> int:
        """Current scroll offset (0 = top of history)."""
        return self._scroll_offset
    
    def _clamp_scroll(self):
        """Ensure scroll offset is valid."""
        self._scroll_offset = max(0, min(self._scroll_offset, self.max_scroll))
    
    # ─────────────────────────────────────────────────────────
    # Data input
    # ─────────────────────────────────────────────────────────
    
    def feed(self, data: bytes):
        """Feed PTY output data to terminal emulator."""
        was_at_bottom = self._scroll_offset >= self.max_scroll
        
        try:
            self.stream.feed(data)
        except Exception as e:
            # Log but don't crash on malformed sequences
            import sys
            print(f"pyte stream error: {e}", file=sys.stderr)
        
        self._clamp_scroll()
        
        # Auto-scroll if we were at bottom
        if was_at_bottom and self._auto_scroll:
            self._scroll_offset = self.max_scroll
        
        self._dirty = True
    
    def write(self, text: str):
        """Write text (convenience wrapper)."""
        self.feed(text.encode('utf-8'))
    
    # ─────────────────────────────────────────────────────────
    # Scrolling
    # ─────────────────────────────────────────────────────────
    
    def scroll_to(self, offset: int):
        """Scroll to absolute offset."""
        self._scroll_offset = max(0, min(offset, self.max_scroll))
        self._dirty = True
    
    def scroll_by(self, delta: int):
        """Scroll by delta lines."""
        self.scroll_to(self._scroll_offset + delta)
    
    def scroll_page(self, direction: int):
        """Scroll by page (-1 = up, 1 = down)."""
        self.scroll_by(direction * (self.visible_rows - 2))
    
    def scroll_to_top(self):
        """Scroll to top of history."""
        self.scroll_to(0)
    
    def scroll_to_bottom(self):
        """Scroll to bottom (show active screen)."""
        self.scroll_to(self.max_scroll)
    
    # ─────────────────────────────────────────────────────────
    # Line access (unified history + active)
    # ─────────────────────────────────────────────────────────
    
    def get_line(self, abs_row: int) -> Optional[dict]:
        """
        Get line by absolute row number.
        
        Returns dict mapping column -> pyte.Char, or None if out of bounds.
        """
        history_size = self.history_size
        
        if abs_row < 0:
            return None
        
        if abs_row < history_size:
            # Line is in history
            # history.top is a deque, oldest first
            history_list = list(self.screen.history.top)
            if abs_row < len(history_list):
                return history_list[abs_row]
            return None
        
        # Line is in active screen
        screen_row = abs_row - history_size
        if 0 <= screen_row < self.screen.lines:
            return self.screen.buffer[screen_row]
        
        return None
    
    def get_char(self, abs_row: int, col: int) -> Optional[Char]:
        """Get character at absolute position."""
        line = self.get_line(abs_row)
        if line is None:
            return None
        return line.get(col, self.screen.default_char)
    
    # ─────────────────────────────────────────────────────────
    # Selection (in absolute coordinates)
    # ─────────────────────────────────────────────────────────
    
    def start_selection(self, view_row: int, col: int):
        """Start selection at viewport position."""
        abs_row = view_row + self._scroll_offset
        abs_row = max(0, min(abs_row, self.total_lines - 1))
        col = max(0, min(col, self.cols - 1))
        
        self.selection.start_row = abs_row
        self.selection.start_col = col
        self.selection.end_row = abs_row
        self.selection.end_col = col
        self.selection.active = True
        self._dirty = True
    
    def update_selection(self, view_row: int, col: int):
        """Update selection end point."""
        if not self.selection.active:
            return
        
        abs_row = view_row + self._scroll_offset
        abs_row = max(0, min(abs_row, self.total_lines - 1))
        col = max(0, min(col, self.cols - 1))
        
        if self.selection.end_row != abs_row or self.selection.end_col != col:
            self.selection.end_row = abs_row
            self.selection.end_col = col
            self._dirty = True
    
    def end_selection(self):
        """Finalize selection."""
        pass  # Keep active, just stop tracking
    
    def clear_selection(self):
        """Clear selection."""
        if self.selection.active:
            self.selection.clear()
            self._dirty = True
    
    def is_selected(self, abs_row: int, col: int) -> bool:
        """Check if absolute position is selected."""
        return self.selection.contains(abs_row, col)
    
    def get_selected_text(self) -> str:
        """Get text within selection."""
        if not self.selection.active or self.selection.start_row < 0:
            return ""
        
        r1, c1, r2, c2 = self.selection.normalize()
        
        lines = []
        for row in range(r1, r2 + 1):
            line_dict = self.get_line(row)
            if line_dict is None:
                continue
            
            # Determine column range for this row
            start_col = c1 if row == r1 else 0
            end_col = c2 if row == r2 else self.cols - 1
            
            # Extract characters
            chars = []
            for col in range(start_col, end_col + 1):
                char = line_dict.get(col, self.screen.default_char)
                chars.append(char.data if char.data else ' ')
            
            lines.append(''.join(chars).rstrip())
        
        return '\n'.join(lines)
    
    # ─────────────────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────────────────
    
    def to_render_array(self) -> np.ndarray:
        """
        Pack visible cells into numpy array for GPU.
        
        Shape: (rows, cols, 8)
        Data: [char_code, fg_r, fg_g, fg_b, bg_r, bg_g, bg_b, attrs]
        """
        data = np.zeros((self.visible_rows, self.cols, 8), dtype=np.float32)
        
        for view_row in range(self.visible_rows):
            abs_row = self._scroll_offset + view_row
            line = self.get_line(abs_row)
            
            for col in range(self.cols):
                if line is not None:
                    char = line.get(col, self.screen.default_char)
                else:
                    char = self.screen.default_char
                
                # Get character
                char_data = char.data if char.data else ' '
                char_code = ord(char_data[0]) if char_data else 32
                
                # Get colors
                fg = pyte_color_to_rgb(char.fg, self.default_fg)
                bg = pyte_color_to_rgb(char.bg, self.default_bg)
                
                # Check selection
                selected = self.is_selected(abs_row, col)
                if selected:
                    bg = self.selection_bg
                
                # Build attributes
                attrs = CellAttr.NONE
                if char.bold:
                    attrs |= CellAttr.BOLD
                if char.italics:
                    attrs |= CellAttr.ITALIC
                if char.underscore:
                    attrs |= CellAttr.UNDERLINE
                if char.blink:
                    attrs |= CellAttr.BLINK
                if char.reverse:
                    attrs |= CellAttr.REVERSE
                if char.strikethrough:
                    attrs |= CellAttr.STRIKE
                if selected:
                    attrs |= CellAttr.SELECTED
                
                # Handle reverse video
                if char.reverse and not selected:
                    fg, bg = bg, fg
                
                data[view_row, col] = [
                    char_code,
                    ((fg >> 16) & 0xFF) / 255.0,
                    ((fg >> 8) & 0xFF) / 255.0,
                    (fg & 0xFF) / 255.0,
                    ((bg >> 16) & 0xFF) / 255.0,
                    ((bg >> 8) & 0xFF) / 255.0,
                    (bg & 0xFF) / 255.0,
                    float(attrs),
                ]
        
        return data
    
    # ─────────────────────────────────────────────────────────
    # Terminal control
    # ─────────────────────────────────────────────────────────
    
    def resize(self, rows: int, cols: int):
        """Resize terminal."""
        self.visible_rows = rows
        self.cols = cols
        self.screen.resize(rows, cols)
        self._clamp_scroll()
        self._dirty = True
    
    def reset(self):
        """Reset terminal state."""
        self.screen.reset()
        self.selection.clear()
        self._scroll_offset = 0
        self._dirty = True
    
    def clear(self):
        """Clear screen and history."""
        self.screen.reset()
        self.screen.history.top.clear()
        self.screen.history.bottom.clear()
        self.selection.clear()
        self._scroll_offset = 0
        self._dirty = True
    
    @property
    def cursor_position(self) -> Tuple[int, int]:
        """Get cursor position (row, col) in active screen."""
        return (self.screen.cursor.y, self.screen.cursor.x)
    
    @property
    def cursor_visible(self) -> bool:
        """Check if cursor should be visible."""
        # Cursor only visible when viewing active screen
        return self._scroll_offset >= self.max_scroll
    
    def is_dirty(self) -> bool:
        return self._dirty
    
    def clear_dirty(self):
        self._dirty = False
