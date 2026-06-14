import platform
from src.tool.computeruse.exceptions import UnsupportedPlatformError

_adapter_instance = None

def get_platform_adapter():
    global _adapter_instance
    if _adapter_instance is not None:
        return _adapter_instance

    sys_name = platform.system().lower()
    
    if sys_name == "darwin":
        from .macos_adapter import MacOSAdapter
        _adapter_instance = MacOSAdapter()
    elif sys_name == "windows":
        from .windows_adapter import WindowsAdapter
        _adapter_instance = WindowsAdapter()
    else:
        raise UnsupportedPlatformError(sys_name)
        
    return _adapter_instance