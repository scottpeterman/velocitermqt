"""
Terminal Window - Main window for terminal emulator with SSH support.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollBar, QFrame, QMessageBox
)

from .terminal_widget import TerminalWidget
from .gpu_renderer import CursorStyle


class TerminalWindow(QMainWindow):
    """Main window with terminal emulator and controls."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("VelociTermQt")
        self.setMinimumSize(800, 600)

        # SSH polling timer
        self._ssh_timer = None
        self._is_ssh = False

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self.toolbar = self._create_toolbar()
        layout.addLayout(self.toolbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #333;")
        layout.addWidget(sep)

        # Terminal area
        view_layout = QHBoxLayout()
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)

        # Terminal widget
        self.terminal = TerminalWidget()
        self.terminal.scroll_changed.connect(self._on_scroll_changed)
        self.terminal.selection_changed.connect(self._on_selection_changed)
        self.terminal.closed.connect(self._on_terminal_closed)
        view_layout.addWidget(self.terminal)

        # Scrollbar
        self.scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        view_layout.addWidget(self.scrollbar)

        layout.addLayout(view_layout)

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

        # Copy button
        copy_btn = QPushButton("Copy (Ctrl+Shift+C)")
        copy_btn.clicked.connect(self._copy_selection)
        toolbar.addWidget(copy_btn)

        # Paste button
        paste_btn = QPushButton("Paste (Ctrl+Shift+V)")
        paste_btn.clicked.connect(self._paste)
        toolbar.addWidget(paste_btn)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_terminal)
        toolbar.addWidget(clear_btn)

        # Separator
        toolbar.addSpacing(20)

        # SSH button
        self.ssh_btn = QPushButton("SSH Connect")
        self.ssh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5a2d;
                border: 1px solid #3d7a3d;
            }
            QPushButton:hover {
                background-color: #3d7a3d;
            }
            QPushButton:pressed {
                background-color: #1d4a1d;
            }
        """)
        self.ssh_btn.clicked.connect(self._open_ssh_dialog)
        toolbar.addWidget(self.ssh_btn)

        # Disconnect button (hidden initially)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a2d2d;
                border: 1px solid #7a3d3d;
            }
            QPushButton:hover {
                background-color: #7a3d3d;
            }
            QPushButton:pressed {
                background-color: #4a1d1d;
            }
        """)
        self.disconnect_btn.clicked.connect(self._disconnect_ssh)
        self.disconnect_btn.setVisible(False)
        toolbar.addWidget(self.disconnect_btn)

        toolbar.addStretch()

        # Connection status
        self.connection_label = QLabel("Local")
        self.connection_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.connection_label)

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

    # ─────────────────────────────────────────────────────────────
    # SSH Connection
    # ─────────────────────────────────────────────────────────────

    def _open_ssh_dialog(self):
        """Open SSH connection dialog."""
        try:
            from .ssh_dialog import SSHConnectionDialog
            from .ssh_session import check_paramiko_available
        except ImportError as e:
            QMessageBox.warning(
                self, "Error",
                f"SSH modules not found: {e}\n\n"
                "Make sure ssh_dialog.py and ssh_session.py are in vtqt/"
            )
            return

        if not check_paramiko_available():
            QMessageBox.warning(
                self, "Missing Dependency",
                "paramiko is required for SSH.\n\n"
                "Install with: pip install paramiko"
            )
            return

        dialog = SSHConnectionDialog(self)
        if dialog.exec():
            info = dialog.get_connection_info()
            if info:
                self._connect_ssh(info)

    def _connect_ssh(self, info):
        """Establish SSH connection."""
        from .ssh_session import SSHSession
        from .pty_process import PtySize

        size = PtySize(rows=self.terminal.rows, cols=self.terminal.cols)

        # Show connecting status
        self.status_label.setText(f"Connecting to {info.display_name()}...")
        self.ssh_btn.setEnabled(False)

        # Process events to update UI
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            session = SSHSession()

            connect_kwargs = {
                'host': info.host,
                'port': info.port,
                'username': info.username,
                'size': size,
            }

            if info.auth_method == "password":
                connect_kwargs['password'] = info.password
            elif info.auth_method == "key":
                connect_kwargs['key_filename'] = info.key_file
                connect_kwargs['key_passphrase'] = info.key_passphrase
            else:  # agent
                connect_kwargs['use_agent'] = True

            session.connect(**connect_kwargs)

            # Stop local PTY
            if self.terminal._pty:
                self.terminal._pty.terminate()
            if self.terminal._notifier:
                self.terminal._notifier.setEnabled(False)
                self.terminal._notifier = None

            # Attach SSH session
            self.terminal._pty = session
            self.terminal._started = True
            self._is_ssh = True

            # Start SSH polling timer
            if self._ssh_timer:
                self._ssh_timer.stop()
            self._ssh_timer = QTimer(self)
            self._ssh_timer.timeout.connect(self._poll_ssh)
            self._ssh_timer.start(10)  # 10ms polling

            # Update UI
            self.terminal.buffer.clear()
            self.terminal.buffer.feed(
                f"Connected to {info.display_name()}\r\n".encode()
            )
            self.setWindowTitle(f"VelociTermQt - {info.display_name()}")
            self.connection_label.setText(info.display_name())
            self.connection_label.setStyleSheet("color: #4a4; font-weight: bold;")
            self.status_label.setText(f"Connected to {info.display_name()}")

            # Show disconnect button, hide SSH button
            self.ssh_btn.setVisible(False)
            self.disconnect_btn.setVisible(True)

            self.terminal.update()

        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", str(e))
            self.status_label.setText("Connection failed")
        finally:
            self.ssh_btn.setEnabled(True)

    def _poll_ssh(self):
        """Poll SSH session for data."""
        if not self.terminal._pty or not self.terminal._pty.is_alive:
            if self._ssh_timer:
                self._ssh_timer.stop()
            self._on_ssh_disconnected()
            return

        data = self.terminal._pty.read(65536)
        if data:
            self.terminal.buffer.feed(data)
            self.terminal._emit_scroll_state()
            self.terminal.update()

    def _disconnect_ssh(self):
        """Disconnect SSH and return to local shell."""
        if self._ssh_timer:
            self._ssh_timer.stop()
            self._ssh_timer = None

        if self.terminal._pty:
            self.terminal._pty.close()
            self.terminal._pty = None

        self._is_ssh = False
        self._on_ssh_disconnected()

        # Start local shell
        self.terminal.buffer.clear()
        self.terminal.buffer.feed(b"SSH disconnected. Starting local shell...\r\n")
        self.terminal.update()

        try:
            self.terminal.start()
        except Exception as e:
            self.terminal.buffer.feed(f"Error starting shell: {e}\r\n".encode())

    def _on_ssh_disconnected(self):
        """Handle SSH disconnection."""
        self._is_ssh = False
        self.setWindowTitle("VelociTermQt")
        self.connection_label.setText("Local")
        self.connection_label.setStyleSheet("color: #888;")
        self.status_label.setText("Disconnected")

        # Show SSH button, hide disconnect button
        self.ssh_btn.setVisible(True)
        self.disconnect_btn.setVisible(False)

    # ─────────────────────────────────────────────────────────────
    # Terminal operations
    # ─────────────────────────────────────────────────────────────

    def _copy_selection(self):
        """Copy selected text."""
        text = self.terminal.copy_selection()
        if text:
            self.status_label.setText(f"Copied {len(text)} characters")
        else:
            self.status_label.setText("No text selected")

    def _paste(self):
        """Paste from clipboard."""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text and self.terminal._pty:
            self.terminal.send_text(text)
            self.status_label.setText(f"Pasted {len(text)} characters")

    def _clear_terminal(self):
        """Clear terminal screen."""
        if self.terminal.buffer:
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
        if self._is_ssh:
            self._on_ssh_disconnected()
            self.status_label.setText(f"SSH session ended (exit code: {exit_code})")
        else:
            self.status_label.setText(f"Shell exited with code {exit_code}")

    def closeEvent(self, event):
        """Clean up on window close."""
        if self._ssh_timer:
            self._ssh_timer.stop()
        if self.terminal._pty:
            self.terminal._pty.terminate()
        super().closeEvent(event)