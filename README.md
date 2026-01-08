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

### Session 2 ✓ - Terminal Emulation
- **PTY integration** - Unix PTY with non-blocking I/O via QSocketNotifier
- **pyte terminal emulation** - VT100/xterm escape sequence parsing
- **Full TUI support** - htop, vim, nano, cmatrix all work
- **Color support** - 16 colors, 256 colors, true color (24-bit)
- **Scrollback history** - 10k lines with selection across history boundary
- **Flicker-free rendering** - GPU double-buffering eliminates tearing

### What Works Now
```
✅ ls --color           # Directory colors
✅ htop                 # Full-screen TUI, graphs, colors
✅ vim                  # Alternate screen buffer, syntax highlighting  
✅ cmatrix              # Smooth animation stress test
✅ nano                 # Cursor positioning, menus
✅ git diff --color     # Inline colors
✅ Selection + Copy     # Ctrl+Shift+C, works across scrollback
✅ Paste                # Ctrl+Shift+V
✅ Mouse wheel scroll   # Smooth scrollback navigation
```

### Known Limitations
- [ ] No cursor rendering (blinking block)
- [ ] Windows ConPTY not implemented
- [ ] Status bar doesn't update scroll position on startup
- [ ] No font selector UI in terminal mode
- [ ] No URL detection/clicking
- [ ] No search in scrollback

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     terminal_window.py                          │
│   TerminalWindow - toolbar, scrollbar, status bar               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     terminal_widget.py                          │
│   TerminalWidget(GPUTextWidget)                                 │
│   - Spawns PTY process                                          │
│   - Keyboard → escape sequences → PTY                           │
│   - PTY output → pyte → GPU render                              │
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  pty_process.py  │  │  pyte_buffer.py  │  │   gpu_renderer.py    │
│  UnixPty         │  │  PyteTerminal    │  │   GlyphAtlas         │
│  - fork/exec     │  │  Buffer          │  │   GridRenderer       │
│  - read/write    │  │  - pyte.Screen   │  │   - Font → texture   │
│  - SIGWINCH      │  │  - history mgmt  │  │   - OpenGL quads     │
│                  │  │  - selection     │  │   - 2-pass render    │
└──────────────────┘  └──────────────────┘  └──────────────────────┘
```

### Data Flow

```
┌─────────┐    bytes    ┌─────────┐   escape    ┌─────────┐
│   PTY   │ ─────────▶  │  pyte   │  sequences  │ Screen  │
│ process │             │ Stream  │ ──────────▶ │ Buffer  │
└─────────┘             └─────────┘   parsed    └─────────┘
                                                     │
     ┌───────────────────────────────────────────────┘
     │
     ▼
┌─────────────────┐   numpy array   ┌─────────────────┐
│ PyteTerminal    │  (rows,cols,8)  │  GridRenderer   │
│ Buffer          │ ──────────────▶ │  .render()      │
│ .to_render_     │  [char,fg,bg,   │                 │
│  array()        │   attrs]        │  OpenGL quads   │
└─────────────────┘                 └─────────────────┘
```

---

## Key Design Decisions

### Why pyte over libvterm?
- **Pure Python** - pip install, no native compilation
- **Good enough** - handles 95% of terminal escape sequences
- **You know it** - already battle-tested in tkwinterm
- **Fixable** - we patched the CSI dispatch bug in 10 lines

### Why OpenGL Immediate Mode?
- **Broad compatibility** - OpenGL 1.1+, works everywhere
- **Simple** - easy to debug, no shader complexity
- **Fast enough** - 60fps+ at typical terminal sizes
- **Future path** - can migrate to VBOs/instancing if needed

### Why Glyph Atlas?
- **Single texture** - uploaded once, reused every frame
- **O(1) lookup** - character code → UV coordinates
- **Font agnostic** - any font Qt can render
- **Extensible** - easy to add Unicode blocks

### Scrollback Strategy
pyte.HistoryScreen manages scrollback, but we wrap it:
- **Unified line numbering** - history + active screen as one array
- **Absolute selection coords** - selection works across boundary
- **Viewport offset** - scroll position independent of pyte internals

---

## File Structure

```
vtqt/
├── __init__.py           # Package exports
├── main.py               # Entry point, --viewer / --terminal modes
│
├── gpu_renderer.py       # OpenGL glyph atlas + grid rendering
├── text_widget.py        # QOpenGLWidget base class
├── terminal_buffer.py    # Basic text buffer (file viewer mode)
├── pyte_buffer.py        # pyte-backed terminal buffer
│
├── terminal_widget.py    # TerminalWidget - PTY + pyte integration
├── terminal_window.py    # Terminal mode main window
├── main_window.py        # File viewer mode main window
│
├── pty_process.py        # Unix PTY (Windows ConPTY stubbed)
└── vterm_wrapper.py      # libvterm bindings (unused, for reference)
```

---

## Installation

```bash
git clone <repo>
cd velocitermqt
python -m venv .venv
source .venv/bin/activate
pip install PyQt6 PyOpenGL numpy pyte
python -m vtqt.main
```

### Dependencies
- **PyQt6** - GUI framework
- **PyOpenGL** - OpenGL bindings
- **numpy** - render array packing
- **pyte** - terminal emulation

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

---

## Roadmap

### Phase 3: Polish
- [ ] Cursor rendering (blinking block/bar/underline)
- [ ] Font selector in toolbar
- [ ] Double-click word selection
- [ ] Triple-click line selection
- [ ] Fix status bar scroll position display
- [ ] Debounced resize handling

### Phase 4: Features
- [ ] Search in scrollback (Ctrl+Shift+F)
- [ ] URL detection and Ctrl+click
- [ ] Configurable color schemes
- [ ] Bell notification (visual/audio)
- [ ] Window title from escape sequences

### Phase 5: Platform
- [ ] Windows ConPTY support
- [ ] macOS testing
- [ ] Wayland compatibility check

### Phase 6: Advanced
- [ ] Sixel graphics support
- [ ] Kitty image protocol
- [ ] Ligature support
- [ ] Split panes
- [ ] Tabs

### Phase 7: Integration
- [ ] Embeddable widget API for Velocity* tools
- [ ] SSH session support (paramiko backend)
- [ ] Serial port support
- [ ] Telnet support

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

---

## References

- [pyte](https://github.com/selectel/pyte) - Pure Python terminal emulator
- [Alacritty](https://github.com/alacritty/alacritty) - GPU terminal inspiration
- [KodoTerm](https://github.com/diegoiast/KodoTerm) - Qt6/libvterm reference

---

## License

MIT

---

*Session 1: 2025-01-07 - GPU rendering PoC*  
*Session 2: 2025-01-08 - Terminal emulation with pyte*
