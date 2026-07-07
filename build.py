import os
import shutil
import subprocess

def main():
    print("--- Priston Tale Auto Tool - Build Script ---")
    
    # Run PyInstaller
    # --noconsole hides the black terminal window.
    # --onefile makes it a single executable.
    # --add-data includes customtkinter assets (if running from site-packages).
    
    print("Building executable with PyInstaller...")
    subprocess.run([
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "PristonTaleBot",
        "--collect-all", "customtkinter",
        "main.py"
    ], check=True)
    
    print("Build complete! Preparing release folder...")
    
    release_dir = "release_build"
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)
    os.makedirs(release_dir)
    
    # Move the EXE
    shutil.copy(os.path.join("dist", "PristonTaleBot.exe"), release_dir)
    
    # Copy Configs (Create a clean default settings.json)
    config_dir = os.path.join(release_dir, "config")
    os.makedirs(config_dir)
    
    # We write a clean settings.json without the developer's license key!
    default_settings = {
        "mode": "direct",
        "window_title": "Priston Tale",
        "license_key": "",
        "capture": {"backend": "auto"},
        "combat": {
            "target_source": "yolo",
            "left_click": {"enabled": True, "interval_sec": 0.5},
            "right_click": {"enabled": False, "interval_sec": 1.0}
        },
        "thresholds": {
            "hp": [{"percent": 75, "key": "1", "cooldown_sec": 1.0}],
            "mp": [{"percent": 50, "key": "4", "cooldown_sec": 2.0}],
            "stm": [{"percent": 40, "key": "3", "cooldown_sec": 2.0}]
        },
        "loot": {"enabled": True, "scan_key": "a"}
    }
    import json
    with open(os.path.join(config_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(default_settings, f, indent=2)
        
    # Copy whitelist
    if os.path.exists(os.path.join("config", "loot_whitelist.json")):
        shutil.copy(os.path.join("config", "loot_whitelist.json"), config_dir)
        
        # Copy models if they exist
    if os.path.exists("models"):
        shutil.copytree("models", os.path.join(release_dir, "models"))
        
    print("\nCompressing into ZIP file...")
    zip_filename = "PristonTaleBot_Release"
    shutil.make_archive(zip_filename, 'zip', release_dir)
        
    print(f"\nSUCCESS! Your client-ready bot is available at: {zip_filename}.zip")
    print("You can upload this ZIP file to Google Drive, MediaFire, or send it directly via Zalo/Telegram to your clients.")
    print("Notice: The 'scripts' folder (including your private key) was NOT included!")

if __name__ == "__main__":
    main()
