"""
SSH Connection Dialog - PyQt6 dialog for SSH connection parameters.

Supports:
- Session tree from sessions.yaml (folders + sessions)
- Credential lookup from credentials.yaml
- Manual connection entry
- Password, key file, and SSH agent authentication
- Full auth override capabilities
"""

import os
from typing import Optional
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton,
    QCheckBox, QFileDialog, QGroupBox, QMessageBox,
    QTabWidget, QWidget, QTreeWidget,
    QTreeWidgetItem, QStackedWidget, QSplitter, QMenu
)
from PyQt6.QtGui import QAction

from .config_manager import get_config, SessionInfo, Credential


@dataclass
class SSHConnectionInfo:
    """SSH connection parameters for connecting."""
    host: str
    port: int = 22
    username: str = ""
    auth_method: str = "password"  # "password", "key", "agent"
    password: str = ""
    key_file: str = ""
    key_passphrase: str = ""
    display_name: str = ""  # For window title

    # Source tracking (for debugging)
    auth_source: str = ""  # "credential", "session", "override", "manual"

    def get_display_name(self) -> str:
        """Human-readable connection name."""
        if self.display_name:
            return self.display_name
        user_part = f"{self.username}@" if self.username else ""
        port_part = f":{self.port}" if self.port != 22 else ""
        return f"{user_part}{self.host}{port_part}"

    def get_auth_summary(self) -> str:
        """Human-readable auth description."""
        if self.auth_method == "password":
            if self.password:
                return "Password: ●●●●●●●●"
            else:
                return "Password: (will prompt)"
        elif self.auth_method == "key":
            key_name = os.path.basename(self.key_file) if self.key_file else "(default keys)"
            return f"Key: {key_name}"
        else:
            return "SSH Agent"


@dataclass
class ResolvedAuth:
    """Resolved authentication from session + credential + override."""
    username: str = ""
    auth_method: str = "password"
    password: str = ""
    key_file: str = ""
    key_passphrase: str = ""
    source: str = ""  # Where the auth came from

    def get_warnings(self) -> list[str]:
        """Get non-blocking warnings about the auth config."""
        warnings = []

        if not self.username:
            warnings.append("No username - will use current user")

        if self.auth_method == "key" and self.key_file:
            expanded = os.path.expanduser(self.key_file)
            if not os.path.isfile(expanded):
                warnings.append(f"Key file not found: {self.key_file}")

        return warnings


