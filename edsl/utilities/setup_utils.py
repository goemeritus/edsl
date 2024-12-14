import subprocess
import sys
import os


class PlaywrightInstallPlugin:
    def install_browsers(self):
        print("Installing Playwright browsers...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("Successfully installed Playwright browsers")
            if result.stdout:
                print(f"Output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install Playwright browsers: {e}")
            if e.stdout:
                print(f"Output: {e.stdout}")
            if e.stderr:
                print(f"Error: {e.stderr}")
        except Exception as e:
            print(f"Unexpected error during Playwright installation: {e}")
