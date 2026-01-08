"""
GPU Renderer - OpenGL text grid rendering with glyph atlas.

Uses immediate mode OpenGL for broad compatibility.
Future: migrate to instanced rendering with VBOs.
"""

from typing import Optional, Dict, Tuple
import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics, QImage, QPainter, QColor

from OpenGL.GL import (
    glEnable, glDisable, glBlendFunc, glClear, glClearColor,
    glGenTextures, glBindTexture, glTexImage2D, glTexParameteri,
    glBegin, glEnd, glVertex2f, glTexCoord2f, glColor3f, glColor4f,
    GL_TEXTURE_2D, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
    GL_RGBA, GL_UNSIGNED_BYTE, GL_LINEAR, GL_CLAMP_TO_EDGE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
    GL_QUADS
)


class GlyphAtlas:
    """
    Texture atlas containing rendered glyphs.
    
    Generates a texture with all printable ASCII + box drawing characters.
    Each glyph is rendered into a fixed-size cell.
    """
    
    # Character ranges to include
    CHAR_RANGES = [
        (32, 127),      # Printable ASCII
        (0x2500, 0x257F),  # Box drawing
        (0x2580, 0x259F),  # Block elements
    ]
    
    def __init__(self):
        self.texture_id: int = 0
        self.cell_width: int = 0
        self.cell_height: int = 0
        self.atlas_width: int = 0
        self.atlas_height: int = 0
        self.cols: int = 0
        self.rows: int = 0
        
        # Map character code -> (u, v, u2, v2) texture coords
        self._char_to_uv: Dict[int, Tuple[float, float, float, float]] = {}
        
        # Characters in atlas order
        self._chars: list = []
    
    def generate(self, font: QFont) -> bool:
        """Generate atlas texture for given font."""
        
        # Get font metrics
        metrics = QFontMetrics(font)
        self.cell_width = metrics.horizontalAdvance('M')
        self.cell_height = metrics.height()
        
        # Ensure minimum cell size
        self.cell_width = max(self.cell_width, 8)
        self.cell_height = max(self.cell_height, 12)
        
        # Build character list
        self._chars = []
        for start, end in self.CHAR_RANGES:
            for code in range(start, end):
                self._chars.append(chr(code))
        
        # Calculate atlas dimensions (power of 2 friendly)
        num_chars = len(self._chars)
        self.cols = 32  # 32 chars per row
        self.rows = (num_chars + self.cols - 1) // self.cols
        
        self.atlas_width = self.cols * self.cell_width
        self.atlas_height = self.rows * self.cell_height
        
        # Round up to power of 2
        self.atlas_width = self._next_power_of_2(self.atlas_width)
        self.atlas_height = self._next_power_of_2(self.atlas_height)
        
        # Create image
        image = QImage(
            self.atlas_width, self.atlas_height,
            QImage.Format.Format_RGBA8888
        )
        image.fill(QColor(0, 0, 0, 0))  # Transparent background
        
        # Render glyphs
        painter = QPainter(image)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 255))  # White glyphs
        
        for i, char in enumerate(self._chars):
            col = i % self.cols
            row = i // self.cols
            
            x = col * self.cell_width
            y = row * self.cell_height
            
            # Draw character
            painter.drawText(
                x, y + metrics.ascent(),
                char
            )
            
            # Calculate UV coordinates
            u1 = x / self.atlas_width
            v1 = y / self.atlas_height
            u2 = (x + self.cell_width) / self.atlas_width
            v2 = (y + self.cell_height) / self.atlas_height
            
            self._char_to_uv[ord(char)] = (u1, v1, u2, v2)
        
        painter.end()
        
        # Upload to OpenGL texture
        self.texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        # Convert QImage to bytes
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        data = bytes(ptr)
        
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA,
            self.atlas_width, self.atlas_height,
            0, GL_RGBA, GL_UNSIGNED_BYTE, data
        )
        
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        
        glBindTexture(GL_TEXTURE_2D, 0)
        
        return True
    
    def get_uv(self, char_code: int) -> Tuple[float, float, float, float]:
        """Get UV coordinates for character. Returns space if not found."""
        return self._char_to_uv.get(char_code, self._char_to_uv.get(32, (0, 0, 0, 0)))
    
    @staticmethod
    def _next_power_of_2(n: int) -> int:
        """Round up to next power of 2."""
        n -= 1
        n |= n >> 1
        n |= n >> 2
        n |= n >> 4
        n |= n >> 8
        n |= n >> 16
        return n + 1


