"""
Terminal Window - Main window for terminal emulator with SSH support.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollBar, QFrame, QMessageBox,
    QApplication
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
        self._ssh_info = None  # Store connection info

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

    # ─────────────────────────────────────────────────────────────────────────
    # SSH Connection
    # ─────────────────────────────────────────────────────────────────────────

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
        from .ssh_session import SSHSession, SSHAuthError, SSHConnectionError
        from .pty_process import PtySize

        size = PtySize(rows=self.terminal.rows, cols=self.terminal.cols)

        # Show connecting status
        self.status_label.setText(f"Connecting to {info.get_display_name()}...")
        self.ssh_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            session = SSHSession()

            # Build connection kwargs from SSHConnectionInfo
            connect_kwargs = {
                'host': info.host,
                'port': info.port,
                'username': info.username,
                'size': size,
                'auth_method': info.auth_method,
            }

            # Add auth-specific parameters
            if info.auth_method == "password":
                connect_kwargs['password'] = info.password
            elif info.auth_method == "key":
                connect_kwargs['key_filename'] = info.key_file
                if info.key_passphrase:
                    connect_kwargs['key_passphrase'] = info.key_passphrase
            elif info.auth_method == "agent":
                connect_kwargs['use_agent'] = True

            # Attempt connection
            session.connect(**connect_kwargs)

            # Success - stop local PTY
            if self.terminal._pty:
                self.terminal._pty.terminate()
            if self.terminal._notifier:
                self.terminal._notifier.setEnabled(False)
                self.terminal._notifier = None

            # Attach SSH session
            self.terminal._pty = session
            self.terminal._started = True
            self._is_ssh = True
            self._ssh_info = info

            # Start SSH polling timer
            if self._ssh_timer:
                self._ssh_timer.stop()
            self._ssh_timer = QTimer(self)
            self._ssh_timer.timeout.connect(self._poll_ssh)
            self._ssh_timer.start(10)  # 10ms polling

            # Update UI
            self.terminal.buffer.clear()

            # Show connection banner
            auth_desc = {
                "password": "password",
                "key": f"key ({info.key_file})" if info.key_file else "key",
                "agent": "SSH agent"
            }.get(info.auth_method, info.auth_method)

            banner = (
                f"\x1b[32mConnected to {info.host}:{info.port}\x1b[0m\r\n"
                f"\x1b[90mUser: {info.username} | Auth: {auth_desc}\x1b[0m\r\n"
                f"\x1b[90mServer: {session.get_server_banner()}\x1b[0m\r\n\r\n"
            )
            self.terminal.buffer.feed(banner.encode())

            self.setWindowTitle(f"VelociTermQt - {info.get_display_name()}")
            self.connection_label.setText(info.get_display_name())
            self.connection_label.setStyleSheet("color: #4a4; font-weight: bold;")
            self.status_label.setText(f"Connected to {info.get_display_name()}")

            # Show disconnect button, hide SSH button
            self.ssh_btn.setVisible(False)
            self.disconnect_btn.setVisible(True)

            self.terminal.update()

        except SSHAuthError as e:
            self._show_auth_error(info, str(e))
            self.status_label.setText("Authentication failed")

        except SSHConnectionError as e:
            QMessageBox.critical(
                self, "Connection Failed",
                f"Could not connect to {info.host}:{info.port}\n\n{e}"
            )
            self.status_label.setText("Connection failed")

        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Unexpected error:\n\n{e}"
            )
            self.status_label.setText("Connection failed")

        finally:
            self.ssh_btn.setEnabled(True)

    def _show_auth_error(self, info, error_msg: str):
        """Show authentication error with helpful details."""
        auth_help = {
            "password": (
                "• Check that the password is correct\n"
                "• Verify the username is correct\n"
                "• Some servers disable password auth"
            ),
            "key": (
                "• Check that the key file exists and is readable\n"
                "• Verify the key is authorized on the server\n"
                "• If the key is encrypted, check the passphrase"
            ),
            "agent": (
                "• Verify ssh-agent is running (ssh-add -l)\n"
                "• Check that your key is loaded in the agent\n"
                "• The server may not accept any of the agent keys"
            ),
        }

        help_text = auth_help.get(info.auth_method, "")

        QMessageBox.critical(
            self, "Authentication Failed",
            f"Could not authenticate to {info.host}\n\n"
            f"Method: {info.auth_method}\n"
            f"User: {info.username}\n\n"
            f"Error: {error_msg}\n\n"
            f"Suggestions:\n{help_text}"
        )

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
        self._ssh_info = None
        self._on_ssh_disconnected()

        # Start local shell
        self.terminal.buffer.clear()
        self.terminal.buffer.feed(b"\x1b[33mSSH disconnected.\x1b[0m\r\n")
        self.terminal.buffer.feed(b"Starting local shell...\r\n\r\n")
        self.terminal.update()

        try:
            self.terminal.start()
        except Exception as e:
            self.terminal.buffer.feed(f"\x1b[31mError starting shell: {e}\x1b[0m\r\n".encode())

    def _on_ssh_disconnected(self):
        """Handle SSH disconnection."""
        self._is_ssh = False
        self._ssh_info = None
        self.setWindowTitle("VelociTermQt")
        self.connection_label.setText("Local")
        self.connection_label.setStyleSheet("color: #888;")
        self.status_label.setText("Disconnected")

        # Show SSH button, hide disconnect button
        self.ssh_btn.setVisible(True)
        self.disconnect_btn.setVisible(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Terminal operations
    # ─────────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────────
    # Public API for programmatic SSH
    # ─────────────────────────────────────────────────────────────────────────

    def connect_ssh(self,
                    host: str,
                    port: int = 22,
                    username: str = None,
                    password: str = None,
                    key_file: str = None,
                    key_passphrase: str = None,
                    auth_method: str = None):
        """
        Connect to SSH programmatically.

        Args:
            host: Hostname or IP
            port: SSH port (default 22)
            username: Username (default: current user)
            password: Password for password auth
            key_file: Path to private key
            key_passphrase: Passphrase for encrypted key
            auth_method: Explicit auth method ("password", "key", "agent")
        """
        from .ssh_dialog import SSHConnectionInfo
        import os

        if username is None:
            username = os.environ.get('USER', '')

        if auth_method is None:
            if key_file:
                auth_method = "key"
            elif password:
                auth_method = "password"
            else:
                auth_method = "agent"

        info = SSHConnectionInfo(
            host=host,
            port=port,
            username=username,
            auth_method=auth_method,
            password=password or "",
            key_file=key_file or "",
            key_passphrase=key_passphrase or "",
        )

        self._connect_ssh(info)