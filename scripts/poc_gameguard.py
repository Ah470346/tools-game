#!/usr/bin/env python3
"""
scripts/poc_gameguard.py

Spike/POC script to test:
1) Screen capture using DXcam, PrintWindow, or GDI BitBlt.
2) Simulated input using pydirectinput and direct ctypes SendInput.
3) Frame rate (FPS) measurements.

Run this script on a Windows machine with the Priston Tale game client active.
"""

import os
import sys
import time
import traceback

# Define window title search pattern
WINDOW_SEARCH_PATTERN = "Priston"


def check_dependencies():
    """Checks and prints status of required libraries."""
    dependencies = ["win32gui", "win32ui", "win32con", "dxcam", "pydirectinput", "cv2", "numpy"]
    print("Checking dependencies...")
    missing = []
    for dep in dependencies:
        try:
            if dep == "cv2":
                import cv2
            else:
                __import__(dep)
            print(f"  [+] {dep}: Available")
        except ImportError:
            print(f"  [-] {dep}: Missing")
            missing.append(dep)
    
    if missing:
        print(f"\nMissing dependencies: {', '.join(missing)}")
        print("Please install them using: pip install pywin32 dxcam pydirectinput opencv-python numpy")
        if sys.platform != 'win32':
            print("\nWARNING: You are not running on Windows! This script requires Windows APIs to function.")
            print("You can inspect the code, but execution will fail.")
            return False
    return True


if sys.platform == 'win32':
    import win32gui
    import win32ui
    import win32con
    import win32process
    import ctypes
    from ctypes import wintypes
    import numpy as np
    import cv2

    # --- Windows Ctypes Structs for Direct SendInput Fallback ---
    # In case pydirectinput is blocked, direct SendInput with hardware-like scan codes can be tried.
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KeyBdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", PUL)
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD)
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", PUL)
        ]

    class Input_I(ctypes.Union):
        _fields_ = [
            ("ki", KeyBdInput),
            ("mi", MouseInput),
            ("hi", HardwareInput)
        ]

    class Input(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("ii", Input_I)
        ]

    # Constants for SendInput
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    KEYEVENTF_KEYDOWN = 0x0000
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def send_direct_key(scancode, release=False):
        """Send keyboard scan code directly via SendInput."""
        flags = KEYEVENTF_SCANCODE
        if release:
            flags |= KEYEVENTF_KEYUP
        
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, flags, 0, ctypes.pointer(extra))
        x = Input(INPUT_KEYBOARD, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def send_direct_mouse_move(x, y):
        """Move mouse to absolute coordinates (0 to 65535) using SendInput."""
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.mi = MouseInput(x, y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, ctypes.pointer(extra))
        x_input = Input(INPUT_MOUSE, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))

    def send_direct_click(x, y):
        """Click at absolute screen coordinates."""
        send_direct_mouse_move(x, y)
        time.sleep(0.05)
        
        extra = ctypes.c_ulong(0)
        ii_down = Input_I()
        ii_down.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
        input_down = Input(INPUT_MOUSE, ii_down)
        
        ii_up = Input_I()
        ii_up.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
        input_up = Input(INPUT_MOUSE, ii_up)
        
        ctypes.windll.user32.SendInput(1, ctypes.pointer(input_down), ctypes.sizeof(input_down))
        time.sleep(0.05)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(input_up), ctypes.sizeof(input_up))

else:
    # Fallback/Mock implementations for non-Windows platforms
    def send_direct_key(scancode, release=False): pass
    def send_direct_mouse_move(x, y): pass
    def send_direct_click(x, y): pass


def get_game_window():
    """Finds the game window handle and rect."""
    if sys.platform != 'win32':
        print("[MOCK] Running on non-Windows. Cannot search for real windows.")
        return None, (0, 0, 800, 600)

    target_hwnd = None
    windows_found = []

    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                windows_found.append((hwnd, title))
                if WINDOW_SEARCH_PATTERN.lower() in title.lower():
                    nonlocal target_hwnd
                    target_hwnd = hwnd

    win32gui.EnumWindows(enum_windows_callback, None)

    if target_hwnd:
        title = win32gui.GetWindowText(target_hwnd)
        rect = win32gui.GetWindowRect(target_hwnd)
        print(f"[+] Found Target Window: '{title}' (HWND: {target_hwnd}) at Rect: {rect}")
        # Bring window to foreground to test inputs properly
        try:
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.5)
        except Exception as e:
            print(f"[!] Warning: Could not set target window to foreground: {e}")
        return target_hwnd, rect
    
    print(f"[-] Target window matching '{WINDOW_SEARCH_PATTERN}' not found.")
    print("\nAvailable visible windows:")
    for hwnd, title in sorted(windows_found, key=lambda x: x[1]):
        print(f"  - HWND: {hwnd:8d} | Title: {title}")
    return None, None