class GridRenderer:
    """
    Renders text grid using OpenGL.
    
    Two-pass rendering:
    1. Background colors (solid quads)
    2. Glyphs (textured quads with alpha blend)
    """
    
    def __init__(self, parent=None):
        self.parent = parent
        self.atlas: Optional[GlyphAtlas] = None
        self.cell_width: int = 0
        self.cell_height: int = 0
    
    def initialize(self, font: QFont):
        """Initialize renderer with font."""
        self.atlas = GlyphAtlas()
        self.atlas.generate(font)
        self.cell_width = self.atlas.cell_width
        self.cell_height = self.atlas.cell_height
    
    def update_font(self, font: QFont):
        """Update font (regenerate atlas)."""
        if self.atlas:
            # Delete old texture
            pass  # TODO: glDeleteTextures
        self.initialize(font)
    
    def render(self, cell_data: np.ndarray, viewport_size: Tuple[int, int]):
        """
        Render cell grid.
        
        Args:
            cell_data: numpy array (rows, cols, 8)
                       [char_code, fg_r, fg_g, fg_b, bg_r, bg_g, bg_b, attrs]
            viewport_size: (width, height) in pixels
        """
        if self.atlas is None or cell_data is None:
            return
        
        rows, cols = cell_data.shape[:2]
        vp_width, vp_height = viewport_size
        
        # Setup orthographic projection (0,0 at top-left)
        from OpenGL.GL import (
            glMatrixMode, glLoadIdentity, glOrtho,
            GL_PROJECTION, GL_MODELVIEW
        )
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, vp_width, vp_height, 0, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Pass 1: Background colors
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        
        glBegin(GL_QUADS)
        for row in range(rows):
            for col in range(cols):
                cell = cell_data[row, col]
                bg_r, bg_g, bg_b = cell[4], cell[5], cell[6]
                
                x1 = col * self.cell_width
                y1 = row * self.cell_height
                x2 = x1 + self.cell_width
                y2 = y1 + self.cell_height
                
                glColor3f(bg_r, bg_g, bg_b)
                glVertex2f(x1, y1)
                glVertex2f(x2, y1)
                glVertex2f(x2, y2)
                glVertex2f(x1, y2)
        glEnd()
        
        # Pass 2: Glyphs
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glBindTexture(GL_TEXTURE_2D, self.atlas.texture_id)
        
        glBegin(GL_QUADS)
        for row in range(rows):
            for col in range(cols):
                cell = cell_data[row, col]
                char_code = int(cell[0])
                fg_r, fg_g, fg_b = cell[1], cell[2], cell[3]
                
                # Skip space characters (optimization)
                if char_code <= 32:
                    continue
                
                x1 = col * self.cell_width
                y1 = row * self.cell_height
                x2 = x1 + self.cell_width
                y2 = y1 + self.cell_height
                
                u1, v1, u2, v2 = self.atlas.get_uv(char_code)
                
                glColor3f(fg_r, fg_g, fg_b)
                
                glTexCoord2f(u1, v1)
                glVertex2f(x1, y1)
                
                glTexCoord2f(u2, v1)
                glVertex2f(x2, y1)
                
                glTexCoord2f(u2, v2)
                glVertex2f(x2, y2)
                
                glTexCoord2f(u1, v2)
                glVertex2f(x1, y2)
        glEnd()
        
        glBindTexture(GL_TEXTURE_2D, 0)
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
