"""
SSH Session - Paramiko-based SSH session matching PtyProcess interface.

Provides the same API as UnixPty so TerminalWidget can use either
local PTY or remote SSH transparently.
"""

import os
import sys
import threading
import queue
from typing import Optional, List, Dict
from dataclasses import dataclass

try:
    import paramiko
    from paramiko import SSHClient, AutoAddPolicy, RSAKey, Ed25519Key, ECDSAKey

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    paramiko = None

from .pty_process import PtyProcess, PtySize


class SSHSession(PtyProcess):
    """
    SSH session implementation using Paramiko.

    Implements the same interface as UnixPty for transparent
    use in TerminalWidget.

    Usage:
        session = SSHSession()
        session.connect(
            host="server.example.com",
            username="user",
            password="secret"  # or key_filename="~/.ssh/id_rsa"
        )
        # Now use like UnixPty: read(), write(), set_size()
    """

    def __init__(self):
        if not HAS_PARAMIKO:
            raise ImportError(
                "paramiko is required for SSH support. "
                "Install with: pip install paramiko"
            )

        self._client: Optional[SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._connected = False
        self._exit_code: Optional[int] = None

        # Non-blocking read support
        self._read_queue: queue.Queue = queue.Queue()
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Connection info (for display)
        self._host = ""
        self._username = ""

    def connect(self,
                host: str,
                port: int = 22,
                username: str = None,
                password: str = None,
                key_filename: str = None,
                key_passphrase: str = None,
                use_agent: bool = False,
                timeout: float = 10.0,
                size: PtySize = None) -> bool:
        """
        Connect to SSH server.

        Args:
            host: Hostname or IP address
            port: SSH port (default 22)
            username: Username (default: current user)
            password: Password for password auth
            key_filename: Path to private key file
            key_passphrase: Passphrase for encrypted key
            use_agent: Use SSH agent for authentication
            timeout: Connection timeout in seconds
            size: Initial terminal size

        Returns:
            True if connection successful
        """
        if self._connected:
            self.close()

        if username is None:
            username = os.environ.get('USER', 'root')

        if size is None:
            size = PtySize(rows=24, cols=80)

        self._host = host
        self._username = username

        try:
            self._client = SSHClient()
            self._client.set_missing_host_key_policy(AutoAddPolicy())

            # Build auth kwargs
            connect_kwargs = {
                'hostname': host,
                'port': port,
                'username': username,
                'timeout': timeout,
                'allow_agent': use_agent,
                'look_for_keys': use_agent,  # Only look for keys if using agent
            }

            if password:
                connect_kwargs['password'] = password

            if key_filename:
                key_filename = os.path.expanduser(key_filename)
                connect_kwargs['key_filename'] = key_filename
                if key_passphrase:
                    connect_kwargs['passphrase'] = key_passphrase
                connect_kwargs['look_for_keys'] = False

            # Connect
            self._client.connect(**connect_kwargs)

            # Open interactive shell channel
            self._channel = self._client.invoke_shell(
                term='xterm-256color',
                width=size.cols,
                height=size.rows
            )

            # Set non-blocking
            self._channel.setblocking(0)

            # Start read thread
            self._stop_event.clear()
            self._read_thread = threading.Thread(
                target=self._read_worker,
                daemon=True
            )
            self._read_thread.start()

            self._connected = True
            return True

        except paramiko.AuthenticationException as e:
            raise ConnectionError(f"Authentication failed: {e}")
        except paramiko.SSHException as e:
            raise ConnectionError(f"SSH error: {e}")
        except Exception as e:
            raise ConnectionError(f"Connection failed: {e}")

    def _read_worker(self):
        """Background thread to read from channel."""
        while not self._stop_event.is_set():
            try:
                if self._channel and self._channel.recv_ready():
                    data = self._channel.recv(65536)
                    if data:
                        self._read_queue.put(data)
                    else:
                        # Channel closed
                        break
                else:
                    # Small sleep to avoid busy-waiting
                    self._stop_event.wait(0.01)
            except Exception:
                break

        # Channel closed - get exit status
        if self._channel:
            try:
                self._exit_code = self._channel.recv_exit_status()
            except Exception:
                self._exit_code = -1

    # ─────────────────────────────────────────────────────────
    # PtyProcess interface implementation
    # ─────────────────────────────────────────────────────────

    def spawn(self,
              argv: List[str],
              cwd: str = None,
              env: Dict[str, str] = None,
              size: PtySize = None) -> bool:
        """
        Not used for SSH - use connect() instead.

        This exists for API compatibility with UnixPty.
        """
        raise NotImplementedError(
            "SSHSession uses connect() instead of spawn(). "
            "Use session.connect(host=..., username=..., ...)"
        )

    def read(self, size: int = 4096) -> bytes:
        """
        Read available data from SSH channel (non-blocking).

        Returns:
            Bytes read, or empty bytes if nothing available
        """
        if not self._connected:
            return b''

        data = b''
        try:
            while True:
                chunk = self._read_queue.get_nowait()
                data += chunk
                if len(data) >= size:
                    break
        except queue.Empty:
            pass

        return data

    def write(self, data: bytes) -> int:
        """Write data to SSH channel."""
        if not self._channel or not self._connected:
            return 0

        try:
            return self._channel.send(data)
        except Exception:
            return 0

    def set_size(self, rows: int, cols: int, xpixel: int = 0, ypixel: int = 0):
        """Resize the SSH PTY."""
        if self._channel and self._connected:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except Exception:
                pass

    def terminate(self):
        """Close the SSH session gracefully."""
        self.close()

    def kill(self):
        """Force close the SSH session."""
        self.close()

    def close(self):
        """Close SSH connection and clean up."""
        self._stop_event.set()

        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
            self._channel = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self._connected = False

        # Wait for read thread
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=1.0)
        self._read_thread = None

    @property
    def pid(self) -> int:
        """Process ID - not applicable for SSH, return -1."""
        return -1

    @property
    def is_alive(self) -> bool:
        """Check if SSH session is still connected."""
        if not self._connected or not self._channel:
            return False

        try:
            # Check if channel is still open
            return not self._channel.closed
        except Exception:
            return False

    @property
    def exit_code(self) -> Optional[int]:
        """Exit code of remote shell, None if still running."""
        if self.is_alive:
            return None
        return self._exit_code

    @property
    def fd(self) -> int:
        """
        File descriptor - not directly available for SSH.

        Returns the underlying socket fileno for select() compatibility.
        """
        if self._channel:
            try:
                transport = self._channel.get_transport()
                if transport:
                    sock = transport.sock
                    if sock:
                        return sock.fileno()
            except Exception:
                pass
        return -1

    # ─────────────────────────────────────────────────────────
    # SSH-specific properties
    # ─────────────────────────────────────────────────────────

    @property
    def host(self) -> str:
        """Connected host."""
        return self._host

    @property
    def username(self) -> str:
        """Connected username."""
        return self._username

    @property
    def connection_string(self) -> str:
        """User-friendly connection string."""
        return f"{self._username}@{self._host}"

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self.close()


def check_paramiko_available() -> bool:
    """Check if paramiko is installed."""
    return HAS_PARAMIKO


def get_ssh_agent_keys() -> List[str]:
    """
    Get list of keys available from SSH agent.

    Returns:
        List of key fingerprints/comments
    """
    if not HAS_PARAMIKO:
        return []

    try:
        agent = paramiko.Agent()
        keys = agent.get_keys()
        result = []
        for key in keys:
            fingerprint = key.get_fingerprint().hex()
            name = key.get_name()
            result.append(f"{name} {fingerprint[:16]}...")
        return result
    except Exception:
        return []