class SSHConnectionDialog(QDialog):
    """
    Dialog for SSH connections with session manager integration.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH Connection")
        self.setMinimumSize(650, 520)
        self.setModal(True)

        self._connection_info: Optional[SSHConnectionInfo] = None
        self._selected_session: Optional[SessionInfo] = None
        self._resolved_auth: Optional[ResolvedAuth] = None

        self._setup_ui()
        self._apply_styling()
        self._load_sessions()

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Main tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_sessions_tab(), "Sessions")
        self.tabs.addTab(self._create_manual_tab(), "Manual")
        layout.addWidget(self.tabs)

        # Button box with custom styling
        button_layout = QHBoxLayout()

        # Left side - manager buttons
        self._manage_sessions_btn = QPushButton("📝 Sessions...")
        self._manage_sessions_btn.setToolTip("Manage saved sessions")
        self._manage_sessions_btn.clicked.connect(self._open_session_manager)
        button_layout.addWidget(self._manage_sessions_btn)

        self._manage_creds_btn = QPushButton("🔑 Credentials...")
        self._manage_creds_btn.setToolTip("Manage credentials")
        self._manage_creds_btn.clicked.connect(self._open_credential_manager)
        button_layout.addWidget(self._manage_creds_btn)

        button_layout.addStretch()

        self._cancel_btn = QPushButton("✕ Cancel")
        self._cancel_btn.setObjectName("cancelButton")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        self._connect_btn = QPushButton("✓ Connect")
        self._connect_btn.setObjectName("connectButton")
        self._connect_btn.clicked.connect(self._on_accept)
        self._connect_btn.setDefault(True)
        button_layout.addWidget(self._connect_btn)

        layout.addLayout(button_layout)

    def _apply_styling(self):
        """Apply dark theme styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #d4d4d4;
            }
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #d4d4d4;
                padding: 8px 16px;
                border: 1px solid #404040;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #2d2d2d;
                border-bottom: 1px solid #2d2d2d;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #404040;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px 8px;
                color: #d4d4d4;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #0078d4;
            }
            QLineEdit:disabled {
                background-color: #2a2a2a;
                color: #808080;
            }
            QTreeWidget {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 6px 16px;
                color: #d4d4d4;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QPushButton#connectButton {
                background-color: #2d5a2d;
                border-color: #3d7a3d;
            }
            QPushButton#connectButton:hover {
                background-color: #3d7a3d;
            }
            QPushButton#cancelButton {
                background-color: #5a2d2d;
                border-color: #7a3d3d;
            }
            QPushButton#cancelButton:hover {
                background-color: #7a3d3d;
            }
            QLabel#authSummary {
                color: #4ec9b0;
                font-family: monospace;
                padding: 4px;
                background-color: #1e1e1e;
                border-radius: 3px;
            }
            QLabel#authWarning {
                color: #cca700;
            }
        """)

    def _create_sessions_tab(self) -> QWidget:
        """Create the sessions tree tab."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # === Left side: Session tree ===
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        # Tree header
        tree_header = QHBoxLayout()
        tree_header.addWidget(QLabel("Saved Sessions:"))
        tree_header.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Reload sessions.yaml")
        refresh_btn.clicked.connect(self._load_sessions)
        tree_header.addWidget(refresh_btn)
        tree_layout.addLayout(tree_header)

        # Tree view
        self._session_tree = QTreeWidget()
        self._session_tree.setHeaderHidden(True)
        self._session_tree.setRootIsDecorated(True)
        self._session_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._session_tree.itemClicked.connect(self._on_session_selected)
        self._session_tree.itemDoubleClicked.connect(self._on_session_double_click)
        tree_layout.addWidget(self._session_tree)

        splitter.addWidget(tree_widget)

        # === Right side: Details + Auth ===
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        # Session details group
        details_group = QGroupBox("Session Details")
        details_grid = QGridLayout(details_group)
        details_grid.setColumnStretch(1, 1)

        row = 0
        for label_text, attr_name in [
            ("Name:", "_detail_name"),
            ("Host:", "_detail_host"),
            ("Port:", "_detail_port"),
            ("Type:", "_detail_type"),
            ("Device:", "_detail_device"),
            ("Credential:", "_detail_cred"),
        ]:
            details_grid.addWidget(QLabel(label_text), row, 0)
            label = QLabel("-")
            if attr_name == "_detail_name":
                label.setStyleSheet("font-weight: bold;")
            setattr(self, attr_name, label)
            details_grid.addWidget(label, row, 1)
            row += 1

        details_layout.addWidget(details_group)

        # Authentication Override group
        override_group = QGroupBox("Authentication Override")
        override_layout = QVBoxLayout(override_group)

        # Enable override checkbox
        self._override_enabled = QCheckBox("Override credential settings")
        self._override_enabled.toggled.connect(self._on_override_toggled)
        override_layout.addWidget(self._override_enabled)

        # Override fields container
        self._override_container = QWidget()
        override_fields = QGridLayout(self._override_container)
        override_fields.setContentsMargins(0, 8, 0, 0)

        # Username override
        override_fields.addWidget(QLabel("Username:"), 0, 0)
        self._override_username = QLineEdit()
        self._override_username.setPlaceholderText("(from credential)")
        self._override_username.textChanged.connect(self._update_auth_summary)
        override_fields.addWidget(self._override_username, 0, 1, 1, 2)

        # Auth method override
        override_fields.addWidget(QLabel("Method:"), 1, 0)
        self._override_method = QComboBox()
        self._override_method.addItems(["(from credential)", "Password", "Key File", "SSH Agent"])
        self._override_method.currentIndexChanged.connect(self._on_override_method_changed)
        override_fields.addWidget(self._override_method, 1, 1, 1, 2)

        # Password field
        self._override_password_label = QLabel("Password:")
        override_fields.addWidget(self._override_password_label, 2, 0)
        self._override_password = QLineEdit()
        self._override_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._override_password.setPlaceholderText("(leave empty to prompt)")
        self._override_password.textChanged.connect(self._update_auth_summary)
        override_fields.addWidget(self._override_password, 2, 1, 1, 2)

        # Key file field
        self._override_key_label = QLabel("Key File:")
        override_fields.addWidget(self._override_key_label, 3, 0)
        self._override_key = QLineEdit()
        self._override_key.setPlaceholderText("(default: ~/.ssh/id_*)")
        self._override_key.textChanged.connect(self._update_auth_summary)
        override_fields.addWidget(self._override_key, 3, 1)
        self._override_key_browse = QPushButton("...")
        self._override_key_browse.setFixedWidth(30)
        self._override_key_browse.clicked.connect(self._browse_override_key)
        override_fields.addWidget(self._override_key_browse, 3, 2)

        # Key passphrase
        self._override_passphrase_label = QLabel("Passphrase:")
        override_fields.addWidget(self._override_passphrase_label, 4, 0)
        self._override_passphrase = QLineEdit()
        self._override_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._override_passphrase.setPlaceholderText("(if key is encrypted)")
        override_fields.addWidget(self._override_passphrase, 4, 1, 1, 2)

        self._override_container.setVisible(False)
        override_layout.addWidget(self._override_container)

        details_layout.addWidget(override_group)

        # Resolved auth summary
        auth_summary_group = QGroupBox("Connection Will Use")
        auth_summary_layout = QVBoxLayout(auth_summary_group)

        self._auth_summary_label = QLabel("Select a session")
        self._auth_summary_label.setObjectName("authSummary")
        self._auth_summary_label.setWordWrap(True)
        auth_summary_layout.addWidget(self._auth_summary_label)

        self._auth_warning_label = QLabel("")
        self._auth_warning_label.setObjectName("authWarning")
        self._auth_warning_label.setWordWrap(True)
        self._auth_warning_label.setVisible(False)
        auth_summary_layout.addWidget(self._auth_warning_label)

        details_layout.addWidget(auth_summary_group)
        details_layout.addStretch()

        splitter.addWidget(details_widget)
        splitter.setSizes([250, 350])

        layout.addWidget(splitter)

        # Initial state
        self._on_override_method_changed(0)

        return widget

    def _create_manual_tab(self) -> QWidget:
        """Create manual connection entry tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

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
        password_layout.setContentsMargins(0, 8, 0, 0)
        password_layout.addWidget(QLabel("Password:"), 0, 0)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("(leave empty to prompt)")
        password_layout.addWidget(self._password_edit, 0, 1)
        password_layout.setColumnStretch(1, 1)
        self._auth_stack.addWidget(password_page)

        # Key file page
        key_page = QWidget()
        key_layout = QGridLayout(key_page)
        key_layout.setContentsMargins(0, 8, 0, 0)
        key_layout.addWidget(QLabel("Key File:"), 0, 0)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("(default: ~/.ssh/id_*)")
        key_layout.addWidget(self._key_edit, 0, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key_file)
        key_layout.addWidget(browse_btn, 0, 2)
        key_layout.addWidget(QLabel("Passphrase:"), 1, 0)
        self._passphrase_edit = QLineEdit()
        self._passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase_edit.setPlaceholderText("(if key is encrypted)")
        key_layout.addWidget(self._passphrase_edit, 1, 1, 1, 2)
        key_layout.setColumnStretch(1, 1)
        self._auth_stack.addWidget(key_page)

        # Agent page
        agent_page = QWidget()
        agent_layout = QVBoxLayout(agent_page)
        agent_layout.setContentsMargins(0, 8, 0, 0)
        agent_label = QLabel("Will use keys from running SSH agent (ssh-agent)\nAlso tries default keys in ~/.ssh/")
        agent_label.setStyleSheet("color: #808080; font-style: italic;")
        agent_layout.addWidget(agent_label)
        agent_layout.addStretch()
        self._auth_stack.addWidget(agent_page)

        auth_layout.addWidget(self._auth_stack)
        layout.addWidget(auth_group)

        layout.addStretch()

        return widget

    # ─────────────────────────────────────────────────────────────────────────
    # Session loading
    # ─────────────────────────────────────────────────────────────────────────

    def _load_sessions(self):
        """Load sessions from config into tree."""
        self._session_tree.clear()

        config = get_config()
        config.load_sessions()  # Reload from disk

        for folder in config.session_folders:
            folder_item = QTreeWidgetItem([f"📁 {folder.folder_name}"])
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder.folder_name))
            folder_item.setExpanded(False)

            for session in folder.sessions:
                session_text = session.display_name or session.host
                session_item = QTreeWidgetItem([f"  🖥 {session_text}"])
                session_item.setData(0, Qt.ItemDataRole.UserRole, ("session", session))
                session_item.setToolTip(0, f"{session.host}:{session.port}")
                folder_item.addChild(session_item)

            self._session_tree.addTopLevelItem(folder_item)

        # Show message if no sessions
        if not config.session_folders:
            empty_item = QTreeWidgetItem(["No sessions configured"])
            empty_item.setData(0, Qt.ItemDataRole.UserRole, None)
            empty_item.setDisabled(True)
            self._session_tree.addTopLevelItem(empty_item)

    def _on_tree_context_menu(self, pos):
        """Show context menu for session tree."""
        item = self._session_tree.itemAt(pos)
        menu = QMenu(self)

        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "session":
                session = data[1]
                edit_action = menu.addAction("✏️ Edit Session")
                edit_action.triggered.connect(lambda: self._edit_session(session))
                delete_action = menu.addAction("🗑️ Delete Session")
                delete_action.triggered.connect(lambda: self._delete_session(session))
                menu.addSeparator()

        add_session_action = menu.addAction("➕ Add Session")
        add_session_action.triggered.connect(self._add_session)
        add_folder_action = menu.addAction("📁 Add Folder")
        add_folder_action.triggered.connect(self._add_folder)

        menu.exec(self._session_tree.mapToGlobal(pos))

    # ─────────────────────────────────────────────────────────────────────────
    # Session selection handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_session_selected(self, item: QTreeWidgetItem, column: int):
        """Handle session selection in tree."""
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if data is None or data[0] == "folder":
            self._selected_session = None
            self._clear_session_details()
            return

        session = data[1]
        self._selected_session = session
        self._populate_session_details(session)
        self._update_auth_summary()

    def _clear_session_details(self):
        """Clear the session details panel."""
        self._detail_name.setText("-")
        self._detail_host.setText("-")
        self._detail_port.setText("-")
        self._detail_type.setText("-")
        self._detail_device.setText("-")
        self._detail_cred.setText("-")
        self._auth_summary_label.setText("Select a session")
        self._auth_warning_label.setVisible(False)
        self._resolved_auth = None

    def _populate_session_details(self, session: SessionInfo):
        """Populate session details panel."""
        self._detail_name.setText(session.display_name or session.host)
        self._detail_host.setText(session.host)
        self._detail_port.setText(str(session.port))
        self._detail_type.setText(session.DeviceType or "linux")

        # Device vendor/model
        device_str = ""
        if session.Vendor:
            device_str = session.Vendor
        if session.Model:
            device_str += f" {session.Model}" if device_str else session.Model
        self._detail_device.setText(device_str or "-")

        # Credential info
        config = get_config()
        cred = config.get_credential_for_session(session)
        if cred:
            auth_icon = {"password": "🔑", "key": "🔐", "agent": "🔓"}.get(cred.auth_method, "")
            self._detail_cred.setText(f"{auth_icon} {cred.name} ({cred.username})")
        elif session.username:
            self._detail_cred.setText(f"Direct: {session.username}")
        else:
            self._detail_cred.setText("(will use current user)")

    def _on_session_double_click(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on session - connect immediately."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "session":
            self._selected_session = data[1]
            self._on_accept()

    # ─────────────────────────────────────────────────────────────────────────
    # Override handling
    # ─────────────────────────────────────────────────────────────────────────

    def _on_override_toggled(self, enabled: bool):
        """Handle override checkbox toggle."""
        self._override_container.setVisible(enabled)
        self._update_auth_summary()

    def _on_override_method_changed(self, index: int):
        """Handle override auth method change."""
        # 0 = from credential, 1 = password, 2 = key, 3 = agent
        show_password = index in (0, 1)  # Show for "from cred" and "password"
        show_key = index == 2

        self._override_password_label.setVisible(show_password)
        self._override_password.setVisible(show_password)
        self._override_key_label.setVisible(show_key)
        self._override_key.setVisible(show_key)
        self._override_key_browse.setVisible(show_key)
        self._override_passphrase_label.setVisible(show_key)
        self._override_passphrase.setVisible(show_key)

        self._update_auth_summary()

    def _browse_override_key(self):
        """Browse for key file in override."""
        self._browse_key_file_to(self._override_key)

    # ─────────────────────────────────────────────────────────────────────────
    # Auth resolution - NO BLOCKING VALIDATION
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_auth(self) -> Optional[ResolvedAuth]:
        """Resolve authentication from session + credential + override."""
        if not self._selected_session:
            return None

        session = self._selected_session
        config = get_config()
        cred = config.get_credential_for_session(session)

        # Start with defaults
        auth = ResolvedAuth()
        auth.source = "default"
        auth.auth_method = "agent"  # Safe default - tries agent then keys

        # Layer 1: Session direct auth (if no credential)
        if session.username:
            auth.username = session.username
            auth.source = "session"
        if session.auth_method:
            auth.auth_method = session.auth_method
        if session.key_file:
            auth.key_file = session.key_file

        # Layer 2: Credential (overrides session)
        if cred:
            auth.username = cred.username
            auth.auth_method = cred.auth_method
            auth.password = cred.password
            auth.key_file = cred.key_file
            auth.key_passphrase = cred.key_passphrase
            auth.source = f"credential:{cred.name}"

        # Layer 3: Override (if enabled)
        if self._override_enabled.isChecked():
            override_username = self._override_username.text().strip()
            if override_username:
                auth.username = override_username
                auth.source = "override"

            override_method_idx = self._override_method.currentIndex()
            if override_method_idx > 0:  # Not "from credential"
                auth.auth_method = ["password", "key", "agent"][override_method_idx - 1]
                auth.source = "override"

                if auth.auth_method == "password":
                    override_pass = self._override_password.text()
                    if override_pass:
                        auth.password = override_pass
                elif auth.auth_method == "key":
                    override_key = self._override_key.text().strip()
                    if override_key:
                        auth.key_file = override_key
                    auth.key_passphrase = self._override_passphrase.text()

            # Password override even with "from credential" method
            elif self._override_password.text():
                auth.password = self._override_password.text()
                auth.source = "override"

        # Fallback username
        if not auth.username:
            auth.username = os.environ.get('USER', '')

        return auth

    def _update_auth_summary(self):
        """Update the auth summary display."""
        auth = self._resolve_auth()
        self._resolved_auth = auth

        if not auth:
            self._auth_summary_label.setText("Select a session")
            self._auth_warning_label.setVisible(False)
            return

        # Build summary text
        method_names = {"password": "Password", "key": "Key File", "agent": "SSH Agent"}
        method_str = method_names.get(auth.auth_method, auth.auth_method)

        if auth.auth_method == "key":
            if auth.key_file:
                key_name = os.path.basename(os.path.expanduser(auth.key_file))
                method_str = f"Key: {key_name}"
            else:
                method_str = "Key: (default ~/.ssh/id_*)"
        elif auth.auth_method == "password":
            if auth.password:
                method_str = "Password: ●●●●●●●●"
            else:
                method_str = "Password: (will prompt)"
        elif auth.auth_method == "agent":
            method_str = "SSH Agent + default keys"

        summary = f"User: {auth.username or '(current user)'}\nAuth: {method_str}\nSource: {auth.source}"
        self._auth_summary_label.setText(summary)

        # Show warnings (non-blocking)
        warnings = auth.get_warnings()
        if warnings:
            self._auth_warning_label.setText("⚠ " + "\n⚠ ".join(warnings))
            self._auth_warning_label.setVisible(True)
        else:
            self._auth_warning_label.setVisible(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Manual tab handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_auth_method_changed(self, index: int):
        """Handle auth method combo change."""
        self._auth_stack.setCurrentIndex(index)

    def _browse_key_file(self):
        """Open file dialog to select SSH key."""
        self._browse_key_file_to(self._key_edit)

    def _browse_key_file_to(self, target_edit: QLineEdit):
        """Browse for key file and set to target line edit."""
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
            # Shorten path if in ~/.ssh
            home = os.path.expanduser("~")
            if path.startswith(home):
                path = "~" + path[len(home):]
            target_edit.setText(path)

    # ─────────────────────────────────────────────────────────────────────────
    # Connection - NO BLOCKING VALIDATION
    # ─────────────────────────────────────────────────────────────────────────

    def _on_accept(self):
        """Validate and accept the dialog."""
        if self.tabs.currentIndex() == 0:
            # Sessions tab
            if not self._connect_from_session():
                return
        else:
            # Manual tab
            if not self._connect_manual():
                return

        self.accept()

    def _connect_from_session(self) -> bool:
        """Build connection info from selected session."""
        if self._selected_session is None:
            QMessageBox.warning(self, "No Session", "Please select a session.")
            return False

        session = self._selected_session
        auth = self._resolve_auth()

        if not auth:
            QMessageBox.warning(self, "Error", "Could not resolve authentication.")
            return False

        self._connection_info = SSHConnectionInfo(
            host=session.host,
            port=session.get_port_int(),
            username=auth.username or os.environ.get('USER', ''),
            auth_method=auth.auth_method,
            password=auth.password,
            key_file=auth.key_file,
            key_passphrase=auth.key_passphrase,
            display_name=session.display_name or f"{auth.username}@{session.host}",
            auth_source=auth.source,
        )

        return True

    def _connect_manual(self) -> bool:
        """Build connection info from manual entry."""
        host = self._host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Error", "Please enter a host.")
            self._host_edit.setFocus()
            return False

        username = self._username_edit.text().strip()
        if not username:
            username = os.environ.get('USER', '')

        auth_method = ["password", "key", "agent"][self._auth_combo.currentIndex()]

        password = ""
        key_file = ""
        key_passphrase = ""

        if auth_method == "password":
            password = self._password_edit.text()
            # Empty password is OK - server will prompt

        elif auth_method == "key":
            key_file = self._key_edit.text().strip()
            # Empty key_file is OK - will use defaults
            key_passphrase = self._passphrase_edit.text()

        # Agent needs nothing

        self._connection_info = SSHConnectionInfo(
            host=host,
            port=self._port_spin.value(),
            username=username,
            auth_method=auth_method,
            password=password,
            key_file=key_file,
            key_passphrase=key_passphrase,
            auth_source="manual",
        )

        return True

    def get_connection_info(self) -> Optional[SSHConnectionInfo]:
        """Get the connection info after dialog is accepted."""
        return self._connection_info

    # ─────────────────────────────────────────────────────────────────────────
    # Session/Credential Management
    # ─────────────────────────────────────────────────────────────────────────

    def _open_session_manager(self):
        """Open the session manager dialog."""
        try:
            from .session_manager import SessionManagerDialog
            dialog = SessionManagerDialog(self)
            dialog.exec()
            self._load_sessions()  # Refresh tree
        except ImportError:
            QMessageBox.information(
                self, "Coming Soon",
                "Session manager dialog not yet implemented.\n\n"
                "Edit ~/.velocitermqt/sessions.yaml directly."
            )

    def _open_credential_manager(self):
        """Open the credential manager dialog."""
        try:
            from .credential_manager import CredentialManagerDialog
            dialog = CredentialManagerDialog(self)
            dialog.exec()
            # Refresh current session details in case credential changed
            if self._selected_session:
                self._populate_session_details(self._selected_session)
                self._update_auth_summary()
        except ImportError:
            QMessageBox.information(
                self, "Coming Soon",
                "Credential manager dialog not yet implemented.\n\n"
                "Edit ~/.velocitermqt/credentials.yaml directly."
            )

    def _add_session(self):
        """Add a new session."""
        try:
            from .session_manager import SessionEditorDialog
            dialog = SessionEditorDialog(self)
            if dialog.exec():
                self._load_sessions()
        except ImportError:
            QMessageBox.information(
                self, "Coming Soon",
                "Session editor not yet implemented."
            )

    def _edit_session(self, session: SessionInfo):
        """Edit an existing session."""
        try:
            from .session_manager import SessionEditorDialog
            dialog = SessionEditorDialog(self, session=session)
            if dialog.exec():
                self._load_sessions()
        except ImportError:
            QMessageBox.information(
                self, "Coming Soon",
                "Session editor not yet implemented."
            )

    def _delete_session(self, session: SessionInfo):
        """Delete a session."""
        result = QMessageBox.question(
            self, "Delete Session",
            f"Delete session '{session.display_name or session.host}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            config = get_config()
            config.remove_session(session.host, session.get_port_int())
            config.save_sessions()
            self._load_sessions()

    def _add_folder(self):
        """Add a new folder."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            config = get_config()
            from .config_manager import SessionFolder
            config.session_folders.append(SessionFolder(folder_name=name))
            config.save_sessions()
            self._load_sessions()