def capture_dxcam(rect):
    """Tries capturing window region using DXcam."""
    try:
        import dxcam
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        
        print(f"Testing DXcam on region: [{left}, {top}, {right}, {bottom}] ({w}x{h})")
        camera = dxcam.create(output_color="BGR")
        
        # Capture a single frame
        frame = camera.grab(region=(left, top, right, bottom))
        if frame is not None:
            return True, frame, "DXcam"
        else:
            # Let's try full screen first and crop manually
            frame_full = camera.grab()
            if frame_full is not None:
                cropped = frame_full[top:bottom, left:right]
                return True, cropped, "DXcam (manual crop)"
            return False, None, "DXcam grabbed None"
    except Exception as e:
        return False, None, f"DXcam error: {e}"


def capture_printwindow(hwnd, rect):
    """Tries capturing window using PrintWindow API (GDI Fallback)."""
    try:
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)
        
        # Try PrintWindow
        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
        if not result:
            result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
            
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype='uint8')
        img.shape = (h, w, 4)
        
        # Cleanup
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        if result and img is not None:
            bgr_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return True, bgr_img, "PrintWindow"
        return False, None, "PrintWindow call failed"
    except Exception as e:
        return False, None, f"PrintWindow error: {e}"


def capture_bitblt(hwnd, rect):
    """Tries capturing window using standard BitBlt GDI copy."""
    try:
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)
        
        saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)
        
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype='uint8')
        img.shape = (h, w, 4)
        
        # Cleanup
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        if img is not None:
            bgr_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return True, bgr_img, "BitBlt"
        return False, None, "BitBlt returned empty image"
    except Exception as e:
        return False, None, f"BitBlt error: {e}"


def benchmark_fps(capture_func, hwnd, rect, num_frames=100):
    """Measures performance of a capture method over 100 frames."""
    print(f"Benchmarking FPS over {num_frames} frames...")
    start_time = time.time()
    success_count = 0
    
    for _ in range(num_frames):
        if capture_func == "dxcam":
            success, _, _ = capture_dxcam(rect)
        elif capture_func == "printwindow":
            success, _, _ = capture_printwindow(hwnd, rect)
        elif capture_func == "bitblt":
            success, _, _ = capture_bitblt(hwnd, rect)
        else:
            success = False
            
        if success:
            success_count += 1
            
    elapsed = time.time() - start_time
    fps = success_count / elapsed if elapsed > 0 else 0
    print(f"Benchmark completed: Captured {success_count}/{num_frames} frames in {elapsed:.2f}s. Avg FPS: {fps:.2f}")
    return fps, success_count


def test_inputs(hwnd, rect):
    """Sends test inputs to the game window and asks user for verification."""
    print("\n--- Starting Input Simulation Tests ---")
    left, top, right, bottom = rect
    center_x = left + (right - left) // 2
    center_y = top + (bottom - top) // 2
    
    pydirectinput_ok = False
    direct_input_ok = False
    
    # 1. Test Mouse Move & Click using pydirectinput
    try:
        import pydirectinput
        print("[*] Testing input: pydirectinput Move & Click...")
        print(f"Moving to center of game window: ({center_x}, {center_y})")
        pydirectinput.moveTo(center_x, center_y)
        time.sleep(0.5)
        pydirectinput.click()
        pydirectinput_ok = True
        print("[+] pydirectinput simulation sent successfully.")
    except Exception as e:
        print(f"[-] pydirectinput failed: {e}")

    # 2. Test direct hardware keyboard scan codes (Direct Input fallback)
    print("[*] Testing input: Direct Hardware Input via SendInput (ctypes)...")
    try:
        # Spacebar scan code = 0x39
        print("Sending Space press...")
        send_direct_key(0x39, release=False) # Key down
        time.sleep(0.1)
        send_direct_key(0x39, release=True)  # Key up
        
        time.sleep(0.5)
        print(f"Sending ctypes SendInput Click at: ({center_x + 50}, {center_y})")
        
        screen_w = 1920
        screen_h = 1080
        try:
            import win32api
            screen_w = win32api.GetSystemMetrics(0)
            screen_h = win32api.GetSystemMetrics(1)
        except ImportError:
            pass
            
        norm_x = int((center_x + 50) * 65535 / screen_w)
        norm_y = int(center_y * 65535 / screen_h)
        send_direct_click(norm_x, norm_y)
        
        direct_input_ok = True
        print("[+] Direct SendInput simulation sent successfully.")
    except Exception as e:
        print(f"[-] Direct SendInput failed: {e}")
        traceback.print_exc()

    return pydirectinput_ok, direct_input_ok


