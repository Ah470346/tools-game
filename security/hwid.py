"""
security/hwid.py

Utility for generating a unique hardware ID (HWID) based on machine characteristics.
Used to bind an offline license key to a specific physical machine.
"""

import hashlib
import platform
import subprocess
import logging

logger = logging.getLogger(__name__)

def get_hardware_id() -> str:
    """
    Retrieves a unique hardware identifier for the current machine.
    On Windows, it uses the WMI CSProduct UUID.
    Returns a SHA-256 hash (hex string) of the identifier to preserve privacy
    and ensure a fixed length.
    
    Returns:
        str: 64-character hexadecimal SHA-256 hash.
    """
    hwid = ""
    
    try:
        if platform.system() == "Windows":
            # wmic is standard on Windows and provides a unique UUID
            output = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"],
                stderr=subprocess.STDOUT,
                text=True
            )
            # The output contains the header "UUID" followed by the actual UUID.
            lines = output.strip().split("\n")
            if len(lines) >= 2:
                hwid = lines[1].strip()
            
            # Fallback if wmic fails or returns empty
            if not hwid or hwid.lower() == "ffffffff-ffff-ffff-ffff-ffffffffffff":
                # Try getting MachineGuid from registry
                import winreg
                registry = winreg.HKEY_LOCAL_MACHINE
                address = r"SOFTWARE\Microsoft\Cryptography"
                key = winreg.OpenKey(registry, address, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                winreg.CloseKey(key)
                hwid = value
                
        elif platform.system() == "Darwin":
            output = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True
            )
            for line in output.split('\n'):
                if "IOPlatformUUID" in line:
                    hwid = line.split('=')[1].strip().strip('"')
                    break
        elif platform.system() == "Linux":
            with open("/etc/machine-id", "r") as f:
                hwid = f.read().strip()
                
    except Exception as e:
        logger.error("Failed to retrieve native HWID: %s", e)
        # Final fallback to node name if all else fails, but it's easily spoofed.
        hwid = platform.node()

    # Hash the retrieved ID to ensure consistency and fixed length (64 chars)
    if not hwid:
        hwid = "UNKNOWN_HWID_FALLBACK"
        
    return hashlib.sha256(hwid.encode('utf-8')).hexdigest()
