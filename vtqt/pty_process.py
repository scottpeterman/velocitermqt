"""
PTY Process - Cross-platform pseudo-terminal abstraction.

Unix: Uses pty module (forkpty/openpty)
Windows: Uses ConPTY (Windows 10 1809+)
"""

import os
import sys
import signal
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from dataclasses import dataclass


@dataclass
class PtySize:
    """Terminal size in rows and columns."""
    rows: int
    cols: int
    
    # Pixel dimensions (optional, some apps use these)
    xpixel: int = 0
    ypixel: int = 0


class PtyProcess(ABC):
    """
    Abstract base class for PTY process.
    
    Implementations:
    - UnixPty: Standard Unix PTY via pty module
    - ConPty: Windows ConPTY API
    """
    
    @abstractmethod
    def spawn(self, 
              argv: List[str], 
              cwd: str = None,
              env: Dict[str, str] = None,
              size: PtySize = None) -> bool:
        """
        Spawn a process in the PTY.
        
        Args:
            argv: Command and arguments (e.g., ['/bin/bash', '-l'])
            cwd: Working directory
            env: Environment variables (merged with current env)
            size: Initial terminal size
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def read(self, size: int = 4096) -> bytes:
        """
        Read available data from PTY (non-blocking).
        
        Returns:
            Bytes read, or empty bytes if nothing available
        """
        pass
    
    @abstractmethod
    def write(self, data: bytes) -> int:
        """
        Write data to PTY.
        
        Returns:
            Number of bytes written
        """
        pass
    
    @abstractmethod
    def set_size(self, rows: int, cols: int, xpixel: int = 0, ypixel: int = 0):
        """Resize the PTY."""
        pass
    
    @abstractmethod
    def terminate(self):
        """Terminate the process."""
        pass
    
    @abstractmethod
    def kill(self):
        """Forcefully kill the process."""
        pass
    
    @property
    @abstractmethod
    def pid(self) -> int:
        """Process ID."""
        pass
    
    @property
    @abstractmethod
    def is_alive(self) -> bool:
        """Check if process is still running."""
        pass
    
    @property
    @abstractmethod
    def exit_code(self) -> Optional[int]:
        """Exit code if process has exited, None otherwise."""
        pass
    
    @property
    @abstractmethod
    def fd(self) -> int:
        """File descriptor for the PTY master (for select/poll)."""
        pass


class UnixPty(PtyProcess):
    """
    Unix PTY implementation using pty module.
    """
    
    def __init__(self):
        self._pid: int = -1
        self._fd: int = -1
        self._exit_code: Optional[int] = None
    
    def spawn(self, 
              argv: List[str], 
              cwd: str = None,
              env: Dict[str, str] = None,
              size: PtySize = None) -> bool:
        """Spawn process in PTY using forkpty."""
        
        import pty
        import fcntl
        import termios
        import struct
        
        # Prepare environment
        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        
        # Set TERM if not specified
        if 'TERM' not in spawn_env:
            spawn_env['TERM'] = 'xterm-256color'
        
        try:
            # Fork with PTY
            self._pid, self._fd = pty.fork()
            
            if self._pid == 0:
                # Child process
                if cwd:
                    os.chdir(cwd)
                
                os.execvpe(argv[0], argv, spawn_env)
                # execvpe doesn't return on success
                sys.exit(1)
            
            # Parent process
            
            # Set non-blocking
            flags = fcntl.fcntl(self._fd, fcntl.F_GETFL)
            fcntl.fcntl(self._fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Set initial size
            if size:
                self.set_size(size.rows, size.cols, size.xpixel, size.ypixel)
            else:
                self.set_size(24, 80)
            
            return True
            
        except Exception as e:
            print(f"Failed to spawn PTY: {e}", file=sys.stderr)
            return False
    
    def read(self, size: int = 4096) -> bytes:
        """Read from PTY (non-blocking)."""
        if self._fd < 0:
            return b''
        
        try:
            return os.read(self._fd, size)
        except BlockingIOError:
            return b''
        except OSError:
            return b''
    
    def write(self, data: bytes) -> int:
        """Write to PTY."""
        if self._fd < 0:
            return 0
        
        try:
            return os.write(self._fd, data)
        except OSError:
            return 0
    
    def set_size(self, rows: int, cols: int, xpixel: int = 0, ypixel: int = 0):
        """Set PTY size using TIOCSWINSZ."""
        if self._fd < 0:
            return
        
        import fcntl
        import termios
        import struct
        
        winsize = struct.pack('HHHH', rows, cols, xpixel, ypixel)
        fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        
        # Send SIGWINCH to notify process
        if self._pid > 0:
            try:
                os.kill(self._pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass
    
    def terminate(self):
        """Send SIGTERM to process."""
        if self._pid > 0:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    
    def kill(self):
        """Send SIGKILL to process."""
        if self._pid > 0:
            try:
                os.kill(self._pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        
        self._close()
    
    def _close(self):
        """Close PTY file descriptor."""
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
    
    @property
    def pid(self) -> int:
        return self._pid
    
    @property
    def is_alive(self) -> bool:
        if self._pid <= 0:
            return False
        
        # Check with waitpid (non-blocking)
        try:
            pid, status = os.waitpid(self._pid, os.WNOHANG)
            if pid == 0:
                return True  # Still running
            
            # Process exited
            if os.WIFEXITED(status):
                self._exit_code = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                self._exit_code = -os.WTERMSIG(status)
            
            return False
            
        except ChildProcessError:
            return False
    
    @property
    def exit_code(self) -> Optional[int]:
        if self._exit_code is None:
            self.is_alive  # Update exit code
        return self._exit_code
    
    @property
    def fd(self) -> int:
        return self._fd


class ConPty(PtyProcess):
    """
    Windows ConPTY implementation.
    
    Requires Windows 10 version 1809 or later.
    Uses the CreatePseudoConsole API.
    """
    
    def __init__(self):
        self._pid: int = -1
        self._handle = None
        self._process_handle = None
        self._input_pipe = None
        self._output_pipe = None
        self._exit_code: Optional[int] = None
    
    def spawn(self, 
              argv: List[str], 
              cwd: str = None,
              env: Dict[str, str] = None,
              size: PtySize = None) -> bool:
        """Spawn process using ConPTY."""
        
        # TODO: Implement using ctypes or pywin32
        # 
        # Steps:
        # 1. CreatePipe for input/output
        # 2. CreatePseudoConsole with size and pipes
        # 3. InitializeProcThreadAttributeList
        # 4. UpdateProcThreadAttribute with pseudo console handle
        # 5. CreateProcess with EXTENDED_STARTUPINFO_PRESENT
        #
        # Reference: 
        # https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/
        
        raise NotImplementedError("ConPTY support not yet implemented")
    
    def read(self, size: int = 4096) -> bytes:
        if not self._output_pipe:
            return b''
        
        # TODO: Read from output pipe
        raise NotImplementedError()
    
    def write(self, data: bytes) -> int:
        if not self._input_pipe:
            return 0
        
        # TODO: Write to input pipe
        raise NotImplementedError()
    
    def set_size(self, rows: int, cols: int, xpixel: int = 0, ypixel: int = 0):
        if not self._handle:
            return
        
        # TODO: ResizePseudoConsole
        raise NotImplementedError()
    
    def terminate(self):
        # TODO: TerminateProcess
        raise NotImplementedError()
    
    def kill(self):
        self.terminate()
    
    @property
    def pid(self) -> int:
        return self._pid
    
    @property
    def is_alive(self) -> bool:
        # TODO: WaitForSingleObject with 0 timeout
        return False
    
    @property
    def exit_code(self) -> Optional[int]:
        return self._exit_code
    
    @property
    def fd(self) -> int:
        # Windows uses handles, not file descriptors
        return -1


def create_pty() -> PtyProcess:
    """Create appropriate PTY for current platform."""
    if sys.platform == 'win32':
        return ConPty()
    else:
        return UnixPty()


# Convenience function
def spawn_shell(shell: str = None, 
                cwd: str = None, 
                env: dict = None,
                rows: int = 24,
                cols: int = 80) -> PtyProcess:
    """
    Spawn a shell in a PTY.
    
    Args:
        shell: Shell path (default: $SHELL or /bin/bash or cmd.exe)
        cwd: Working directory (default: $HOME)
        env: Additional environment variables
        rows: Terminal rows
        cols: Terminal columns
    
    Returns:
        PtyProcess instance
    """
    # Determine shell
    if shell is None:
        if sys.platform == 'win32':
            shell = os.environ.get('COMSPEC', 'cmd.exe')
        else:
            shell = os.environ.get('SHELL', '/bin/bash')
    
    # Determine working directory
    if cwd is None:
        cwd = os.environ.get('HOME', os.getcwd())
    
    # Create PTY
    pty = create_pty()
    
    # Spawn shell
    size = PtySize(rows=rows, cols=cols)
    
    if sys.platform == 'win32':
        argv = [shell]
    else:
        # Login shell
        argv = [shell, '-l']
    
    if not pty.spawn(argv, cwd=cwd, env=env, size=size):
        raise RuntimeError(f"Failed to spawn shell: {shell}")
    
    return pty
