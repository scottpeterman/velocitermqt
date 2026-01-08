"""
Session Manager - Dialog for managing SSH sessions.

Allows viewing, adding, editing, and deleting sessions
stored in ~/.velocitermqt/sessions.yaml
"""

import os
from typing import Optional, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton,
    QGroupBox, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QWidget, QSplitter, QInputDialog
)

from .config_manager import get_config, SessionInfo, SessionFolder, Credential


class SessionManagerDialog(QDialog):
    """
    Dialog for managing SSH sessions.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Manager")
        self.setMinimumSize(750, 500)
        self.setModal(True)

        self._current_session: Optional[SessionInfo] = None
        self._current_folder: Optional[str] = None
        self._is_new = False

        self._setup_ui()
        self._apply_styling()
        self._load_sessions()

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Session tree
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        tree_layout.addWidget(QLabel("Sessions:"))

        self._session_tree = QTreeWidget()
        self._session_tree.setHeaderHidden(True)
        self._session_tree.setRootIsDecorated(True)
        self._session_tree.itemClicked.connect(self._on_selection_changed)
        tree_layout.addWidget(self._session_tree)

        # Tree buttons
        tree_btn_layout = QHBoxLayout()
        self._add_folder_btn = QPushButton("📁 Folder")
        self._add_folder_btn.clicked.connect(self._add_folder)
        tree_btn_layout.addWidget(self._add_folder_btn)

        self._add_session_btn = QPushButton("➕ Session")
        self._add_session_btn.clicked.connect(self._add_session)
        tree_btn_layout.addWidget(self._add_session_btn)

        self._delete_btn = QPushButton("🗑️ Delete")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)
        tree_btn_layout.addWidget(self._delete_btn)

        tree_layout.addLayout(tree_btn_layout)
        splitter.addWidget(tree_widget)

        # Right: Editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        # Connection group
        conn_group = QGroupBox("Connection")
        conn_grid = QGridLayout(conn_group)

        row = 0
        conn_grid.addWidget(QLabel("Display Name:"), row, 0)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Friendly name (optional)")
        conn_grid.addWidget(self._name_edit, row, 1, 1, 3)
        row += 1

        conn_grid.addWidget(QLabel("Host:"), row, 0)
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("hostname or IP")
        conn_grid.addWidget(self._host_edit, row, 1, 1, 2)

        conn_grid.addWidget(QLabel("Port:"), row, 3)
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        conn_grid.addWidget(self._port_spin, row, 4)
        row += 1

        conn_grid.addWidget(QLabel("Folder:"), row, 0)
        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        conn_grid.addWidget(self._folder_combo, row, 1, 1, 4)
        row += 1

        editor_layout.addWidget(conn_group)

        # Device info group
        device_group = QGroupBox("Device Info (Optional)")
        device_grid = QGridLayout(device_group)

        device_grid.addWidget(QLabel("Type:"), 0, 0)
        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems([
            "linux", "cisco_ios", "cisco_nxos", "cisco_xe", "cisco_xr",
            "arista_eos", "juniper_junos", "paloalto_panos", "fortinet",
            "hp_procurve", "dell_os10", "mikrotik", "ubiquiti_edgeos"
        ])
        device_grid.addWidget(self._type_combo, 0, 1)

        device_grid.addWidget(QLabel("Vendor:"), 0, 2)
        self._vendor_edit = QLineEdit()
        device_grid.addWidget(self._vendor_edit, 0, 3)

        device_grid.addWidget(QLabel("Model:"), 1, 0)
        self._model_edit = QLineEdit()
        device_grid.addWidget(self._model_edit, 1, 1)

        device_grid.addWidget(QLabel("Serial:"), 1, 2)
        self._serial_edit = QLineEdit()
        device_grid.addWidget(self._serial_edit, 1, 3)

        device_grid.addWidget(QLabel("Version:"), 2, 0)
        self._version_edit = QLineEdit()
        device_grid.addWidget(self._version_edit, 2, 1, 1, 3)

        editor_layout.addWidget(device_group)

        # Authentication group
        auth_group = QGroupBox("Authentication")
        auth_grid = QGridLayout(auth_group)

        auth_grid.addWidget(QLabel("Credential:"), 0, 0)
        self._cred_combo = QComboBox()
        self._cred_combo.currentIndexChanged.connect(self._on_credential_changed)
        auth_grid.addWidget(self._cred_combo, 0, 1, 1, 2)

        self._manage_creds_btn = QPushButton("🔑 Manage...")
        self._manage_creds_btn.clicked.connect(self._open_credential_manager)
        auth_grid.addWidget(self._manage_creds_btn, 0, 3)

        # Direct auth (if no credential)
        auth_grid.addWidget(QLabel("Or direct:"), 1, 0)
        self._direct_username = QLineEdit()
        self._direct_username.setPlaceholderText("Username (if not using credential)")
        auth_grid.addWidget(self._direct_username, 1, 1, 1, 3)

        editor_layout.addWidget(auth_group)

        # Editor buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._save_btn = QPushButton("💾 Save")
        self._save_btn.clicked.connect(self._save_session)
        self._save_btn.setEnabled(False)
        btn_layout.addWidget(self._save_btn)

        self._cancel_btn = QPushButton("↩ Cancel")
        self._cancel_btn.clicked.connect(self._cancel_edit)
        self._cancel_btn.setEnabled(False)
        btn_layout.addWidget(self._cancel_btn)

        editor_layout.addLayout(btn_layout)
        editor_layout.addStretch()

        splitter.addWidget(editor_widget)
        splitter.setSizes([250, 500])

        layout.addWidget(splitter)

        # Dialog buttons
        dialog_btn_layout = QHBoxLayout()
        dialog_btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        dialog_btn_layout.addWidget(close_btn)
        layout.addLayout(dialog_btn_layout)

        # Initially disable editor
        self._set_editor_enabled(False)

    def _apply_styling(self):
        """Apply dark theme styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #d4d4d4;
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
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
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
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 6px 12px;
                color: #d4d4d4;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #606060;
            }
        """)

    def _load_sessions(self):
        """Load sessions into tree."""
        self._session_tree.clear()
        self._folder_combo.clear()
        self._cred_combo.clear()

        config = get_config()
        config.load_sessions()
        config.load_credentials()

        # Populate folder combo
        folder_names = [f.folder_name for f in config.session_folders]
        self._folder_combo.addItems(folder_names)

        # Populate credential combo
        self._cred_combo.addItem("(none)", "")
        for cred in config.credentials:
            auth_icon = {"password": "🔑", "key": "🔐", "agent": "🔓"}.get(cred.auth_method, "")
            self._cred_combo.addItem(f"{auth_icon} {cred.name} ({cred.username})", cred.id)

        # Populate tree
        for folder in config.session_folders:
            folder_item = QTreeWidgetItem([f"📁 {folder.folder_name}"])
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder.folder_name))
            folder_item.setExpanded(True)

            for session in folder.sessions:
                session_text = session.display_name or session.host
                session_item = QTreeWidgetItem([f"  🖥 {session_text}"])
                session_item.setData(0, Qt.ItemDataRole.UserRole, ("session", session, folder.folder_name))
                session_item.setToolTip(0, f"{session.host}:{session.port}")
                folder_item.addChild(session_item)

            self._session_tree.addTopLevelItem(folder_item)

    def _on_selection_changed(self, item: QTreeWidgetItem, column: int):
        """Handle tree selection."""
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if data is None:
            self._current_session = None
            self._current_folder = None
            self._set_editor_enabled(False)
            self._delete_btn.setEnabled(False)
            return

        if data[0] == "folder":
            self._current_session = None
            self._current_folder = data[1]
            self._clear_editor()
            self._set_editor_enabled(False)
            self._delete_btn.setEnabled(True)

        elif data[0] == "session":
            self._current_session = data[1]
            self._current_folder = data[2]
            self._is_new = False
            self._populate_editor(data[1], data[2])
            self._set_editor_enabled(True)
            self._delete_btn.setEnabled(True)

    def _populate_editor(self, session: SessionInfo, folder_name: str):
        """Populate editor from session."""
        self._name_edit.setText(session.display_name)
        self._host_edit.setText(session.host)
        self._port_spin.setValue(session.get_port_int())

        # Set folder
        idx = self._folder_combo.findText(folder_name)
        if idx >= 0:
            self._folder_combo.setCurrentIndex(idx)

        # Device info
        self._type_combo.setCurrentText(session.DeviceType or "linux")
        self._vendor_edit.setText(session.Vendor)
        self._model_edit.setText(session.Model)
        self._serial_edit.setText(session.SerialNumber)
        self._version_edit.setText(session.SoftwareVersion)

        # Credential
        cred_idx = 0
        if session.credsid:
            for i in range(self._cred_combo.count()):
                if self._cred_combo.itemData(i) == session.credsid:
                    cred_idx = i
                    break
        self._cred_combo.setCurrentIndex(cred_idx)

        self._direct_username.setText(session.username)

    def _clear_editor(self):
        """Clear editor fields."""
        self._name_edit.clear()
        self._host_edit.clear()
        self._port_spin.setValue(22)
        self._type_combo.setCurrentText("linux")
        self._vendor_edit.clear()
        self._model_edit.clear()
        self._serial_edit.clear()
        self._version_edit.clear()
        self._cred_combo.setCurrentIndex(0)
        self._direct_username.clear()

    def _set_editor_enabled(self, enabled: bool):
        """Enable/disable editor."""
        self._name_edit.setEnabled(enabled)
        self._host_edit.setEnabled(enabled)
        self._port_spin.setEnabled(enabled)
        self._folder_combo.setEnabled(enabled)
        self._type_combo.setEnabled(enabled)
        self._vendor_edit.setEnabled(enabled)
        self._model_edit.setEnabled(enabled)
        self._serial_edit.setEnabled(enabled)
        self._version_edit.setEnabled(enabled)
        self._cred_combo.setEnabled(enabled)
        self._direct_username.setEnabled(enabled)
        self._save_btn.setEnabled(enabled)
        self._cancel_btn.setEnabled(enabled)

    def _on_credential_changed(self, index: int):
        """Handle credential selection change."""
        # Disable direct username if credential selected
        has_cred = index > 0
        self._direct_username.setEnabled(not has_cred)
        if has_cred:
            self._direct_username.clear()

    def _add_folder(self):
        """Add a new folder."""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            config = get_config()
            # Check for duplicate
            for folder in config.session_folders:
                if folder.folder_name == name:
                    QMessageBox.warning(self, "Error", f"Folder '{name}' already exists.")
                    return

            config.session_folders.append(SessionFolder(folder_name=name))
            config.save_sessions()
            self._load_sessions()

    def _add_session(self):
        """Add a new session."""
        self._session_tree.clearSelection()
        self._clear_editor()
        self._is_new = True
        self._current_session = None
        self._set_editor_enabled(True)

        # Default to first folder if exists
        if self._folder_combo.count() > 0:
            self._folder_combo.setCurrentIndex(0)

        self._host_edit.setFocus()

    def _delete_selected(self):
        """Delete selected item."""
        if self._current_session:
            result = QMessageBox.question(
                self, "Delete Session",
                f"Delete session '{self._current_session.display_name or self._current_session.host}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result == QMessageBox.StandardButton.Yes:
                config = get_config()
                config.remove_session(self._current_session.host, self._current_session.get_port_int())
                config.save_sessions()
                self._load_sessions()
                self._clear_editor()
                self._set_editor_enabled(False)

        elif self._current_folder:
            config = get_config()
            # Check if folder has sessions
            for folder in config.session_folders:
                if folder.folder_name == self._current_folder:
                    if folder.sessions:
                        result = QMessageBox.question(
                            self, "Delete Folder",
                            f"Folder '{self._current_folder}' contains {len(folder.sessions)} sessions.\n"
                            "Delete folder and all sessions?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        if result != QMessageBox.StandardButton.Yes:
                            return
                    break

            config.session_folders = [f for f in config.session_folders if f.folder_name != self._current_folder]
            config.save_sessions()
            self._load_sessions()

    def _save_session(self):
        """Save current session."""
        host = self._host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Error", "Host is required.")
            self._host_edit.setFocus()
            return

        folder_name = self._folder_combo.currentText().strip()
        if not folder_name:
            QMessageBox.warning(self, "Error", "Folder is required.")
            self._folder_combo.setFocus()
            return

        session = SessionInfo(
            display_name=self._name_edit.text().strip(),
            host=host,
            port=str(self._port_spin.value()),
            DeviceType=self._type_combo.currentText(),
            Vendor=self._vendor_edit.text().strip(),
            Model=self._model_edit.text().strip(),
            SerialNumber=self._serial_edit.text().strip(),
            SoftwareVersion=self._version_edit.text().strip(),
            credsid=self._cred_combo.currentData() or "",
            username=self._direct_username.text().strip(),
        )

        config = get_config()

        # Remove old session if editing
        if not self._is_new and self._current_session:
            config.remove_session(self._current_session.host, self._current_session.get_port_int())

        # Add to folder
        config.add_session(folder_name, session)
        config.save_sessions()

        self._load_sessions()
        self._is_new = False

        # Re-select the saved session
        self._select_session(host, session.get_port_int())

    def _select_session(self, host: str, port: int):
        """Select a session in the tree by host/port."""
        for i in range(self._session_tree.topLevelItemCount()):
            folder_item = self._session_tree.topLevelItem(i)
            for j in range(folder_item.childCount()):
                session_item = folder_item.child(j)
                data = session_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "session":
                    session = data[1]
                    if session.host == host and session.get_port_int() == port:
                        self._session_tree.setCurrentItem(session_item)
                        return

    def _cancel_edit(self):
        """Cancel current edit."""
        if self._is_new:
            self._clear_editor()
            self._set_editor_enabled(False)
            self._is_new = False
        elif self._current_session:
            self._populate_editor(self._current_session, self._current_folder)

    def _open_credential_manager(self):
        """Open credential manager dialog."""
        from .credential_manager import CredentialManagerDialog
        dialog = CredentialManagerDialog(self)
        dialog.exec()
        # Refresh credential combo
        self._load_sessions()


class SessionEditorDialog(QDialog):
    """
    Standalone dialog for editing a single session.
    Used when adding/editing from other dialogs.
    """

    def __init__(self, parent=None, session: SessionInfo = None, folder_name: str = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Session" if session else "New Session")
        self.setMinimumSize(450, 400)
        self.setModal(True)

        self._session = session
        self._folder_name = folder_name
        self._is_new = session is None

        self._setup_ui()
        self._apply_styling()
        self._load_combos()

        if session:
            self._populate_from_session(session, folder_name)

    def _setup_ui(self):
        """Build dialog UI."""
        layout = QVBoxLayout(self)

        # Connection
        conn_group = QGroupBox("Connection")
        conn_grid = QGridLayout(conn_group)

        conn_grid.addWidget(QLabel("Name:"), 0, 0)
        self._name_edit = QLineEdit()
        conn_grid.addWidget(self._name_edit, 0, 1, 1, 2)

        conn_grid.addWidget(QLabel("Host:"), 1, 0)
        self._host_edit = QLineEdit()
        conn_grid.addWidget(self._host_edit, 1, 1)

        conn_grid.addWidget(QLabel("Port:"), 1, 2)
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        conn_grid.addWidget(self._port_spin, 1, 3)

        conn_grid.addWidget(QLabel("Folder:"), 2, 0)
        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        conn_grid.addWidget(self._folder_combo, 2, 1, 1, 3)

        layout.addWidget(conn_group)

        # Auth
        auth_group = QGroupBox("Authentication")
        auth_grid = QGridLayout(auth_group)

        auth_grid.addWidget(QLabel("Credential:"), 0, 0)
        self._cred_combo = QComboBox()
        auth_grid.addWidget(self._cred_combo, 0, 1)

        auth_grid.addWidget(QLabel("Username:"), 1, 0)
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("(if not using credential)")
        auth_grid.addWidget(self._username_edit, 1, 1)

        layout.addWidget(auth_group)

        # Device
        device_group = QGroupBox("Device (Optional)")
        device_grid = QGridLayout(device_group)

        device_grid.addWidget(QLabel("Type:"), 0, 0)
        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(["linux", "cisco_ios", "cisco_nxos", "arista_eos", "juniper_junos"])
        device_grid.addWidget(self._type_combo, 0, 1)

        device_grid.addWidget(QLabel("Vendor:"), 1, 0)
        self._vendor_edit = QLineEdit()
        device_grid.addWidget(self._vendor_edit, 1, 1)

        device_grid.addWidget(QLabel("Model:"), 2, 0)
        self._model_edit = QLineEdit()
        device_grid.addWidget(self._model_edit, 2, 1)

        layout.addWidget(device_group)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _apply_styling(self):
        """Apply styling."""
        self.setStyleSheet("""
            QDialog { background-color: #2d2d2d; color: #d4d4d4; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #404040;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                padding: 4px;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                padding: 6px 12px;
            }
        """)

    def _load_combos(self):
        """Load combo box data."""
        config = get_config()

        # Folders
        for folder in config.session_folders:
            self._folder_combo.addItem(folder.folder_name)

        # Credentials
        self._cred_combo.addItem("(none)", "")
        for cred in config.credentials:
            self._cred_combo.addItem(f"{cred.name} ({cred.username})", cred.id)

    def _populate_from_session(self, session: SessionInfo, folder_name: str):
        """Fill fields from session."""
        self._name_edit.setText(session.display_name)
        self._host_edit.setText(session.host)
        self._port_spin.setValue(session.get_port_int())

        idx = self._folder_combo.findText(folder_name or "")
        if idx >= 0:
            self._folder_combo.setCurrentIndex(idx)

        # Credential
        for i in range(self._cred_combo.count()):
            if self._cred_combo.itemData(i) == session.credsid:
                self._cred_combo.setCurrentIndex(i)
                break

        self._username_edit.setText(session.username)
        self._type_combo.setCurrentText(session.DeviceType or "linux")
        self._vendor_edit.setText(session.Vendor)
        self._model_edit.setText(session.Model)

    def _save(self):
        """Save and accept."""
        host = self._host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Error", "Host is required.")
            return

        folder_name = self._folder_combo.currentText().strip()
        if not folder_name:
            QMessageBox.warning(self, "Error", "Folder is required.")
            return

        session = SessionInfo(
            display_name=self._name_edit.text().strip(),
            host=host,
            port=str(self._port_spin.value()),
            DeviceType=self._type_combo.currentText(),
            Vendor=self._vendor_edit.text().strip(),
            Model=self._model_edit.text().strip(),
            credsid=self._cred_combo.currentData() or "",
            username=self._username_edit.text().strip(),
        )

        config = get_config()

        # Remove old if editing
        if not self._is_new and self._session:
            config.remove_session(self._session.host, self._session.get_port_int())

        config.add_session(folder_name, session)
        config.save_sessions()

        self.accept()