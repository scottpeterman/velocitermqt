"""
SSH Session - Paramiko-based SSH session matching PtyProcess interface.

Provides the same API as UnixPty so TerminalWidget can use either
local PTY or remote SSH transparently.
"""

import os
import sys
import threading
import queue
import socket
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


class SSHAuthError(Exception):
    """SSH authentication failed."""
    pass


class SSHConnectionError(Exception):
    """SSH connection failed."""
    pass


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
        self._port = 22
        self._username = ""
        self._auth_method = ""

    def connect(self,
                host: str,
                port: int = 22,
                username: str = None,
                password: str = None,
                key_filename: str = None,
                key_passphrase: str = None,
                use_agent: bool = False,
                timeout: float = 10.0,
                size: PtySize = None,
                auth_method: str = None) -> bool:
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
            auth_method: Explicit auth method ("password", "key", "agent")

        Returns:
            True if connection successful

        Raises:
            SSHAuthError: Authentication failed
            SSHConnectionError: Connection failed
        """
        if self._connected:
            self.close()

        if username is None:
            username = os.environ.get('USER', 'root')

        if size is None:
            size = PtySize(rows=24, cols=80)

        self._host = host
        self._port = port
        self._username = username

        # Determine auth method if not explicit
        if auth_method is None:
            if key_filename:
                auth_method = "key"
            elif use_agent:
                auth_method = "agent"
            elif password:
                auth_method = "password"
            else:
                auth_method = "agent"  # Default fallback

        self._auth_method = auth_method

        try:
            self._client = SSHClient()
            self._client.set_missing_host_key_policy(AutoAddPolicy())

            # Build connection kwargs based on auth method
            connect_kwargs = {
                'hostname': host,
                'port': port,
                'username': username,
                'timeout': timeout,
                'allow_agent': False,
                'look_for_keys': False,
            }

            if auth_method == "password":
                # Password can be empty - Paramiko will prompt if server requires it
                # But we need to provide SOMETHING or Paramiko won't try password auth
                if password:
                    connect_kwargs['password'] = password
                else:
                    # Enable keyboard-interactive which can prompt for password
                    # Also try agent/keys as fallback
                    connect_kwargs['allow_agent'] = True
                    connect_kwargs['look_for_keys'] = True

            elif auth_method == "key":
                if key_filename:
                    key_filename = os.path.expanduser(key_filename)
                    if not os.path.isfile(key_filename):
                        raise SSHAuthError(f"Key file not found: {key_filename}")
                    connect_kwargs['key_filename'] = key_filename
                    if key_passphrase:
                        connect_kwargs['passphrase'] = key_passphrase
                else:
                    # No specific key - try default locations (~/.ssh/id_*)
                    connect_kwargs['look_for_keys'] = True
                # Also try agent as fallback
                connect_kwargs['allow_agent'] = True

            elif auth_method == "agent":
                connect_kwargs['allow_agent'] = True
                connect_kwargs['look_for_keys'] = True  # Also try default keys

            else:
                raise SSHAuthError(f"Unknown auth method: {auth_method}")

            # Connect with timeout
            try:
                self._client.connect(**connect_kwargs)
            except paramiko.AuthenticationException as e:
                raise SSHAuthError(f"Authentication failed: {e}")
            except paramiko.SSHException as e:
                raise SSHConnectionError(f"SSH protocol error: {e}")
            except socket.timeout:
                raise SSHConnectionError(f"Connection timed out after {timeout}s")
            except socket.gaierror as e:
                raise SSHConnectionError(f"Could not resolve hostname: {host}")
            except socket.error as e:
                raise SSHConnectionError(f"Network error: {e}")
            except Exception as e:
                raise SSHConnectionError(f"Connection failed: {e}")

            # Open interactive shell channel
            try:
                self._channel = self._client.invoke_shell(
                    term='xterm-256color',
                    width=size.cols,
                    height=size.rows
                )
            except paramiko.SSHException as e:
                raise SSHConnectionError(f"Could not open shell: {e}")

            # Set non-blocking
            self._channel.setblocking(0)

            # Start read thread
            self._stop_event.clear()
            self._read_thread = threading.Thread(
                target=self._read_worker,
                daemon=True,
                name=f"ssh-reader-{host}"
            )
            self._read_thread.start()

            self._connected = True
            return True

        except (SSHAuthError, SSHConnectionError):
            # Re-raise our custom exceptions
            self._cleanup_failed_connection()
            raise
        except Exception as e:
            self._cleanup_failed_connection()
            raise SSHConnectionError(f"Unexpected error: {e}")

    def _cleanup_failed_connection(self):
        """Clean up after a failed connection attempt."""
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

    # ───────────────────────────────────────────────────────────────────────
    # PtyProcess interface implementation
    # ───────────────────────────────────────────────────────────────────────

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
            transport = self._channel.get_transport()
            if transport is None or not transport.is_active():
                return False
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

    # ───────────────────────────────────────────────────────────────────────
    # SSH-specific properties
    # ───────────────────────────────────────────────────────────────────────

    @property
    def host(self) -> str:
        """Connected host."""
        return self._host

    @property
    def port(self) -> int:
        """Connected port."""
        return self._port

    @property
    def username(self) -> str:
        """Connected username."""
        return self._username

    @property
    def auth_method(self) -> str:
        """Authentication method used."""
        return self._auth_method

    @property
    def connection_string(self) -> str:
        """User-friendly connection string."""
        port_str = f":{self._port}" if self._port != 22 else ""
        return f"{self._username}@{self._host}{port_str}"

    def get_server_banner(self) -> str:
        """Get SSH server banner if available."""
        if self._client:
            try:
                transport = self._client.get_transport()
                if transport:
                    return transport.remote_version or ""
            except Exception:
                pass
        return ""

    def get_host_key_type(self) -> str:
        """Get the type of host key used."""
        if self._client:
            try:
                transport = self._client.get_transport()
                if transport:
                    key = transport.get_remote_server_key()
                    if key:
                        return key.get_name()
            except Exception:
                pass
        return ""

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self.close()


def check_paramiko_available() -> bool:
    """Check if paramiko is installed."""
    return HAS_PARAMIKO


def get_ssh_agent_keys() -> List[Dict[str, str]]:
    """
    Get list of keys available from SSH agent.

    Returns:
        List of dicts with 'type', 'fingerprint', 'comment'
    """
    if not HAS_PARAMIKO:
        return []

    try:
        agent = paramiko.Agent()
        keys = agent.get_keys()
        result = []
        for key in keys:
            fingerprint = key.get_fingerprint().hex()
            # Format fingerprint nicely
            fp_formatted = ':'.join(fingerprint[i:i+2] for i in range(0, len(fingerprint), 2))
            result.append({
                'type': key.get_name(),
                'fingerprint': fp_formatted,
                'bits': key.get_bits(),
            })
        return result
    except Exception:
        return []


def test_connection(host: str,
                   port: int = 22,
                   username: str = None,
                   password: str = None,
                   key_filename: str = None,
                   key_passphrase: str = None,
                   use_agent: bool = False,
                   timeout: float = 5.0) -> tuple[bool, str]:
    """
    Test SSH connection without opening a shell.

    Returns:
        (success: bool, message: str)
    """
    if not HAS_PARAMIKO:
        return False, "paramiko not installed"

    if username is None:
        username = os.environ.get('USER', 'root')

    try:
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())

        connect_kwargs = {
            'hostname': host,
            'port': port,
            'username': username,
            'timeout': timeout,
            'allow_agent': use_agent,
            'look_for_keys': use_agent,
        }

        if password:
            connect_kwargs['password'] = password

        if key_filename:
            connect_kwargs['key_filename'] = os.path.expanduser(key_filename)
            if key_passphrase:
                connect_kwargs['passphrase'] = key_passphrase
            connect_kwargs['look_for_keys'] = False

        client.connect(**connect_kwargs)

        # Get server info
        transport = client.get_transport()
        server_version = transport.remote_version if transport else "unknown"

        client.close()

        return True, f"Connected successfully. Server: {server_version}"

    except paramiko.AuthenticationException as e:
        return False, f"Authentication failed: {e}"
    except paramiko.SSHException as e:
        return False, f"SSH error: {e}"
    except socket.timeout:
        return False, f"Connection timed out"
    except socket.gaierror:
        return False, f"Could not resolve hostname: {host}"
    except socket.error as e:
        return False, f"Network error: {e}"
    except Exception as e:
        return False, f"Error: {e}"