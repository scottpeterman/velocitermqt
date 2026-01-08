# VelociTermQt - GPU-Accelerated Terminal Emulator

## Project Status: Proof of Concept ✓

A PyQt6 terminal emulator using OpenGL for GPU-accelerated text rendering. Part of the Velocity* tool family.

### What Works (Session 1)
- ✅ GPU-rendered text grid via OpenGL glyph atlas
- ✅ Smooth scrolling with mouse wheel
- ✅ Text selection with click-drag
- ✅ Copy to clipboard (Ctrl+C)
- ✅ File viewer mode (Ctrl+O)
- ✅ Font family selector (auto-detects monospace fonts)
- ✅ Font size control (6-32pt, Ctrl+Plus/Minus)
- ✅ Dark theme UI
- ✅ Box drawing characters (═║╔╗ etc.)

### Known Issues / TODO
- [ ] Text clipping on resize (needs
 debounced re-render)
- [ ] Selection doesn't extend past viewport during drag
- [ ] No cursor rendering yet
- [ ] Terminal emulation not wired up (stubs only)
- [ ] Windows ConPTY not implemented

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        main_window.py                           │
│   TextViewerWindow - toolbar, scrollbar, font controls, theme   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        text_widget.py                           │
│   GPUTextWidget(QOpenGLWidget) - base class                     │
│   - Mouse/keyboard input                                        │
│   - Scroll management                                           │
│   - Selection tracking                                          │
│   - Coordinates GL context lifecycle                            │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────┐    ┌─────────────────────────────────┐
│   terminal_buffer.py    │    │       gpu_renderer.py           │
│   TextBuffer            │    │   GlyphAtlas + GridRenderer     │
│   - Lines/Cells model   │    │   - Font → texture atlas        │
│   - Scrollback storage  │    │   - Immediate mode GL rendering │
│   - Selection state     │    │   - Background + glyph passes   │
│   - to_render_array()   │    │                                 │
└─────────────────────────┘    └─────────────────────────────────┘
```

### Terminal Extension (Stubbed)

```
┌─────────────────────────────────────────────────────────────────┐
│                     terminal_widget.py                          │
│   TerminalWidget(GPUTextWidget) - extends base with PTY/vterm   │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────┐    ┌─────────────────────────────────┐
│     pty_process.py      │    │       vterm_wrapper.py          │
│   UnixPty / ConPty      │    │   libvterm cffi bindings        │
│   - spawn shell         │    │   - Escape sequence parsing     │
│   - read/write          │    │   - Screen state management     │
│   - resize (SIGWINCH)   │    │   - Scrollback callbacks        │
└─────────────────────────┘    └─────────────────────────────────┘
```

---

## Data Flow

### File Viewer Mode (Current)
```
load_file() → TextBuffer.load_text() → Lines/Cells populated
    │
    ▼
paintGL() → buffer.to_render_array() → numpy array (rows, cols, 8)
    │                                   [char, fg_rgb, bg_rgb, attrs]
    ▼
GridRenderer.render() → GL immediate mode quads
    │
    ├─ Pass 1: Background colors (solid quads)
    └─ Pass 2: Glyphs (textured quads with alpha blend)
```

### Terminal Mode (Planned)
```
PTY output → vterm.input_write() → callbacks triggered
    │
    ├─ damage(rect)      → update buffer cells → queue redraw
    ├─ sb_pushline(line) → append to scrollback buffer
    ├─ movecursor(pos)   → update cursor state
    └─ bell/title        → emit signals

Keyboard → vterm_keyboard_*() → vterm.get_output() → PTY write
```

---

## Key Design Decisions

### Why libvterm?
- Battle-tested (Neovim, Qt Creator, Emacs use it)
- Handles VT220/xterm escape sequences correctly
- Clean callback model - WE manage scrollback
- Platform-agnostic (PTY layer is separate)

### Why OpenGL Immediate Mode?
- Broad compatibility (OpenGL 1.1+)
- Simple to implement and debug
- Good enough for 60fps at typical terminal sizes
- Future: migrate to instanced rendering with VBOs

### Why Glyph Atlas?
- Single texture upload, reused every frame
- O(1) lookup per character
- Supports any font Qt can render
- Easy to extend for Unicode blocks

### Scrollback Model
libvterm does NOT store scrollback. When a line scrolls off top:
1. `sb_pushline(cells)` callback fires
2. WE store the line in TextBuffer.scrollback[]
3. On resize taller, `sb_popline()` returns lines back

This gives us full control over scrollback limits and storage.

---

## File Structure

```
vtqt/
├── __init__.py           # Package exports
├── main.py               # Entry point (12 lines)
│
├── terminal_buffer.py    # Data model - lines, cells, selection
├── gpu_renderer.py       # OpenGL - glyph atlas, grid rendering
│
├── text_widget.py        # QOpenGLWidget base class
├── main_window.py        # App chrome - toolbar, scrollbar
│
├── terminal_widget.py    # Terminal emulator (stub)
├── pty_process.py        # PTY abstraction (Unix done, Windows stub)
└── vterm_wrapper.py      # libvterm cffi bindings (stub)
```

---

## Dependencies

**Required:**
- PyQt6
- PyOpenGL
- numpy

**For Terminal Mode (not yet implemented):**
- libvterm (system library)
- cffi (Python bindings)

---

## Next Steps

### Phase 2: Basic Terminal
1. Wire up UnixPty - spawn bash, read output
2. Raw mode first (no vterm) - prove PTY→buffer→render pipeline
3. Add cursor rendering (blinking block)
4. Implement vterm cffi bindings
5. Connect vterm callbacks to buffer

### Phase 3: Polish
1. Debounced resize handling
2. Auto-scroll during edge-drag selection
3. Double-click word selection
4. Dirty-region tracking (only redraw changed cells)
5. Performance profiling

### Phase 4: Advanced
1. Windows ConPTY support
2. Kitty graphics protocol
3. Sixel support
4. URL detection/clicking
5. Search in scrollback

---

## Running

```bash
cd velocitermqt
python -m vtqt.main
```

Or:
```bash
python -m venv .venv
source .venv/bin/activate
pip install PyQt6 PyOpenGL numpy
python -m vtqt.main
```

---

## References

- [libvterm](https://www.leonerd.org.uk/code/libvterm/) - VT220/xterm emulation
- [KodoTerm](https://github.com/diegoiast/KodoTerm) - Qt6/libvterm reference (MIT)
- [Neovim terminal.c](https://github.com/neovim/neovim/blob/master/src/nvim/terminal.c) - libvterm integration
- [Windows ConPTY](https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/)

---

*Session 1 completed: 2025-01-07*
*GPU rendering PoC validated, architecture established*