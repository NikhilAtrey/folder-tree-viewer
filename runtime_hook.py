
import os
import sys
import ctypes
from ctypes import wintypes

# Add runtime hook to improve antivirus detection
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# Set process DPI awareness
if sys.platform == 'win32':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
