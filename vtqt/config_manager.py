"""
Configuration Manager - Handles app settings and session management.

Config directory: ~/.velocitermqt/
Files:
  - settings.yaml     # App preferences
  - sessions.yaml     # SSH session definitions (folders + sessions)
  - credentials.yaml  # Credential sets (optional, referenced by credsid)
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
import yaml


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionInfo:
    """SSH session definition."""
    display_name: str
    host: str
    port: str = "22"
    DeviceType: str = "linux"
    Model: str = ""
    Vendor: str = ""
    SerialNumber: str = ""
    SoftwareVersion: str = ""
    credsid: str = ""

    # Additional fields for direct auth (if not using credsid)
    username: str = ""
    auth_method: str = "password"  # password, key, agent
    key_file: str = ""

    def get_port_int(self) -> int:
        """Get port as integer."""
        try:
            return int(self.port)
        except (ValueError, TypeError):
            return 22


@dataclass
class SessionFolder:
    """Folder containing sessions."""
    folder_name: str
    sessions: List[SessionInfo] = field(default_factory=list)


@dataclass
class Credential:
    """Credential set for session authentication."""
    id: str
    name: str
    username: str
    auth_method: str = "password"  # password, key, agent
    password: str = ""  # Note: storing passwords in plaintext is not secure
    key_file: str = ""
    key_passphrase: str = ""


@dataclass
class AppSettings:
    """Application settings."""
    # Font
    font_family: str = "monospace"
    font_size: int = 14

    # Cursor
    cursor_style: str = "block"  # block, bar, underline
    cursor_blink: bool = True
    cursor_blink_ms: int = 530

    # Colors
    foreground: str = "#d4d4d4"
    background: str = "#1e1e1e"
    selection: str = "#264f78"

    # Terminal
    scrollback_lines: int = 10000

    # Window
    window_width: int = 800
    window_height: int = 600


# ─────────────────────────────────────────────────────────────────────────────
# Config Manager
# ─────────────────────────────────────────────────────────────────────────────

class ConfigManager:
    """
    Manages application configuration and sessions.

    Usage:
        config = ConfigManager()
        config.load()

        # Access settings
        font_size = config.settings.font_size

        # Access sessions
        for folder in config.session_folders:
            for session in folder.sessions:
                print(f"{folder.folder_name}/{session.display_name}")

        # Get credential by id
        cred = config.get_credential("1")
    """

    DEFAULT_CONFIG_DIR = "~/.velocitermqt"

    def __init__(self, config_dir: str = None):
        """
        Initialize config manager.

        Args:
            config_dir: Config directory path (default: ~/.velocitermqt)
        """
        if config_dir:
            self.config_dir = Path(config_dir).expanduser()
        else:
            self.config_dir = Path(self.DEFAULT_CONFIG_DIR).expanduser()

        self.settings_file = self.config_dir / "settings.yaml"
        self.sessions_file = self.config_dir / "sessions.yaml"
        self.credentials_file = self.config_dir / "credentials.yaml"

        # Data
        self.settings = AppSettings()
        self.session_folders: List[SessionFolder] = []
        self.credentials: List[Credential] = []

        # Ensure config dir exists
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist."""
        if not self.config_dir.exists():
            try:
                self.config_dir.mkdir(parents=True, mode=0o700)
                print(f"Created config directory: {self.config_dir}")
                self._create_default_configs()
            except Exception as e:
                print(f"Warning: Could not create config dir: {e}", file=sys.stderr)

    def _create_default_configs(self):
        """Create default configuration files for new installation."""
        # Default settings
        if not self.settings_file.exists():
            default_settings = AppSettings()
            try:
                with open(self.settings_file, 'w') as f:
                    yaml.dump(asdict(default_settings), f, default_flow_style=False)
                print(f"Created default settings: {self.settings_file}")
            except Exception as e:
                print(f"Warning: Could not create default settings: {e}", file=sys.stderr)

        # Default sessions (example structure)
        if not self.sessions_file.exists():
            default_sessions = [
                {
                    'folder_name': 'Examples',
                    'sessions': [
                        {
                            'display_name': 'Local SSH',
                            'host': '127.0.0.1',
                            'port': '22',
                            'DeviceType': 'linux',
                            'Vendor': '',
                            'Model': '',
                            'credsid': '',
                        }
                    ]
                }
            ]
            try:
                with open(self.sessions_file, 'w') as f:
                    yaml.dump(default_sessions, f, default_flow_style=False, sort_keys=False)
                print(f"Created default sessions: {self.sessions_file}")
            except Exception as e:
                print(f"Warning: Could not create default sessions: {e}", file=sys.stderr)

        # Default credentials (empty template)
        if not self.credentials_file.exists():
            default_creds = [
                {
                    'id': '1',
                    'name': 'Default',
                    'username': os.environ.get('USER', 'admin'),
                    'auth_method': 'agent',  # Safe default - uses SSH agent
                }
            ]
            try:
                with open(self.credentials_file, 'w') as f:
                    yaml.dump(default_creds, f, default_flow_style=False)
                os.chmod(self.credentials_file, 0o600)
                print(f"Created default credentials: {self.credentials_file}")
            except Exception as e:
                print(f"Warning: Could not create default credentials: {e}", file=sys.stderr)

    # ─────────────────────────────────────────────────────────────
    # Load/Save
    # ─────────────────────────────────────────────────────────────

    def load(self):
        """Load all configuration files."""
        self.load_settings()
        self.load_sessions()
        self.load_credentials()

    def save(self):
        """Save all configuration files."""
        self.save_settings()
        self.save_sessions()
        self.save_credentials()

    def load_settings(self):
        """Load settings from settings.yaml."""
        if not self.settings_file.exists():
            self.settings = AppSettings()
            return

        try:
            with open(self.settings_file, 'r') as f:
                data = yaml.safe_load(f) or {}

            self.settings = AppSettings(**{
                k: v for k, v in data.items()
                if k in AppSettings.__dataclass_fields__
            })
        except Exception as e:
            print(f"Warning: Could not load settings: {e}", file=sys.stderr)
            self.settings = AppSettings()

    def save_settings(self):
        """Save settings to settings.yaml."""
        try:
            with open(self.settings_file, 'w') as f:
                yaml.dump(asdict(self.settings), f, default_flow_style=False)
        except Exception as e:
            print(f"Warning: Could not save settings: {e}", file=sys.stderr)

    def load_sessions(self):
        """Load sessions from sessions.yaml."""
        if not self.sessions_file.exists():
            self.session_folders = []
            return

        try:
            with open(self.sessions_file, 'r') as f:
                data = yaml.safe_load(f) or []

            self.session_folders = []
            for folder_data in data:
                folder = SessionFolder(
                    folder_name=folder_data.get('folder_name', 'Unnamed')
                )

                for session_data in folder_data.get('sessions', []):
                    session = SessionInfo(
                        display_name=session_data.get('display_name', ''),
                        host=session_data.get('host', ''),
                        port=str(session_data.get('port', '22')),
                        DeviceType=session_data.get('DeviceType', 'linux'),
                        Model=session_data.get('Model', ''),
                        Vendor=session_data.get('Vendor', ''),
                        SerialNumber=session_data.get('SerialNumber', ''),
                        SoftwareVersion=session_data.get('SoftwareVersion', ''),
                        credsid=str(session_data.get('credsid', '')),
                        username=session_data.get('username', ''),
                        auth_method=session_data.get('auth_method', 'password'),
                        key_file=session_data.get('key_file', ''),
                    )
                    folder.sessions.append(session)

                self.session_folders.append(folder)

        except Exception as e:
            print(f"Warning: Could not load sessions: {e}", file=sys.stderr)
            self.session_folders = []

    def save_sessions(self):
        """Save sessions to sessions.yaml."""
        try:
            data = []
            for folder in self.session_folders:
                folder_data = {
                    'folder_name': folder.folder_name,
                    'sessions': []
                }
                for session in folder.sessions:
                    session_data = {
                        'display_name': session.display_name,
                        'host': session.host,
                        'port': session.port,
                        'DeviceType': session.DeviceType,
                        'Model': session.Model,
                        'Vendor': session.Vendor,
                        'SerialNumber': session.SerialNumber,
                        'SoftwareVersion': session.SoftwareVersion,
                        'credsid': session.credsid,
                    }
                    # Only include optional fields if set
                    if session.username:
                        session_data['username'] = session.username
                    if session.auth_method != 'password':
                        session_data['auth_method'] = session.auth_method
                    if session.key_file:
                        session_data['key_file'] = session.key_file

                    folder_data['sessions'].append(session_data)
                data.append(folder_data)

            with open(self.sessions_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        except Exception as e:
            print(f"Warning: Could not save sessions: {e}", file=sys.stderr)

    def load_credentials(self):
        """Load credentials from credentials.yaml."""
        if not self.credentials_file.exists():
            self.credentials = []
            return

        try:
            with open(self.credentials_file, 'r') as f:
                data = yaml.safe_load(f) or []

            self.credentials = []
            for cred_data in data:
                cred = Credential(
                    id=str(cred_data.get('id', '')),
                    name=cred_data.get('name', ''),
                    username=cred_data.get('username', ''),
                    auth_method=cred_data.get('auth_method', 'password'),
                    password=cred_data.get('password', ''),
                    key_file=cred_data.get('key_file', ''),
                    key_passphrase=cred_data.get('key_passphrase', ''),
                )
                self.credentials.append(cred)

        except Exception as e:
            print(f"Warning: Could not load credentials: {e}", file=sys.stderr)
            self.credentials = []

    def save_credentials(self):
        """Save credentials to credentials.yaml."""
        try:
            data = []
            for cred in self.credentials:
                cred_data = {
                    'id': cred.id,
                    'name': cred.name,
                    'username': cred.username,
                    'auth_method': cred.auth_method,
                }
                if cred.password:
                    cred_data['password'] = cred.password
                if cred.key_file:
                    cred_data['key_file'] = cred.key_file
                if cred.key_passphrase:
                    cred_data['key_passphrase'] = cred.key_passphrase
                data.append(cred_data)

            # Set restrictive permissions for credentials file
            with open(self.credentials_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

            os.chmod(self.credentials_file, 0o600)

        except Exception as e:
            print(f"Warning: Could not save credentials: {e}", file=sys.stderr)

    # ─────────────────────────────────────────────────────────────
    # Credential lookup
    # ─────────────────────────────────────────────────────────────

    def get_credential(self, creds_id: str) -> Optional[Credential]:
        """Get credential by ID."""
        for cred in self.credentials:
            if cred.id == creds_id:
                return cred
        return None

    def get_credential_for_session(self, session: SessionInfo) -> Optional[Credential]:
        """Get credential for a session."""
        if session.credsid:
            return self.get_credential(session.credsid)
        return None

    # ─────────────────────────────────────────────────────────────
    # Session management
    # ─────────────────────────────────────────────────────────────

    def get_all_sessions(self) -> List[SessionInfo]:
        """Get flat list of all sessions."""
        sessions = []
        for folder in self.session_folders:
            sessions.extend(folder.sessions)
        return sessions

    def find_session(self, host: str, port: int = 22) -> Optional[SessionInfo]:
        """Find session by host and port."""
        port_str = str(port)
        for folder in self.session_folders:
            for session in folder.sessions:
                if session.host == host and session.port == port_str:
                    return session
        return None

    def add_session(self, folder_name: str, session: SessionInfo):
        """Add session to a folder (creates folder if needed)."""
        # Find or create folder
        folder = None
        for f in self.session_folders:
            if f.folder_name == folder_name:
                folder = f
                break

        if folder is None:
            folder = SessionFolder(folder_name=folder_name)
            self.session_folders.append(folder)

        folder.sessions.append(session)

    def remove_session(self, host: str, port: int = 22):
        """Remove session by host and port."""
        port_str = str(port)
        for folder in self.session_folders:
            folder.sessions = [
                s for s in folder.sessions
                if not (s.host == host and s.port == port_str)
            ]

        # Remove empty folders
        self.session_folders = [
            f for f in self.session_folders if f.sessions
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Global instance
# ─────────────────────────────────────────────────────────────────────────────

_config_instance: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get global config manager instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
        _config_instance.load()
    return _config_instance


def reload_config():
    """Reload configuration from disk."""
    global _config_instance
    if _config_instance:
        _config_instance.load()
    else:
        get_config()


# ─────────────────────────────────────────────────────────────────────────────
# CLI for testing
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = get_config()

    print(f"Config directory: {config.config_dir}")
    print(f"Sessions file: {config.sessions_file}")
    print()

    print("Settings:")
    print(f"  Font: {config.settings.font_family} {config.settings.font_size}pt")
    print(f"  Cursor: {config.settings.cursor_style}, blink={config.settings.cursor_blink}")
    print()

    print("Session Folders:")
    for folder in config.session_folders:
        print(f"  📁 {folder.folder_name}")
        for session in folder.sessions:
            cred = config.get_credential_for_session(session)
            user = cred.username if cred else session.username or "?"
            print(f"     └─ {session.display_name} ({user}@{session.host}:{session.port})")

    print()
    print("Credentials:")
    for cred in config.credentials:
        print(f"  [{cred.id}] {cred.name}: {cred.username} ({cred.auth_method})")