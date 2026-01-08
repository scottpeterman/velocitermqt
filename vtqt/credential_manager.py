"""
Credential Manager - Dialog for managing SSH credentials.

Allows viewing, adding, editing, and deleting credentials
stored in ~/.velocitermqt/credentials.yaml
"""

import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QGroupBox, QMessageBox, QListWidget, QListWidgetItem,
    QFileDialog, QStackedWidget, QWidget, QSplitter
)

from .config_manager import get_config, Credential


class CredentialManagerDialog(QDialog):
    """
    Dialog for managing SSH credentials.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credential Manager")
        self.setMinimumSize(600, 450)
        self.setModal(True)

        self._current_credential: Optional[Credential] = None
        self._is_new = False

        self._setup_ui()
        self._apply_styling()
        self._load_credentials()

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Credential list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_layout.addWidget(QLabel("Credentials:"))

        self._cred_list = QListWidget()
        self._cred_list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self._cred_list)

        # List buttons
        list_btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("➕ Add")
        self._add_btn.clicked.connect(self._add_credential)
        list_btn_layout.addWidget(self._add_btn)

        self._delete_btn = QPushButton("🗑️ Delete")
        self._delete_btn.clicked.connect(self._delete_credential)
        self._delete_btn.setEnabled(False)
        list_btn_layout.addWidget(self._delete_btn)
        list_layout.addLayout(list_btn_layout)

        splitter.addWidget(list_widget)

        # Right: Editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        # Editor group
        self._editor_group = QGroupBox("Credential Details")
        editor_grid = QGridLayout(self._editor_group)

        row = 0

        # ID (read-only for existing)
        editor_grid.addWidget(QLabel("ID:"), row, 0)
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("Unique identifier (e.g., '1', 'prod-servers')")
        editor_grid.addWidget(self._id_edit, row, 1, 1, 2)
        row += 1

        # Name
        editor_grid.addWidget(QLabel("Name:"), row, 0)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Display name (e.g., 'Production Admin')")
        editor_grid.addWidget(self._name_edit, row, 1, 1, 2)
        row += 1

        # Username
        editor_grid.addWidget(QLabel("Username:"), row, 0)
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText(os.environ.get('USER', 'username'))
        editor_grid.addWidget(self._username_edit, row, 1, 1, 2)
        row += 1

        # Auth method
        editor_grid.addWidget(QLabel("Auth Method:"), row, 0)
        self._method_combo = QComboBox()
        self._method_combo.addItems(["Password", "Key File", "SSH Agent"])
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        editor_grid.addWidget(self._method_combo, row, 1, 1, 2)
        row += 1

        # Auth-specific fields in stacked widget
        self._auth_stack = QStackedWidget()

        # Password page
        password_page = QWidget()
        password_layout = QGridLayout(password_page)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.addWidget(QLabel("Password:"), 0, 0)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("(stored in plaintext - be careful)")
        password_layout.addWidget(self._password_edit, 0, 1)

        self._show_password_btn = QPushButton("👁")
        self._show_password_btn.setFixedWidth(30)
        self._show_password_btn.setCheckable(True)
        self._show_password_btn.toggled.connect(self._toggle_password_visibility)
        password_layout.addWidget(self._show_password_btn, 0, 2)
        self._auth_stack.addWidget(password_page)

        # Key page
        key_page = QWidget()
        key_layout = QGridLayout(key_page)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(QLabel("Key File:"), 0, 0)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("~/.ssh/id_rsa")
        key_layout.addWidget(self._key_edit, 0, 1)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(self._browse_key)
        key_layout.addWidget(browse_btn, 0, 2)

        key_layout.addWidget(QLabel("Passphrase:"), 1, 0)
        self._passphrase_edit = QLineEdit()
        self._passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase_edit.setPlaceholderText("(if key is encrypted)")
        key_layout.addWidget(self._passphrase_edit, 1, 1, 1, 2)
        self._auth_stack.addWidget(key_page)

        # Agent page
        agent_page = QWidget()
        agent_layout = QVBoxLayout(agent_page)
        agent_layout.setContentsMargins(0, 0, 0, 0)
        agent_label = QLabel("Uses SSH agent for authentication.\nNo additional configuration needed.")
        agent_label.setStyleSheet("color: #808080; font-style: italic;")
        agent_layout.addWidget(agent_label)
        agent_layout.addStretch()
        self._auth_stack.addWidget(agent_page)

        editor_grid.addWidget(self._auth_stack, row, 0, 1, 3)
        row += 1

        editor_layout.addWidget(self._editor_group)

        # Save/Cancel buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._save_btn = QPushButton("💾 Save")
        self._save_btn.clicked.connect(self._save_credential)
        self._save_btn.setEnabled(False)
        btn_layout.addWidget(self._save_btn)

        self._cancel_edit_btn = QPushButton("↩ Cancel")
        self._cancel_edit_btn.clicked.connect(self._cancel_edit)
        self._cancel_edit_btn.setEnabled(False)
        btn_layout.addWidget(self._cancel_edit_btn)

        editor_layout.addLayout(btn_layout)
        editor_layout.addStretch()

        splitter.addWidget(editor_widget)
        splitter.setSizes([200, 400])

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
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px 8px;
                color: #d4d4d4;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #0078d4;
            }
            QLineEdit:disabled {
                background-color: #2a2a2a;
                color: #808080;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 6px;
            }
            QListWidget::item:selected {
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

    def _load_credentials(self):
        """Load credentials into list."""
        self._cred_list.clear()
        config = get_config()
        config.load_credentials()

        for cred in config.credentials:
            auth_icon = {"password": "🔑", "key": "🔐", "agent": "🔓"}.get(cred.auth_method, "")
            item = QListWidgetItem(f"{auth_icon} {cred.name} ({cred.username})")
            item.setData(Qt.ItemDataRole.UserRole, cred)
            self._cred_list.addItem(item)

    def _on_selection_changed(self, current, previous):
        """Handle credential selection."""
        if current is None:
            self._current_credential = None
            self._set_editor_enabled(False)
            self._delete_btn.setEnabled(False)
            return

        cred = current.data(Qt.ItemDataRole.UserRole)
        self._current_credential = cred
        self._is_new = False
        self._populate_editor(cred)
        self._set_editor_enabled(True)
        self._delete_btn.setEnabled(True)

    def _populate_editor(self, cred: Credential):
        """Populate editor fields from credential."""
        self._id_edit.setText(cred.id)
        self._id_edit.setReadOnly(True)  # Can't change ID of existing
        self._name_edit.setText(cred.name)
        self._username_edit.setText(cred.username)

        method_idx = {"password": 0, "key": 1, "agent": 2}.get(cred.auth_method, 0)
        self._method_combo.setCurrentIndex(method_idx)

        self._password_edit.setText(cred.password)
        self._key_edit.setText(cred.key_file)
        self._passphrase_edit.setText(cred.key_passphrase)

    def _clear_editor(self):
        """Clear editor fields."""
        self._id_edit.clear()
        self._id_edit.setReadOnly(False)
        self._name_edit.clear()
        self._username_edit.clear()
        self._method_combo.setCurrentIndex(0)
        self._password_edit.clear()
        self._key_edit.clear()
        self._passphrase_edit.clear()

    def _set_editor_enabled(self, enabled: bool):
        """Enable/disable editor fields."""
        self._id_edit.setEnabled(enabled)
        self._name_edit.setEnabled(enabled)
        self._username_edit.setEnabled(enabled)
        self._method_combo.setEnabled(enabled)
        self._password_edit.setEnabled(enabled)
        self._key_edit.setEnabled(enabled)
        self._passphrase_edit.setEnabled(enabled)
        self._save_btn.setEnabled(enabled)
        self._cancel_edit_btn.setEnabled(enabled)

    def _on_method_changed(self, index: int):
        """Handle auth method change."""
        self._auth_stack.setCurrentIndex(index)

    def _toggle_password_visibility(self, checked: bool):
        """Toggle password visibility."""
        if checked:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_password_btn.setText("🙈")
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_password_btn.setText("👁")

    def _browse_key(self):
        """Browse for key file."""
        ssh_dir = os.path.expanduser("~/.ssh")
        if not os.path.isdir(ssh_dir):
            ssh_dir = os.path.expanduser("~")

        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH Private Key", ssh_dir, "All Files (*)"
        )
        if path:
            home = os.path.expanduser("~")
            if path.startswith(home):
                path = "~" + path[len(home):]
            self._key_edit.setText(path)

    def _add_credential(self):
        """Add a new credential."""
        self._cred_list.clearSelection()
        self._clear_editor()
        self._is_new = True
        self._current_credential = None
        self._set_editor_enabled(True)
        self._id_edit.setReadOnly(False)
        self._id_edit.setFocus()

        # Suggest next ID
        config = get_config()
        existing_ids = {c.id for c in config.credentials}
        next_id = 1
        while str(next_id) in existing_ids:
            next_id += 1
        self._id_edit.setText(str(next_id))

    def _delete_credential(self):
        """Delete selected credential."""
        if not self._current_credential:
            return

        result = QMessageBox.question(
            self, "Delete Credential",
            f"Delete credential '{self._current_credential.name}'?\n\n"
            "Sessions using this credential will need to be updated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if result == QMessageBox.StandardButton.Yes:
            config = get_config()
            config.credentials = [c for c in config.credentials if c.id != self._current_credential.id]
            config.save_credentials()
            self._load_credentials()
            self._clear_editor()
            self._set_editor_enabled(False)

    def _save_credential(self):
        """Save current credential."""
        # Validate
        cred_id = self._id_edit.text().strip()
        if not cred_id:
            QMessageBox.warning(self, "Error", "ID is required.")
            self._id_edit.setFocus()
            return

        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Name is required.")
            self._name_edit.setFocus()
            return

        username = self._username_edit.text().strip()
        if not username:
            username = os.environ.get('USER', '')

        auth_method = ["password", "key", "agent"][self._method_combo.currentIndex()]

        # Check for ID collision on new credentials
        config = get_config()
        if self._is_new:
            for existing in config.credentials:
                if existing.id == cred_id:
                    QMessageBox.warning(self, "Error", f"Credential ID '{cred_id}' already exists.")
                    self._id_edit.setFocus()
                    return

        # Build credential
        cred = Credential(
            id=cred_id,
            name=name,
            username=username,
            auth_method=auth_method,
            password=self._password_edit.text() if auth_method == "password" else "",
            key_file=self._key_edit.text().strip() if auth_method == "key" else "",
            key_passphrase=self._passphrase_edit.text() if auth_method == "key" else "",
        )

        # Update or add
        if self._is_new:
            config.credentials.append(cred)
        else:
            for i, existing in enumerate(config.credentials):
                if existing.id == cred_id:
                    config.credentials[i] = cred
                    break

        config.save_credentials()
        self._load_credentials()

        # Re-select the saved credential
        for i in range(self._cred_list.count()):
            item = self._cred_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole).id == cred_id:
                self._cred_list.setCurrentItem(item)
                break

        self._is_new = False

    def _cancel_edit(self):
        """Cancel current edit."""
        if self._is_new:
            self._clear_editor()
            self._set_editor_enabled(False)
            self._is_new = False
        elif self._current_credential:
            self._populate_editor(self._current_credential)


class CredentialEditorDialog(QDialog):
    """
    Standalone dialog for editing a single credential.
    Used when adding/editing from other dialogs.
    """

    def __init__(self, parent=None, credential: Credential = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Credential" if credential else "New Credential")
        self.setMinimumSize(400, 300)
        self.setModal(True)

        self._credential = credential
        self._is_new = credential is None
        self._result_credential: Optional[Credential] = None

        self._setup_ui()
        self._apply_styling()

        if credential:
            self._populate_from_credential(credential)

    def _setup_ui(self):
        """Build dialog UI."""
        layout = QVBoxLayout(self)

        grid = QGridLayout()
        row = 0

        # ID
        grid.addWidget(QLabel("ID:"), row, 0)
        self._id_edit = QLineEdit()
        grid.addWidget(self._id_edit, row, 1, 1, 2)
        row += 1

        # Name
        grid.addWidget(QLabel("Name:"), row, 0)
        self._name_edit = QLineEdit()
        grid.addWidget(self._name_edit, row, 1, 1, 2)
        row += 1

        # Username
        grid.addWidget(QLabel("Username:"), row, 0)
        self._username_edit = QLineEdit()
        grid.addWidget(self._username_edit, row, 1, 1, 2)
        row += 1

        # Auth method
        grid.addWidget(QLabel("Method:"), row, 0)
        self._method_combo = QComboBox()
        self._method_combo.addItems(["Password", "Key File", "SSH Agent"])
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        grid.addWidget(self._method_combo, row, 1, 1, 2)
        row += 1

        # Auth stack
        self._auth_stack = QStackedWidget()

        # Password
        pw_widget = QWidget()
        pw_layout = QHBoxLayout(pw_widget)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.addWidget(QLabel("Password:"))
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pw_layout.addWidget(self._password_edit)
        self._auth_stack.addWidget(pw_widget)

        # Key
        key_widget = QWidget()
        key_layout = QGridLayout(key_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(QLabel("Key:"), 0, 0)
        self._key_edit = QLineEdit()
        key_layout.addWidget(self._key_edit, 0, 1)
        key_layout.addWidget(QLabel("Passphrase:"), 1, 0)
        self._passphrase_edit = QLineEdit()
        self._passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_layout.addWidget(self._passphrase_edit, 1, 1)
        self._auth_stack.addWidget(key_widget)

        # Agent
        agent_widget = QLabel("Uses SSH agent")
        agent_widget.setStyleSheet("color: gray;")
        self._auth_stack.addWidget(agent_widget)

        grid.addWidget(self._auth_stack, row, 0, 1, 3)

        layout.addLayout(grid)
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
            QLineEdit, QComboBox {
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

    def _populate_from_credential(self, cred: Credential):
        """Fill fields from credential."""
        self._id_edit.setText(cred.id)
        self._id_edit.setReadOnly(True)
        self._name_edit.setText(cred.name)
        self._username_edit.setText(cred.username)
        idx = {"password": 0, "key": 1, "agent": 2}.get(cred.auth_method, 0)
        self._method_combo.setCurrentIndex(idx)
        self._password_edit.setText(cred.password)
        self._key_edit.setText(cred.key_file)
        self._passphrase_edit.setText(cred.key_passphrase)

    def _on_method_changed(self, index: int):
        """Handle method change."""
        self._auth_stack.setCurrentIndex(index)

    def _save(self):
        """Save and accept."""
        cred_id = self._id_edit.text().strip()
        name = self._name_edit.text().strip()
        username = self._username_edit.text().strip()

        if not cred_id or not name:
            QMessageBox.warning(self, "Error", "ID and Name are required.")
            return

        auth_method = ["password", "key", "agent"][self._method_combo.currentIndex()]

        self._result_credential = Credential(
            id=cred_id,
            name=name,
            username=username or os.environ.get('USER', ''),
            auth_method=auth_method,
            password=self._password_edit.text() if auth_method == "password" else "",
            key_file=self._key_edit.text() if auth_method == "key" else "",
            key_passphrase=self._passphrase_edit.text() if auth_method == "key" else "",
        )
        self.accept()

    def get_credential(self) -> Optional[Credential]:
        """Get the resulting credential."""
        return self._result_credential