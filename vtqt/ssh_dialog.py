"""
SSH Connection Dialog - PyQt6 dialog for SSH connection parameters.

Supports:
- Host, port, username
- Password authentication
- Key file authentication
- SSH agent authentication
- Connection history (optional)
"""

import os
from typing import Optional, Tuple
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton,
    QCheckBox, QFileDialog, QGroupBox, QMessageBox,
    QDialogButtonBox, QTabWidget, QWidget, QListWidget,
    QListWidgetItem, QStackedWidget
)
from PyQt6.QtGui import QFont


@dataclass
class SSHConnectionInfo:
    """SSH connection parameters."""
    host: str
    port: int = 22
    username: str = ""
    auth_method: str = "password"  # "password", "key", "agent"
    password: str = ""
    key_file: str = ""
    key_passphrase: str = ""

    def display_name(self) -> str:
        """Human-readable connection name."""
        user_part = f"{self.username}@" if self.username else ""
        port_part = f":{self.port}" if self.port != 22 else ""
        return f"{user_part}{self.host}{port_part}"


class SSHConnectionDialog(QDialog):
    """
    Dialog for entering SSH connection parameters.

    Usage:
        dialog = SSHConnectionDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            info = dialog.get_connection_info()
            # Connect using info
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH Connection")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._connection_info: Optional[SSHConnectionInfo] = None
        self._setup_ui()
        self._load_recent()

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Main tab widget
        tabs = QTabWidget()
        tabs.addTab(self._create_connection_tab(), "Connection")
        tabs.addTab(self._create_recent_tab(), "Recent")
        layout.addWidget(tabs)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        # Custom connect button
        self._connect_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._connect_btn.setText("Connect")

        layout.addWidget(button_box)

    def _create_connection_tab(self) -> QWidget:
        """Create the main connection parameters tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Host group
        host_group = QGroupBox("Server")
        host_layout = QGridLayout(host_group)

        host_layout.addWidget(QLabel("Host:"), 0, 0)
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("hostname or IP address")
        host_layout.addWidget(self._host_edit, 0, 1)

        host_layout.addWidget(QLabel("Port:"), 0, 2)
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        self._port_spin.setFixedWidth(80)
        host_layout.addWidget(self._port_spin, 0, 3)

        host_layout.addWidget(QLabel("Username:"), 1, 0)
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText(os.environ.get('USER', 'username'))
        host_layout.addWidget(self._username_edit, 1, 1, 1, 3)

        layout.addWidget(host_group)

        # Authentication group
        auth_group = QGroupBox("Authentication")
        auth_layout = QVBoxLayout(auth_group)

        # Auth method selector
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Method:"))
        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["Password", "Key File", "SSH Agent"])
        self._auth_combo.currentIndexChanged.connect(self._on_auth_method_changed)
        method_layout.addWidget(self._auth_combo)
        method_layout.addStretch()
        auth_layout.addLayout(method_layout)

        # Stacked widget for auth-specific fields
        self._auth_stack = QStackedWidget()

        # Password page
        password_page = QWidget()
        password_layout = QGridLayout(password_page)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.addWidget(QLabel("Password:"), 0, 0)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(self._password_edit, 0, 1)
        self._auth_stack.addWidget(password_page)

        # Key file page
        key_page = QWidget()
        key_layout = QGridLayout(key_page)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(QLabel("Key File:"), 0, 0)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("~/.ssh/id_rsa")
        key_layout.addWidget(self._key_edit, 0, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key_file)
        key_layout.addWidget(browse_btn, 0, 2)
        key_layout.addWidget(QLabel("Passphrase:"), 1, 0)
        self._passphrase_edit = QLineEdit()
        self._passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase_edit.setPlaceholderText("(leave empty if none)")
        key_layout.addWidget(self._passphrase_edit, 1, 1, 1, 2)
        self._auth_stack.addWidget(key_page)

        # Agent page
        agent_page = QWidget()
        agent_layout = QVBoxLayout(agent_page)
        agent_layout.setContentsMargins(0, 0, 0, 0)
        agent_label = QLabel("Will use keys from running SSH agent (ssh-agent)")
        agent_label.setStyleSheet("color: gray; font-style: italic;")
        agent_layout.addWidget(agent_label)
        agent_layout.addStretch()
        self._auth_stack.addWidget(agent_page)

        auth_layout.addWidget(self._auth_stack)
        layout.addWidget(auth_group)

        layout.addStretch()

        return widget

    def _create_recent_tab(self) -> QWidget:
        """Create the recent connections tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._recent_list = QListWidget()
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_click)
        layout.addWidget(self._recent_list)

        btn_layout = QHBoxLayout()

        use_btn = QPushButton("Use Selected")
        use_btn.clicked.connect(self._on_use_recent)
        btn_layout.addWidget(use_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_recent)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._on_clear_recent)
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)

        return widget

    def _on_auth_method_changed(self, index: int):
        """Handle auth method combo change."""
        self._auth_stack.setCurrentIndex(index)

    def _browse_key_file(self):
        """Open file dialog to select SSH key."""
        ssh_dir = os.path.expanduser("~/.ssh")
        if not os.path.isdir(ssh_dir):
            ssh_dir = os.path.expanduser("~")

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SSH Private Key",
            ssh_dir,
            "All Files (*)"
        )
        if path:
            self._key_edit.setText(path)

    def _on_accept(self):
        """Validate and accept the dialog."""
        host = self._host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Error", "Please enter a host.")
            self._host_edit.setFocus()
            return

        username = self._username_edit.text().strip()
        if not username:
            username = os.environ.get('USER', '')

        auth_method = ["password", "key", "agent"][self._auth_combo.currentIndex()]

        if auth_method == "key":
            key_file = self._key_edit.text().strip()
            if not key_file:
                key_file = os.path.expanduser("~/.ssh/id_rsa")
            key_file = os.path.expanduser(key_file)
            if not os.path.isfile(key_file):
                QMessageBox.warning(
                    self, "Error",
                    f"Key file not found: {key_file}"
                )
                return
        else:
            key_file = ""

        self._connection_info = SSHConnectionInfo(
            host=host,
            port=self._port_spin.value(),
            username=username,
            auth_method=auth_method,
            password=self._password_edit.text() if auth_method == "password" else "",
            key_file=key_file,
            key_passphrase=self._passphrase_edit.text() if auth_method == "key" else "",
        )

        # Save to recent
        self._save_recent()

        self.accept()

    def get_connection_info(self) -> Optional[SSHConnectionInfo]:
        """Get the connection info after dialog is accepted."""
        return self._connection_info

    # ─────────────────────────────────────────────────────────
    # Recent connections persistence
    # ─────────────────────────────────────────────────────────

    def _load_recent(self):
        """Load recent connections from settings."""
        settings = QSettings("VelociTermQt", "SSHConnections")
        count = settings.beginReadArray("recent")

        for i in range(count):
            settings.setArrayIndex(i)
            host = settings.value("host", "")
            if host:
                item = QListWidgetItem(
                    f"{settings.value('username', '')}@{host}:{settings.value('port', 22)}"
                )
                item.setData(Qt.ItemDataRole.UserRole, {
                    'host': host,
                    'port': int(settings.value('port', 22)),
                    'username': settings.value('username', ''),
                    'auth_method': settings.value('auth_method', 'password'),
                    'key_file': settings.value('key_file', ''),
                })
                self._recent_list.addItem(item)

        settings.endArray()

    def _save_recent(self):
        """Save current connection to recent list."""
        if not self._connection_info:
            return

        settings = QSettings("VelociTermQt", "SSHConnections")

        # Load existing
        recent = []
        count = settings.beginReadArray("recent")
        for i in range(count):
            settings.setArrayIndex(i)
            recent.append({
                'host': settings.value('host', ''),
                'port': int(settings.value('port', 22)),
                'username': settings.value('username', ''),
                'auth_method': settings.value('auth_method', 'password'),
                'key_file': settings.value('key_file', ''),
            })
        settings.endArray()

        # Add new (remove duplicate if exists)
        new_entry = {
            'host': self._connection_info.host,
            'port': self._connection_info.port,
            'username': self._connection_info.username,
            'auth_method': self._connection_info.auth_method,
            'key_file': self._connection_info.key_file,
        }

        recent = [r for r in recent if not (
                r['host'] == new_entry['host'] and
                r['port'] == new_entry['port'] and
                r['username'] == new_entry['username']
        )]
        recent.insert(0, new_entry)
        recent = recent[:20]  # Keep last 20

        # Save
        settings.beginWriteArray("recent")
        for i, entry in enumerate(recent):
            settings.setArrayIndex(i)
            settings.setValue('host', entry['host'])
            settings.setValue('port', entry['port'])
            settings.setValue('username', entry['username'])
            settings.setValue('auth_method', entry['auth_method'])
            settings.setValue('key_file', entry['key_file'])
        settings.endArray()

    def _on_recent_double_click(self, item: QListWidgetItem):
        """Handle double-click on recent item."""
        self._use_recent_item(item)
        self._on_accept()

    def _on_use_recent(self):
        """Use selected recent connection."""
        item = self._recent_list.currentItem()
        if item:
            self._use_recent_item(item)

    def _use_recent_item(self, item: QListWidgetItem):
        """Populate fields from recent item."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self._host_edit.setText(data['host'])
            self._port_spin.setValue(data['port'])
            self._username_edit.setText(data['username'])

            method_idx = {'password': 0, 'key': 1, 'agent': 2}.get(
                data['auth_method'], 0
            )
            self._auth_combo.setCurrentIndex(method_idx)

            if data.get('key_file'):
                self._key_edit.setText(data['key_file'])

    def _on_remove_recent(self):
        """Remove selected recent connection."""
        row = self._recent_list.currentRow()
        if row >= 0:
            self._recent_list.takeItem(row)
            self._save_recent_list()

    def _on_clear_recent(self):
        """Clear all recent connections."""
        if QMessageBox.question(
                self, "Confirm",
                "Clear all recent connections?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._recent_list.clear()
            settings = QSettings("VelociTermQt", "SSHConnections")
            settings.remove("recent")

    def _save_recent_list(self):
        """Save the current recent list to settings."""
        settings = QSettings("VelociTermQt", "SSHConnections")
        settings.beginWriteArray("recent")

        for i in range(self._recent_list.count()):
            item = self._recent_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                settings.setArrayIndex(i)
                settings.setValue('host', data['host'])
                settings.setValue('port', data['port'])
                settings.setValue('username', data['username'])
                settings.setValue('auth_method', data['auth_method'])
                settings.setValue('key_file', data.get('key_file', ''))

        settings.endArray()