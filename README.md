# VelociTermQt - GPU-Accelerated Terminal Emulator

A PyQt6 terminal emulator using OpenGL for GPU-accelerated text rendering. Part of the Velocity* tool family.

**Why?** To eliminate xterm.js dependencies and have a native, flicker-free terminal widget that can be embedded in Python network tools.

---

## Project Status

### Session 1 ✓ - GPU Rendering Foundation
- GPU-rendered text grid via OpenGL glyph atlas
- Smooth scrolling with mouse wheel
- Text selection with click-drag
- Copy to clipboard
- File viewer mode
- Box drawing characters (═║╔╗ etc.)
- Dark theme UI

### Session 2 ✓ - Terminal Emulation & SSH
- **PTY integration** - Unix PTY with non-blocking I/O via QSocketNotifier
- **pyte terminal emulation** - VT100/xterm escape sequence parsing
- **Full TUI support** - htop, vim, nano, cmatrix all work
- **Color support** - 16 colors, 256 colors, true color (24-bit)
- **Cursor rendering** - Blinking block/bar/underline with configurable color
- **Scrollback history** - 10k lines with selection across history boundary
- **Flicker-free rendering** - GPU double-buffering eliminates tearing
- **SSH support** - Paramiko integration with password/key/agent auth
- **Connection dialog** - Recent connections history, key file browser

### What Works Now
```
✅ ls --color           # Directory colors
✅ htop                 # Full-screen TUI, graphs, colors
✅ vim                  # Alternate screen buffer, syntax highlighting  
✅ cmatrix              # Smooth animation stress test
✅ nano                 # Cursor positioning, menus
✅ neofetch             # Full color system info
✅ git diff --color     # Inline colors
✅ 256-color palette    # Full xterm 256-color support
✅ True color (24-bit)  # Smooth gradients, modern apps
✅ Blinking cursor      # Block, bar, or underline styles
✅ Selection + Copy     # Ctrl+Shift+C, works across scrollback
✅ Paste                # Ctrl+Shift+V
✅ Mouse wheel scroll   # Smooth scrollback navigation
✅ SSH connections      # Password, key file, or SSH agent auth
✅ Recent connections   # Saved connection history
```

### Known Limitations
- [ ] Windows ConPTY not implemented
- [ ] No mouse reporting to applications (vim mouse mode, tmux)
- [ ] No OSC sequences (hyperlinks, window title, clipboard)
- [ ] No font selector UI
- [ ] No URL detection/clicking
- [ ] No search in scrollback

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     terminal_window.py                          │
│   TerminalWindow - toolbar, scrollbar, status bar, SSH button   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     terminal_widget.py                          │
│   TerminalWidget(GPUTextWidget)                                 │
│   - Spawns PTY process or SSH session                           │
│   - Keyboard → escape sequences → PTY/SSH                       │
│   - Output → pyte → GPU render                                  │
│   - Cursor blink timer                                          │
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  pty_process.py  │  │  pyte_buffer.py  │  │   gpu_renderer.py    │
│  UnixPty         │  │  PyteTerminal    │  │   GlyphAtlas         │
│  - fork/exec     │  │  Buffer          │  │   GridRenderer       │
│  - read/write    │  │  - pyte.Screen   │  │   - Font → texture   │
│  - SIGWINCH      │  │  - 256/truecolor │  │   - OpenGL quads     │
│                  │  │  - history mgmt  │  │   - Cursor overlay   │
│  SSHSession      │  │  - selection     │  │   - 3-pass render    │
│  - paramiko      │  │                  │  │                      │
│  - same API      │  │                  │  │                      │
└──────────────────┘  └──────────────────┘  └──────────────────────┘
                                │
                                ▼
                     ┌──────────────────┐
                     │  ssh_dialog.py   │
                     │  Connection UI   │
                     │  - Host/port     │
                     │  - Auth methods  │
                     │  - Recent list   │
                     └──────────────────┘
