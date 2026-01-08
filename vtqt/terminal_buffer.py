"""
Terminal Buffer - Core data structures for terminal/text grid rendering.
Separates buffer management from rendering.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import IntFlag
import numpy as np


class CellAttr(IntFlag):
    """Cell attributes - matches libvterm's VTermAttr"""
    NONE = 0
    BOLD = 1 << 0
    ITALIC = 1 << 1
    UNDERLINE = 1 << 2
    BLINK = 1 << 3
    REVERSE = 1 << 4
    STRIKE = 1 << 5
    DIM = 1 << 6
    SELECTED = 1 << 7  # For text selection


@dataclass(slots=True)
class Cell:
    """Single terminal cell"""
    char: str = ' '
    fg: int = 0xD4D4D4       # Light gray foreground
    bg: int = 0x1E1E1E       # Dark background
    attrs: CellAttr = CellAttr.NONE
    width: int = 1


@dataclass
class Line:
    """Single line of cells"""
    cells: List[Cell]
    continuation: bool = False
    
    @classmethod
    def blank(cls, cols: int, bg: int = 0x1E1E1E) -> 'Line':
        return cls(cells=[Cell(bg=bg) for _ in range(cols)])
    
    @classmethod
    def from_text(cls, text: str, cols: int, 
                  fg: int = 0xD4D4D4, bg: int = 0x1E1E1E) -> 'Line':
        """Create line from text string, padded/truncated to cols."""
        cells = []
        for i in range(cols):
            char = text[i] if i < len(text) else ' '
            # Handle tabs
            if char == '\t':
                char = ' '
            # Handle non-printable
            if ord(char) < 32 and char != ' ':
                char = ' '
            cells.append(Cell(char=char, fg=fg, bg=bg))
        return cls(cells=cells)


@dataclass
class Selection:
    """Text selection state"""
    start_row: int = -1
    start_col: int = -1
    end_row: int = -1
    end_col: int = -1
    active: bool = False
    
    def clear(self):
        self.start_row = -1
        self.start_col = -1
        self.end_row = -1
        self.end_col = -1
        self.active = False
    
    def normalize(self) -> Tuple[int, int, int, int]:
        """Return selection with start before end."""
        if (self.start_row, self.start_col) <= (self.end_row, self.end_col):
            return self.start_row, self.start_col, self.end_row, self.end_col
        return self.end_row, self.end_col, self.start_row, self.start_col
    
    def contains(self, row: int, col: int) -> bool:
        """Check if cell is within selection."""
        if not self.active or self.start_row < 0:
            return False
        
        r1, c1, r2, c2 = self.normalize()
        
        if row < r1 or row > r2:
            return False
        if row == r1 and row == r2:
            return c1 <= col <= c2
        if row == r1:
            return col >= c1
        if row == r2:
            return col <= c2
        return True


