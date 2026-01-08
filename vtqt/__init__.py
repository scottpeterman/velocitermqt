"""
VelociTermQt - GPU-accelerated terminal emulator.

Part of the Velocity* tool family.
"""

__version__ = "0.3.0"
__author__ = "Scott Peterman"

from .terminal_buffer import TextBuffer, Cell, Line, CellAttr
from .pyte_buffer import PyteTerminalBuffer
from .text_widget import GPUTextWidget
from .terminal_widget import TerminalWidget
from .pty_process import UnixPty, PtyProcess, PtySize, spawn_shell

__all__ = [
    'TextBuffer',
    'Cell',
    'Line', 
    'CellAttr',
    'PyteTerminalBuffer',
    'GPUTextWidget',
    'TerminalWidget',
    'UnixPty',
    'PtyProcess',
    'PtySize',
    'spawn_shell',
]
