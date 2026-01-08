"""
Terminal Widget - GPU-accelerated terminal emulator.
Extends GPUTextWidget with PTY process and pyte-based terminal emulation.
"""

import os
import sys
from typing import Optional

from PyQt6.QtCore import Qt, QSocketNotifier, pyqtSignal
from PyQt6.QtGui import QKeyEvent

from .text_widget import GPUTextWidget
from .pyte_buffer import PyteTerminalBuffer
from .pty_process import UnixPty, PtySize


class TerminalWidget(GPUTextWidget):
    """
    Terminal emulator widget with PTY backend.
    
    Signals:
        title_changed: Window title from escape sequence (future)
        bell: Terminal bell triggered
        closed: PTY process exited
    """
    
    title_changed = pyqtSignal(str)
    bell = pyqtSignal()
    closed = pyqtSignal(int)  # exit code
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # PTY process
        self._pty: Optional[UnixPty] = None
        self._notifier: Optional[QSocketNotifier] = None
        
        # Shell to spawn
        self._shell = os.environ.get('SHELL', '/bin/bash')
        self._cwd = os.environ.get('HOME', os.getcwd())
        
        # State
        self._started = False
    
    def start(self, shell: str = None, cwd: str = None, env: dict = None):
        """
        Start terminal with shell process.
        
        Args:
            shell: Shell path (default: $SHELL)
            cwd: Working directory (default: $HOME)
            env: Additional environment variables
        """
        if self._started:
            return
        
        if shell:
            self._shell = shell
        if cwd:
            self._cwd = cwd
        
        # Create PTY
        self._pty = UnixPty()
        
        # Spawn shell
        size = PtySize(rows=self.rows, cols=self.cols)
        argv = [self._shell, '-l']  # Login shell
        
        if not self._pty.spawn(argv, cwd=self._cwd, env=env, size=size):
            raise RuntimeError(f"Failed to spawn: {self._shell}")
        
        # Set up read notifier
        self._notifier = QSocketNotifier(
            self._pty.fd, 
            QSocketNotifier.Type.Read,
            self
        )
        self._notifier.activated.connect(self._on_pty_read)
        
        self._started = True
    
    def _on_pty_read(self):
        """Called when PTY has data to read."""
        if not self._pty:
            return
        
        # Check if process still alive
        if not self._pty.is_alive:
            self._on_pty_closed()
            return
        
        # Read available data
        data = self._pty.read(65536)  # Read up to 64KB
        
        if data:
            # Feed to terminal emulator
            if isinstance(self.buffer, PyteTerminalBuffer):
                self.buffer.feed(data)
                self._emit_scroll_state()
                self.update()
    
    def _on_pty_closed(self):
        """Handle PTY process exit."""
        if self._notifier:
            self._notifier.setEnabled(False)
            self._notifier = None
        
        exit_code = self._pty.exit_code if self._pty else -1
        self._pty = None
        self._started = False
        
        # Append exit message
        if isinstance(self.buffer, PyteTerminalBuffer):
            msg = f"\n[Process exited with code {exit_code}]\n"
            self.buffer.feed(msg.encode())
            self.update()
        
        self.closed.emit(exit_code)
    
    def write(self, data: bytes):
        """Write data to PTY."""
        if self._pty and self._pty.is_alive:
            self._pty.write(data)
    
    def send_text(self, text: str):
        """Send text to PTY."""
        self.write(text.encode('utf-8'))
    
    # ─────────────────────────────────────────────────────────
    # Override base class methods
    # ─────────────────────────────────────────────────────────
    
    def initializeGL(self):
        """Initialize OpenGL and terminal buffer."""
        # Call parent to set up renderer
        from OpenGL.GL import glClearColor
        glClearColor(0.12, 0.12, 0.12, 1.0)
        
        from .gpu_renderer import GridRenderer
        self.renderer = GridRenderer(self)
        self.renderer.initialize(self.get_font())
        
        self._calculate_grid_size()
        
        # Use pyte-backed terminal buffer
        self.buffer = PyteTerminalBuffer(self.rows, self.cols)
        
        # Show startup message
        self.buffer.feed(b"Terminal initialized. Starting shell...\r\n")
        
        # Auto-start shell
        try:
            self.start()
        except Exception as e:
            self.buffer.feed(f"Error: {e}\r\n".encode())
    
    def _load_initial_content(self):
        """Override - terminal doesn't load file content."""
        pass
    
    def _on_grid_resized(self):
        """Handle grid resize - notify PTY and buffer."""
        if self._pty and self._pty.is_alive:
            self._pty.set_size(self.rows, self.cols)
        
        # Resize buffer
        if isinstance(self.buffer, PyteTerminalBuffer):
            self.buffer.resize(self.rows, self.cols)
            self._emit_scroll_state()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input - send to PTY."""
        if not self._pty or not self._pty.is_alive:
            # Fall back to viewer navigation if no PTY
            super().keyPressEvent(event)
            return
        
        modifiers = event.modifiers()
        key = event.key()
        
        # Ctrl+Shift+C - copy (don't send to terminal)
        if (modifiers == (Qt.KeyboardModifier.ControlModifier | 
                         Qt.KeyboardModifier.ShiftModifier) and 
            key == Qt.Key.Key_C):
            self._copy_selection()
            return
        
        # Ctrl+Shift+V - paste
        if (modifiers == (Qt.KeyboardModifier.ControlModifier | 
                         Qt.KeyboardModifier.ShiftModifier) and 
            key == Qt.Key.Key_V):
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            if text:
                self.send_text(text)
            return
        
        # Convert key to terminal sequence
        seq = self._key_to_sequence(event)
        if seq:
            self.write(seq)
    
    def _key_to_sequence(self, event: QKeyEvent) -> Optional[bytes]:
        """Convert Qt key event to terminal escape sequence."""
        modifiers = event.modifiers()
        key = event.key()
        text = event.text()
        
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        # Special keys
        key_map = {
            Qt.Key.Key_Return: b'\r',
            Qt.Key.Key_Enter: b'\r',
            Qt.Key.Key_Backspace: b'\x7f',  # DEL
            Qt.Key.Key_Tab: b'\t',
            Qt.Key.Key_Escape: b'\x1b',
            
            # Arrow keys
            Qt.Key.Key_Up: b'\x1b[A',
            Qt.Key.Key_Down: b'\x1b[B',
            Qt.Key.Key_Right: b'\x1b[C',
            Qt.Key.Key_Left: b'\x1b[D',
            
            # Navigation
            Qt.Key.Key_Home: b'\x1b[H',
            Qt.Key.Key_End: b'\x1b[F',
            Qt.Key.Key_PageUp: b'\x1b[5~',
            Qt.Key.Key_PageDown: b'\x1b[6~',
            Qt.Key.Key_Insert: b'\x1b[2~',
            Qt.Key.Key_Delete: b'\x1b[3~',
            
            # Function keys
            Qt.Key.Key_F1: b'\x1bOP',
            Qt.Key.Key_F2: b'\x1bOQ',
            Qt.Key.Key_F3: b'\x1bOR',
            Qt.Key.Key_F4: b'\x1bOS',
            Qt.Key.Key_F5: b'\x1b[15~',
            Qt.Key.Key_F6: b'\x1b[17~',
            Qt.Key.Key_F7: b'\x1b[18~',
            Qt.Key.Key_F8: b'\x1b[19~',
            Qt.Key.Key_F9: b'\x1b[20~',
            Qt.Key.Key_F10: b'\x1b[21~',
            Qt.Key.Key_F11: b'\x1b[23~',
            Qt.Key.Key_F12: b'\x1b[24~',
        }
        
        if key in key_map:
            seq = key_map[key]
            # Add modifiers for arrow keys etc
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, 
                       Qt.Key.Key_Left, Qt.Key.Key_Right):
                if ctrl or alt or shift:
                    # CSI 1 ; modifier code
                    mod = 1
                    if shift: mod += 1
                    if alt: mod += 2
                    if ctrl: mod += 4
                    base = seq[2:3]  # A, B, C, or D
                    seq = f'\x1b[1;{mod}{base.decode()}'.encode()
            return seq
        
        # Ctrl+letter -> control character
        if ctrl and not alt and not shift:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                # Ctrl+A = 0x01, Ctrl+Z = 0x1A
                return bytes([key - Qt.Key.Key_A + 1])
            # Special ctrl combos
            if key == Qt.Key.Key_Space:
                return b'\x00'
            if key == Qt.Key.Key_BracketLeft:
                return b'\x1b'
            if key == Qt.Key.Key_Backslash:
                return b'\x1c'
            if key == Qt.Key.Key_BracketRight:
                return b'\x1d'
        
        # Alt+key -> ESC + key
        if alt and text:
            return b'\x1b' + text.encode('utf-8')
        
        # Regular text
        if text:
            return text.encode('utf-8')
        
        return None
    
    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────
    
    def terminate(self):
        """Terminate the shell process."""
        if self._pty:
            self._pty.terminate()
    
    def kill(self):
        """Kill the shell process."""
        if self._pty:
            self._pty.kill()
    
    @property
    def is_running(self) -> bool:
        """Check if shell is running."""
        return self._pty is not None and self._pty.is_alive
    
    def closeEvent(self, event):
        """Clean up on widget close."""
        if self._notifier:
            self._notifier.setEnabled(False)
        if self._pty:
            self._pty.terminate()
        super().closeEvent(event)