def main():
    print("==================================================")
    print("      Priston Tale VTC - GameGuard POC Script     ")
    print("==================================================")
    
    if not check_dependencies():
        if sys.platform != 'win32':
            return
            
    hwnd, rect = get_game_window()
    if not hwnd:
        print("\n[!] CRITICAL: Target game window not found.")
        print("Please start Priston Tale VTC and ensure it is not minimized.")
        return

    print("\n--- Starting Capture Method Tests ---")
    
    # 1. DXcam capture
    print("\n[1] Testing DXcam Capture...")
    dxcam_success, dxcam_img, dxcam_details = capture_dxcam(rect)
    if dxcam_success:
        cv2.imwrite("dxcam_capture.png", dxcam_img)
        print(f"[+] DXcam capture SUCCESS. Saved to dxcam_capture.png. Resolution: {dxcam_img.shape}")
    else:
        print(f"[-] DXcam capture FAILED: {dxcam_details}")

    # 2. PrintWindow capture
    print("\n[2] Testing PrintWindow Capture...")
    pw_success, pw_img, pw_details = capture_printwindow(hwnd, rect)
    if pw_success:
        cv2.imwrite("printwindow_capture.png", pw_img)
        print(f"[+] PrintWindow capture SUCCESS. Saved to printwindow_capture.png. Resolution: {pw_img.shape}")
    else:
        print(f"[-] PrintWindow capture FAILED: {pw_details}")

    # 3. BitBlt capture
    print("\n[3] Testing BitBlt Capture...")
    bb_success, bb_img, bb_details = capture_bitblt(hwnd, rect)
    if bb_success:
        cv2.imwrite("bitblt_capture.png", bb_img)
        print(f"[+] BitBlt capture SUCCESS. Saved to bitblt_capture.png. Resolution: {bb_img.shape}")
    else:
        print(f"[-] BitBlt capture FAILED: {bb_details}")

    # Find the best capture method that succeeded
    best_capture = None
    if dxcam_success:
        best_capture = "dxcam"
    elif pw_success:
        best_capture = "printwindow"
    elif bb_success:
        best_capture = "bitblt"

    fps = 0.0
    if best_capture:
        print(f"\n[+] Selected '{best_capture}' as the best working method for benchmarking.")
        fps, _ = benchmark_fps(best_capture, hwnd, rect, num_frames=100)
    else:
        print("\n[-] ERROR: All capture methods failed to capture the screen.")

    # Input verification
    pydirectinput_ok, direct_input_ok = test_inputs(hwnd, rect)

    # Prompt user verification
    print("\n==================================================")
    print("                 POC REPORT CARD                  ")
    print("==================================================")
    
    capture_status = "NO"
    capture_method = "None"
    if dxcam_success:
        capture_status = "YES"
        capture_method = "DXcam"
    elif pw_success:
        capture_status = "YES"
        capture_method = "PrintWindow"
    elif bb_success:
        capture_status = "YES"
        capture_method = "BitBlt"
        
    input_status = "NO"
    if pydirectinput_ok or direct_input_ok:
        input_status = "YES"
        input_details = []
        if pydirectinput_ok: input_details.append("pydirectinput")
        if direct_input_ok: input_details.append("Direct SendInput")
        input_status += f" ({', '.join(input_details)})"
        
    print(f"| Metric                     | Result                             |")
    print(f"|----------------------------|------------------------------------|")
    print(f"| Capture Works?             | {capture_status:<34} |")
    print(f"| Capture Method             | {capture_method:<34} |")
    print(f"| Average Capture FPS        | {fps:<34.2f} |")
    print(f"| Simulated Input Works?     | {input_status:<34} |")
    print(f"| GameGuard Interference?    | [Check Game Console & Client]      |")
    print("==================================================")
    print("\nAction required by User:")
    print("1. Verify the generated capture images (dxcam_capture.png, printwindow_capture.png, bitblt_capture.png). Do they show correct game frame pixels or are they black/incorrect?")
    print("2. Confirm whether you saw the character jump (Space key) and mouse click/move during the input phase.")
    print("3. Check if GameGuard popped up a security alert, disconnected, or closed the game.")
    print("\nAfter manual check, please respond to this agent with the table results & Go/No-Go decision.")
    print("==================================================")


if __name__ == "__main__":
    main()
