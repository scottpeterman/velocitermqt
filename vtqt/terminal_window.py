"""
Terminal Window - Main window for terminal emulator mode.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollBar, QFrame, QApplication
)

from .terminal_widget import TerminalWidget


class TerminalWindow(QMainWindow):
    """Main window for terminal emulator."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("VelociTermQt")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #333;")
        layout.addWidget(sep)
        
        # Terminal area
        term_layout = QHBoxLayout()
        term_layout.setContentsMargins(0, 0, 0, 0)
        term_layout.setSpacing(0)
        
        # Terminal widget
        self.terminal = TerminalWidget()
        self.terminal.scroll_changed.connect(self._on_scroll_changed)
        self.terminal.selection_changed.connect(self._on_selection_changed)
        self.terminal.closed.connect(self._on_terminal_closed)
        term_layout.addWidget(self.terminal, 1)  # stretch factor
        
        # Scrollbar
        self.scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        term_layout.addWidget(self.scrollbar)
        
        layout.addLayout(term_layout, 1)  # stretch factor - fill available space
        
        # Status bar
        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet("color: #888; padding: 4px 8px;")
        layout.addWidget(self.status_label)
        
        # Apply dark theme
        self._apply_dark_theme()
    
    def _create_toolbar(self) -> QHBoxLayout:
        """Create toolbar with buttons."""
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 8)
        
        copy_btn = QPushButton("Copy (Ctrl+Shift+C)")
        copy_btn.clicked.connect(self._copy_selection)
        toolbar.addWidget(copy_btn)
        
        paste_btn = QPushButton("Paste (Ctrl+Shift+V)")
        paste_btn.clicked.connect(self._paste)
        toolbar.addWidget(paste_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_terminal)
        toolbar.addWidget(clear_btn)
        
        toolbar.addStretch()
        
        return toolbar
    
    def _apply_dark_theme(self):
        """Apply dark color scheme."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 14px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #5a5a5a;
                border-radius: 7px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6a6a6a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QFrame[frameShape="4"] {
                background-color: #333;
                max-height: 1px;
            }
        """)
    
    def _copy_selection(self):
        """Copy selected text."""
        text = self.terminal.copy_selection()
        if text:
            self.status_label.setText(f"Copied {len(text)} characters")
        else:
            self.status_label.setText("No text selected")
    
    def _paste(self):
        """Paste from clipboard."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.terminal.send_text(text)
            self.status_label.setText(f"Pasted {len(text)} characters")
    
    def _clear_terminal(self):
        """Clear terminal buffer."""
        if hasattr(self.terminal, 'buffer') and self.terminal.buffer:
            self.terminal.buffer.clear()
            self.terminal.update()
            self.status_label.setText("Cleared")
    
    def _on_scroll_changed(self, offset: int, max_offset: int):
        """Update scrollbar when terminal scrolls."""
        self.scrollbar.blockSignals(True)
        self.scrollbar.setMaximum(max_offset)
        self.scrollbar.setValue(offset)
        self.scrollbar.blockSignals(False)
    
    def _on_scrollbar_changed(self, value: int):
        """Handle scrollbar changes."""
        self.terminal.set_scroll_position(value)
    
    def _on_selection_changed(self, msg: str):
        """Update status on selection change."""
        self.status_label.setText(msg)
    
    def _on_terminal_closed(self, exit_code: int):
        """Handle terminal process exit."""
        self.status_label.setText(f"Process exited (code {exit_code})")
        self.setWindowTitle("VelociTermQt - [Exited]")
    
    def closeEvent(self, event):
        """Clean up terminal on close."""
        if self.terminal.is_running:
            self.terminal.terminate()
        super().closeEvent(event)


def main():
    """Entry point for terminal mode."""
    import sys
    
    app = QApplication(sys.argv)
    app.setApplicationName("VelociTermQt")
    
    window = TerminalWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
