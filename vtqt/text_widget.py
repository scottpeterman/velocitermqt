"""
GPU Text Widget - QOpenGLWidget-based text grid with scrolling and selection.
Base class for file viewing and terminal emulation.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import glClear, glClearColor, glViewport, GL_COLOR_BUFFER_BIT

from .terminal_buffer import TextBuffer
from .gpu_renderer import GridRenderer


class GPUTextWidget(QOpenGLWidget):
    """
    OpenGL widget for rendering text grid with GPU acceleration.
    Handles scrolling, selection, and keyboard/mouse input.
    
    Subclass this for terminal emulation (TerminalWidget).
    """
    
    # Signals
    scroll_changed = pyqtSignal(int, int)  # offset, max
    selection_changed = pyqtSignal(str)    # status message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Buffer and renderer
        self.buffer: Optional[TextBuffer] = None
        self.renderer: Optional[GridRenderer] = None
        
        # Font settings
        self.font_family = "monospace"
        self.font_size = 14
        self._font: Optional[QFont] = None
        
        # Grid dimensions (calculated from widget size and font)
        self.cols = 80
        self.rows = 24
        
        # Mouse state
        self._mouse_pressed = False
        self._last_mouse_row = -1
        self._last_mouse_col = -1
        
        # Auto-scroll during drag selection
        self._scroll_timer = QTimer()
        self._scroll_timer.setInterval(50)  # 20 fps scroll
        self._scroll_timer.timeout.connect(self._auto_scroll_tick)
        self._scroll_direction = 0  # -1 up, 0 none, 1 down
        
        # Enable mouse tracking for selection
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Size policy - expand to fill available space
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Refresh timer (limit redraw rate)
        self._needs_redraw = True
    
    # ─────────────────────────────────────────────────────────
    # Font management
    # ─────────────────────────────────────────────────────────
    
    def set_font(self, family: str, size: int):
        """Set the font for rendering."""
        self.font_family = family
        self.font_size = size
        self._font = None  # Will be recreated
        self._needs_redraw = True
        self.update()
    
    def get_font(self) -> QFont:
        """Get or create font."""
        if self._font is None:
            self._font = QFont(self.font_family, self.font_size)
            self._font.setStyleHint(QFont.StyleHint.Monospace)
            self._font.setFixedPitch(True)
        return self._font
    
    # ─────────────────────────────────────────────────────────
    # Content loading (for file viewer mode)
    # ─────────────────────────────────────────────────────────
    
    def load_file(self, filepath: str):
        """Load a file into the buffer."""
        if self.buffer:
            self.buffer.load_file(filepath)
            self._needs_redraw = True
            self._emit_scroll_state()
            self.update()
    
    def load_text(self, text: str):
        """Load text directly into the buffer."""
        if self.buffer:
            self.buffer.load_text(text)
            self._needs_redraw = True
            self._emit_scroll_state()
            self.update()
    
    # ─────────────────────────────────────────────────────────
    # Grid geometry
    # ─────────────────────────────────────────────────────────
    
    def _emit_scroll_state(self):
        """Emit scroll position signal."""
        if self.buffer:
            self.scroll_changed.emit(self.buffer.scroll_offset, self.buffer.max_scroll)
    
    def _calculate_grid_size(self):
        """Calculate grid dimensions from widget size and font metrics."""
        if not self.renderer or not self.renderer.atlas:
            return
        
        w, h = self.width(), self.height()
        cw = self.renderer.cell_width
        ch = self.renderer.cell_height
        
        if cw > 0 and ch > 0:
            new_cols = max(1, w // cw)
            new_rows = max(1, h // ch)
            
            if new_cols != self.cols or new_rows != self.rows:
                self.cols = new_cols
                self.rows = new_rows
                self._on_grid_resized()
    
    def _on_grid_resized(self):
        """Called when grid dimensions change. Override in subclass."""
        if self.buffer:
            # Recreate buffer with new size, preserving content
            old_lines = self.buffer.lines
            self.buffer = TextBuffer(self.rows, self.cols)
            
            if old_lines:
                text = '\n'.join(
                    ''.join(c.char for c in line.cells).rstrip() 
                    for line in old_lines
                )
                self.buffer.load_text(text)
            
            self._emit_scroll_state()
    
    def pixel_to_cell(self, x: int, y: int) -> tuple[int, int]:
        """Convert pixel coordinates to cell row, col."""
        if not self.renderer or not self.renderer.atlas:
            return 0, 0
        
        cw = self.renderer.cell_width
        ch = self.renderer.cell_height
        
        col = max(0, min(x // cw, self.cols - 1))
        row = max(0, min(y // ch, self.rows - 1))
        
        return row, col
    
    # ─────────────────────────────────────────────────────────
    # OpenGL lifecycle
    # ─────────────────────────────────────────────────────────
    
    def initializeGL(self):
        """Initialize OpenGL resources."""
        glClearColor(0.12, 0.12, 0.12, 1.0)
        
        # Create renderer
        self.renderer = GridRenderer(self)
        self.renderer.initialize(self.get_font())
        
        # Calculate grid size
        self._calculate_grid_size()
        
        # Create buffer
        self.buffer = TextBuffer(self.rows, self.cols)
        
        # Load initial content
        self._load_initial_content()
    
    def _load_initial_content(self):
        """Load initial content. Override in subclass."""
        sample = self._generate_sample_text()
        self.buffer.load_text(sample)
    
    def resizeGL(self, w: int, h: int):
        """Handle resize."""
        glViewport(0, 0, w, h)
        self._calculate_grid_size()
        self._needs_redraw = True
    
    def paintGL(self):
        """Render the text grid."""
        glClear(GL_COLOR_BUFFER_BIT)
        
        if not self.buffer or not self.renderer:
            return
        
        # Get render data from buffer
        cell_data = self.buffer.to_render_array()
        
        # Render
        self.renderer.render(cell_data, (self.width(), self.height()))
        
        self._needs_redraw = False
    
    def _generate_sample_text(self) -> str:
        """Generate sample text for testing."""
        lines = []
        lines.append("╔══════════════════════════════════════════════════════════════════════╗")
        lines.append("║  GPU Text Viewer - Proof of Concept                                  ║")
        lines.append("║  Scroll with mouse wheel, select text with click+drag                ║")
        lines.append("║  Press Ctrl+O to open a file, Ctrl+C to copy selection               ║")
        lines.append("╚══════════════════════════════════════════════════════════════════════╝")
        lines.append("")
        
        for i in range(1, 201):
            lines.append(f"{i:4d} │ This is line {i} - sample content for scrolling and selection testing")
        
        lines.append("")
        lines.append("═" * 70)
        lines.append("End of sample content")
        
        return '\n'.join(lines)
    
    # ─────────────────────────────────────────────────────────
    # Keyboard input
    # ─────────────────────────────────────────────────────────
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input. Override for terminal input."""
        if not self.buffer:
            return
        
        modifiers = event.modifiers()
        key = event.key()
        
        # Ctrl+C - copy selection
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_C:
            self._copy_selection()
            return
        
        # Navigation
        if key == Qt.Key.Key_Up:
            self.buffer.scroll_by(-1)
        elif key == Qt.Key.Key_Down:
            self.buffer.scroll_by(1)
        elif key == Qt.Key.Key_PageUp:
            self.buffer.scroll_page(-1)
        elif key == Qt.Key.Key_PageDown:
            self.buffer.scroll_page(1)
        elif key == Qt.Key.Key_Home:
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                self.buffer.scroll_to_top()
        elif key == Qt.Key.Key_End:
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                self.buffer.scroll_to_bottom()
        elif key == Qt.Key.Key_Escape:
            self.buffer.clear_selection()
        else:
            super().keyPressEvent(event)
            return
        
        self._emit_scroll_state()
        self.update()
    
    def _copy_selection(self):
        """Copy selected text to clipboard."""
        if self.buffer:
            text = self.buffer.get_selected_text()
            if text:
                QApplication.clipboard().setText(text)
                self.selection_changed.emit(f"Copied {len(text)} chars")
    
    # ─────────────────────────────────────────────────────────
    # Mouse input
    # ─────────────────────────────────────────────────────────
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for scrolling."""
        if not self.buffer:
            return
        
        delta = event.angleDelta().y()
        lines = -delta // 40  # ~3 lines per notch
        
        self.buffer.scroll_by(lines)
        self._emit_scroll_state()
        self.update()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Start selection on mouse press."""
        if not self.buffer:
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            row, col = self.pixel_to_cell(int(event.position().x()), 
                                          int(event.position().y()))
            self.buffer.start_selection(row, col)
            self._mouse_pressed = True
            self._last_mouse_row = row
            self._last_mouse_col = col
            self.update()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Update selection on mouse drag."""
        if not self.buffer or not self._mouse_pressed:
            return
        
        y = int(event.position().y())
        x = int(event.position().x())
        
        # Check if we need to auto-scroll
        if y < 0:
            self._scroll_direction = -1
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        elif y >= self.height():
            self._scroll_direction = 1
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_direction = 0
            self._scroll_timer.stop()
        
        row, col = self.pixel_to_cell(x, y)
        
        # Clamp row to valid range for selection update
        row = max(0, min(row, self.rows - 1))
        
        if row != self._last_mouse_row or col != self._last_mouse_col:
            self.buffer.update_selection(row, col)
            self._last_mouse_row = row
            self._last_mouse_col = col
            self.update()
    
    def _auto_scroll_tick(self):
        """Called by timer during edge-drag to scroll and extend selection."""
        if not self.buffer or self._scroll_direction == 0:
            self._scroll_timer.stop()
            return
        
        # Scroll
        self.buffer.scroll_by(self._scroll_direction)
        
        # Extend selection to edge
        if self._scroll_direction < 0:
            # Scrolling up - select top row
            self.buffer.update_selection(0, self._last_mouse_col)
        else:
            # Scrolling down - select bottom row
            self.buffer.update_selection(self.rows - 1, self._last_mouse_col)
        
        self._emit_scroll_state()
        self.update()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """End selection on mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pressed = False
            self._scroll_timer.stop()
            self._scroll_direction = 0
            if self.buffer:
                self.buffer.end_selection()
                text = self.buffer.get_selected_text()
                if text:
                    self.selection_changed.emit(f"Selected {len(text)} chars")
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Select word on double-click."""
        # TODO: Implement word selection
        pass
    
    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────
    
    def set_scroll_position(self, offset: int):
        """Set scroll position (from scrollbar)."""
        if self.buffer:
            self.buffer.scroll_to(offset)
            self.update()
    
    def get_selected_text(self) -> str:
        """Get currently selected text."""
        if self.buffer:
            return self.buffer.get_selected_text()
        return ""
    
    def copy_selection(self) -> str:
        """Copy selected text to clipboard and return it."""
        text = self.get_selected_text()
        if text:
            QApplication.clipboard().setText(text)
        return text