```

### Data Flow

```
┌─────────┐    bytes    ┌─────────┐   escape    ┌─────────┐
│ PTY/SSH │ ─────────▶  │  pyte   │  sequences  │ Screen  │
│ session │             │ Stream  │ ──────────▶ │ Buffer  │
└─────────┘             └─────────┘   parsed    └─────────┘
                                                     │
     ┌───────────────────────────────────────────────┘
     │
     ▼
┌─────────────────┐   numpy array   ┌─────────────────┐
│ PyteTerminal    │  (rows,cols,8)  │  GridRenderer   │
│ Buffer          │ ──────────────▶ │  .render()      │
│ .to_render_     │  [char,fg,bg,   │                 │
│  array()        │   attrs]        │  Pass 1: BG     │
│                 │                 │  Pass 2: Glyphs │
│ Extended SGR:   │                 │  Pass 3: Cursor │
│ - 38;5;N (256)  │                 │                 │
│ - 48;2;R;G;B    │                 │                 │
└─────────────────┘                 └─────────────────┘
```

---

## Key Design Decisions

### Why pyte over libvterm?
- **Pure Python** - pip install, no native compilation
- **Good enough** - handles 95% of terminal escape sequences
- **Patchable** - we extended SGR for 256/true color in ~50 lines
- **libvterm ready** - tested and working as escape hatch if needed

### Extended Color Support
pyte doesn't natively support 256-color or true color. We patched `FixedHistoryScreen.select_graphic_rendition()` to handle:
- `38;5;N` - 256-color foreground
- `48;5;N` - 256-color background
- `38;2;R;G;B` - 24-bit true color foreground
- `48;2;R;G;B` - 24-bit true color background

### Why OpenGL Immediate Mode?
- **Broad compatibility** - OpenGL 1.1+, works everywhere
- **Simple** - easy to debug, no shader complexity
- **Fast enough** - 60fps+ at typical terminal sizes
- **Future path** - can migrate to VBOs/instancing if needed

### SSH Architecture
`SSHSession` implements the same interface as `UnixPty`:
- `read()`, `write()`, `set_size()`, `is_alive`, `close()`
- Terminal widget doesn't know/care if it's local or remote
- Polling timer (10ms) instead of QSocketNotifier for SSH

### Cursor Rendering
Three-pass GPU rendering:
1. Background colors (solid quads)
2. Glyphs (textured quads with alpha)
3. Cursor overlay (block/bar/underline with character inversion)

Blink timer resets on keypress for responsive feel.

---

## File Structure

```
vtqt/
├── __init__.py           # Package exports
├── main.py               # Entry point, --viewer / --terminal modes
│
├── gpu_renderer.py       # OpenGL glyph atlas + grid + cursor rendering
├── text_widget.py        # QOpenGLWidget base class
├── terminal_buffer.py    # Basic text buffer (file viewer mode)
├── pyte_buffer.py        # pyte-backed terminal buffer (256/true color)
│
├── terminal_widget.py    # TerminalWidget - PTY/SSH + pyte + cursor
├── terminal_window.py    # Terminal mode main window + SSH button
├── main_window.py        # File viewer mode main window
│
├── pty_process.py        # Unix PTY + SSHSession (same interface)
├── ssh_session.py        # Paramiko SSH wrapper
├── ssh_dialog.py         # SSH connection dialog UI
│
└── vterm_wrapper.py      # libvterm bindings (tested, not used)
```

---

## Installation

```bash
git clone <repo>
cd velocitermqt
python -m venv .venv
source .venv/bin/activate
pip install PyQt6 PyOpenGL numpy pyte paramiko
python -m vtqt.main
```

### Dependencies
| Package | Purpose |
|---------|---------|
| PyQt6 | GUI framework |
| PyOpenGL | OpenGL bindings |
| numpy | Render array packing |
| pyte | Terminal emulation |
| paramiko | SSH connections (optional) |

---

## Usage

```bash
# Terminal mode (default)
python -m vtqt.main

