"""
VelociTermQt - Entry Point

Usage:
    python -m vtqt.main              # Terminal mode (default)
    python -m vtqt.main --viewer     # File viewer mode
    python -m vtqt.main <file>       # Open file in viewer
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description='VelociTermQt - GPU Terminal')
    parser.add_argument('file', nargs='?', help='File to open in viewer mode')
    parser.add_argument('--viewer', action='store_true', 
                        help='Start in file viewer mode')
    parser.add_argument('--terminal', action='store_true',
                        help='Start in terminal mode (default)')
    args = parser.parse_args()
    
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("VelociTermQt")
    
    if args.viewer or args.file:
        # File viewer mode
        from .main_window import TextViewerWindow
        window = TextViewerWindow()
        if args.file:
            window.text_widget.load_file(args.file)
            window.setWindowTitle(f"GPU Text Viewer - {args.file}")
    else:
        # Terminal mode (default)
        from .terminal_window import TerminalWindow
        window = TerminalWindow()
    
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
