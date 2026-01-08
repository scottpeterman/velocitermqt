"""
Main Window - Application chrome, toolbar, scrollbar, file dialogs.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QScrollBar, QFrame
)

from .text_widget import GPUTextWidget


class TextViewerWindow(QMainWindow):
    """Main window with text viewer and controls."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("GPU Text Viewer - Terminal Rendering PoC")
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
        
        # Text view area
        view_layout = QHBoxLayout()
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)
        
        # GPU text widget
        self.text_widget = GPUTextWidget()
        self.text_widget.scroll_changed.connect(self._on_scroll_changed)
        self.text_widget.selection_changed.connect(self._on_selection_changed)
        view_layout.addWidget(self.text_widget)
        
        # Scrollbar
        self.scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        view_layout.addWidget(self.scrollbar)
        
        layout.addLayout(view_layout)
        
        # Status bar
        self.scroll_label = QLabel("Line 0 / 0")
        self.scroll_label.setStyleSheet("color: #888; padding: 4px 8px;")
        layout.addWidget(self.scroll_label)
        
        # Apply dark theme
        self._apply_dark_theme()
    
    def _create_toolbar(self) -> QHBoxLayout:
        """Create toolbar with buttons."""
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 8)
        
        open_btn = QPushButton("Open File (Ctrl+O)")
        open_btn.clicked.connect(self._open_file)
        toolbar.addWidget(open_btn)
        
        copy_btn = QPushButton("Copy Selection (Ctrl+C)")
        copy_btn.clicked.connect(self._copy_selection)
        toolbar.addWidget(copy_btn)
        
        toolbar.addStretch()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.status_label)
        
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
    
    def _open_file(self):
        """Open file dialog."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "All Files (*);;Text Files (*.txt);;Python (*.py);;C/C++ (*.c *.cpp *.h)"
        )
        if filepath:
            self.text_widget.load_file(filepath)
            self.setWindowTitle(f"GPU Text Viewer - {Path(filepath).name}")
            self.status_label.setText(f"Loaded: {filepath}")
    
    def _copy_selection(self):
        """Copy selected text."""
        text = self.text_widget.copy_selection()
        if text:
            self.status_label.setText(f"Copied {len(text)} characters")
        else:
            self.status_label.setText("No text selected")
    
    def _on_scroll_changed(self, offset: int, max_offset: int):
        """Update scrollbar when text view scrolls."""
        self.scrollbar.blockSignals(True)
        self.scrollbar.setMaximum(max_offset)
        self.scrollbar.setValue(offset)
        self.scrollbar.blockSignals(False)
        
        self.scroll_label.setText(f"Line {offset + 1} / {max_offset + 1}")
    
    def _on_scrollbar_changed(self, value: int):
        """Handle scrollbar changes."""
        self.text_widget.set_scroll_position(value)
    
    def _on_selection_changed(self, msg: str):
        """Update status on selection change."""
        self.status_label.setText(msg)
    
    def keyPressEvent(self, event):
        """Handle window-level keyboard shortcuts."""
        modifiers = event.modifiers()
        key = event.key()
        
        # Ctrl+O - open file
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_O:
            self._open_file()
            return
        
        super().keyPressEvent(event)