# File viewer mode
python -m vtqt.main --viewer
python -m vtqt.main somefile.py
```

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| Ctrl+Shift+C | Copy selection |
| Ctrl+Shift+V | Paste |
| Ctrl+C | Send SIGINT to process |
| Mouse wheel | Scroll history |
| Click+drag | Select text |

### SSH Connection
1. Click **SSH Connect** button in toolbar
2. Enter host, port, username
3. Choose auth method:
   - **Password** - enter password
   - **Key File** - browse to private key, optional passphrase
   - **SSH Agent** - uses keys from running ssh-agent
4. Click **Connect**
5. Use **Disconnect** button to return to local shell

Recent connections are saved and available in the **Recent** tab.

---

## Roadmap

### Phase 3: Polish
- [x] Cursor rendering (blinking block/bar/underline)
- [ ] Font selector in toolbar
- [ ] Double-click word selection
- [ ] Triple-click line selection
- [ ] Debounced resize handling

### Phase 4: Features
- [ ] Search in scrollback (Ctrl+Shift+F)
- [ ] URL detection and Ctrl+click
- [ ] Configurable color schemes
- [ ] Bell notification (visual/audio)
- [ ] Window title from OSC sequences

### Phase 5: Platform
- [ ] Windows ConPTY support
- [ ] macOS testing
- [ ] Wayland compatibility check

### Phase 6: Mouse & Advanced
- [ ] Mouse reporting (SGR mode for vim/tmux)
- [ ] OSC 8 hyperlinks
- [ ] OSC 52 clipboard
- [ ] Sixel graphics support
- [ ] Kitty image protocol

### Phase 7: Integration
- [x] SSH session support (paramiko backend)
- [ ] Embeddable widget API for Velocity* tools
- [ ] Serial port support
- [ ] Telnet support
- [ ] Split panes
- [ ] Tabs

---

## Color Support

### 16 Colors (ANSI)
Standard terminal colors via SGR codes 30-37, 40-47, 90-97, 100-107.

### 256 Colors
Full xterm palette via `\e[38;5;Nm` (foreground) and `\e[48;5;Nm` (background):
- 0-15: Standard colors
- 16-231: 6×6×6 color cube
- 232-255: Grayscale ramp

### True Color (24-bit)
16 million colors via `\e[38;2;R;G;Bm` and `\e[48;2;R;G;Bm`.

Test with:
```bash
# 256-color palette
for i in {0..255}; do printf '\e[48;5;%dm %3d' $i $i; (( (i+1) % 16 == 0 )) && echo -e '\e[0m'; done

# True color gradient
awk 'BEGIN{for(i=0;i<256;i++)printf "\033[48;2;%d;0;0m \033[0m",i; print ""}'
```

---

## Performance Notes

The GPU rendering approach provides:
- **Flicker-free** - OpenGL double-buffering
- **Smooth scrolling** - entire viewport rendered each frame
- **Low CPU** - text rasterization happens once (glyph atlas)
- **Consistent framerate** - htop at 10Hz update = no dropped frames

Tested with:
- `cmatrix` - smooth full-screen animation
- `htop` - 20-core system, full color, no lag
- `seq 100000` - scrollback stress test
- `vim` - alternate screen buffer switching
- `neofetch` - 256/true color detection

---

## libvterm Escape Hatch

libvterm (C library) is tested and working via ctypes. Not currently used because pyte handles everything we need, but available if we hit walls with:
- Mouse reporting
- OSC sequences (hyperlinks, clipboard)
- Bracketed paste mode edge cases

See `test_libvterm.py` for integration test.

---

## References

- [pyte](https://github.com/selectel/pyte) - Pure Python terminal emulator
- [Alacritty](https://github.com/alacritty/alacritty) - GPU terminal inspiration
- [KodoTerm](https://github.com/diegoiast/KodoTerm) - Qt6/libvterm reference
- [libvterm](https://www.leonerd.org.uk/code/libvterm/) - Reference terminal emulation library
- [paramiko](https://www.paramiko.org/) - Python SSH implementation

---

## License

MIT

---

## Session Log

| Session | Date | Accomplishments |
|---------|------|-----------------|
| 1 | 2025-01-07 | GPU rendering PoC, glyph atlas, scrolling, selection |
| 2 | 2025-01-08 | Terminal emulation, 256/true color, cursor, SSH support |