class TextBuffer:
    """
    Manages text content with viewport scrolling.
    Can be used for file viewer or terminal scrollback.
    """
    
    def __init__(self, visible_rows: int, cols: int):
        self.visible_rows = visible_rows
        self.cols = cols
        
        # All content lines
        self.lines: List[Line] = []
        
        # Viewport offset (which line is at top of view)
        self.scroll_offset: int = 0
        
        # Selection
        self.selection = Selection()
        
        # Colors
        self.default_fg = 0xD4D4D4
        self.default_bg = 0x1E1E1E
        self.selection_bg = 0x264F78  # VS Code blue selection
        
        # Dirty tracking
        self._dirty = True
    
    def load_text(self, text: str):
        """Load text content into buffer."""
        self.lines.clear()
        for line_text in text.split('\n'):
            # Expand tabs
            line_text = line_text.replace('\t', '    ')
            self.lines.append(Line.from_text(
                line_text, self.cols, 
                self.default_fg, self.default_bg
            ))
        
        # Ensure at least visible_rows lines
        while len(self.lines) < self.visible_rows:
            self.lines.append(Line.blank(self.cols, self.default_bg))
        
        self.scroll_offset = 0
        self.selection.clear()
        self._dirty = True
    
    def load_file(self, filepath: str):
        """Load file content into buffer."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                self.load_text(f.read())
        except Exception as e:
            self.load_text(f"Error loading file: {e}")
    
    @property
    def total_lines(self) -> int:
        return len(self.lines)
    
    @property
    def max_scroll(self) -> int:
        return max(0, len(self.lines) - self.visible_rows)
    
    # ─────────────────────────────────────────────────────────
    # Scrolling
    # ─────────────────────────────────────────────────────────
    
    def scroll_to(self, offset: int):
        """Scroll to specific line offset."""
        new_offset = max(0, min(offset, self.max_scroll))
        if new_offset != self.scroll_offset:
            self.scroll_offset = new_offset
            self._dirty = True
    
    def scroll_by(self, delta: int):
        """Scroll by delta lines (positive = down)."""
        self.scroll_to(self.scroll_offset + delta)
    
    def scroll_page(self, direction: int):
        """Scroll by page (direction: 1=down, -1=up)."""
        self.scroll_by(direction * (self.visible_rows - 2))
    
    def scroll_to_top(self):
        self.scroll_to(0)
    
    def scroll_to_bottom(self):
        self.scroll_to(self.max_scroll)
    
    # ─────────────────────────────────────────────────────────
    # Selection
    # ─────────────────────────────────────────────────────────
    
    def start_selection(self, row: int, col: int):
        """Start text selection at position."""
        # Convert viewport position to buffer position
        buf_row = row + self.scroll_offset
        if 0 <= buf_row < len(self.lines) and 0 <= col < self.cols:
            self.selection.start_row = buf_row
            self.selection.start_col = col
            self.selection.end_row = buf_row
            self.selection.end_col = col
            self.selection.active = True
            self._dirty = True
    
    def update_selection(self, row: int, col: int):
        """Update selection end point."""
        if not self.selection.active:
            return
        buf_row = row + self.scroll_offset
        buf_row = max(0, min(buf_row, len(self.lines) - 1))
        col = max(0, min(col, self.cols - 1))
        
        if self.selection.end_row != buf_row or self.selection.end_col != col:
            self.selection.end_row = buf_row
            self.selection.end_col = col
            self._dirty = True
    
    def end_selection(self):
        """Finalize selection."""
        # Keep active but stop tracking
        pass
    
    def clear_selection(self):
        """Clear selection."""
        if self.selection.active:
            self.selection.clear()
            self._dirty = True
    
    def get_selected_text(self) -> str:
        """Get text within selection."""
        if not self.selection.active or self.selection.start_row < 0:
            return ""
        
        r1, c1, r2, c2 = self.selection.normalize()
        
        if r1 == r2:
            # Single line
            line = self.lines[r1]
            return ''.join(c.char for c in line.cells[c1:c2+1]).rstrip()
        
        # Multiple lines
        result = []
        for row in range(r1, r2 + 1):
            if row >= len(self.lines):
                break
            line = self.lines[row]
            if row == r1:
                result.append(''.join(c.char for c in line.cells[c1:]).rstrip())
            elif row == r2:
                result.append(''.join(c.char for c in line.cells[:c2+1]).rstrip())
            else:
                result.append(''.join(c.char for c in line.cells).rstrip())
        
        return '\n'.join(result)
    
    # ─────────────────────────────────────────────────────────
    # Rendering - get visible cells with selection applied
    # ─────────────────────────────────────────────────────────
    
    def get_visible_lines(self) -> List[Line]:
        """Get lines visible in viewport."""
        result = []
        for i in range(self.visible_rows):
            buf_idx = self.scroll_offset + i
            if buf_idx < len(self.lines):
                result.append(self.lines[buf_idx])
            else:
                result.append(Line.blank(self.cols, self.default_bg))
        return result
    
    def is_selected(self, view_row: int, col: int) -> bool:
        """Check if viewport cell is selected."""
        buf_row = view_row + self.scroll_offset
        return self.selection.contains(buf_row, col)
    
    def to_render_array(self) -> np.ndarray:
        """
        Pack visible cells into numpy array for GPU.
        Shape: (rows, cols, 8)
        Data: [char_code, fg_r, fg_g, fg_b, bg_r, bg_g, bg_b, attrs]
        """
        data = np.zeros((self.visible_rows, self.cols, 8), dtype=np.float32)
        
        lines = self.get_visible_lines()
        
        for row_idx, line in enumerate(lines):
            for col_idx, cell in enumerate(line.cells[:self.cols]):
                # Check selection
                selected = self.is_selected(row_idx, col_idx)
                
                fg = cell.fg
                bg = self.selection_bg if selected else cell.bg
                
                # Reverse video if selected and has REVERSE attr
                if selected:
                    attrs = cell.attrs | CellAttr.SELECTED
                else:
                    attrs = cell.attrs
                
                char_code = ord(cell.char[0]) if cell.char else 32
                
                data[row_idx, col_idx] = [
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
    
    def is_dirty(self) -> bool:
        return self._dirty
    
    def clear_dirty(self):
        self._dirty = False
    
    def resize(self, visible_rows: int, cols: int):
        """Handle viewport resize."""
        self.visible_rows = visible_rows
        self.cols = cols
        # Reload to re-wrap lines
        self._dirty = True
