#!/usr/bin/env python3
"""
TinyIntent Autopilot Control - M5.5: Autopilot Management

Controls the scheduled autopilot learning system using launchd on macOS.
Provides easy enable/disable/status commands for operators.
"""

import argparse
import subprocess
import sys
from pathlib import Path


class AutopilotController:
    """Controls TinyIntent autopilot scheduling via launchd"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.plist_source = project_root / "com.tinyintent.autopilot.plist"
        self.plist_target = Path.home() / "Library/LaunchAgents/com.tinyintent.autopilot.plist"
        self.service_label = "com.tinyintent.autopilot"
    
    def is_installed(self) -> bool:
        """Check if autopilot service is installed"""
        return self.plist_target.exists()
    
    def is_loaded(self) -> bool:
        """Check if autopilot service is loaded/active"""
        try:
            result = subprocess.run(
                ['launchctl', 'list', self.service_label],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def install(self) -> bool:
        """Install autopilot service"""
        if not self.plist_source.exists():
            print(f"❌ Source plist not found: {self.plist_source}")
            return False
        
        try:
            # Create LaunchAgents directory if it doesn't exist
            self.plist_target.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy plist file
            import shutil
            shutil.copy2(self.plist_source, self.plist_target)
            print(f"✅ Installed autopilot plist to {self.plist_target}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to install autopilot service: {e}")
            return False
    
    def load(self) -> bool:
        """Load/start autopilot service"""
        if not self.is_installed():
            if not self.install():
                return False
        
        try:
            result = subprocess.run(
                ['launchctl', 'load', str(self.plist_target)],
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ Autopilot service loaded and scheduled")
            return True
            
        except subprocess.CalledProcessError as e:
            if "already loaded" in e.stderr.lower():
                print("✅ Autopilot service already loaded")
                return True
            else:
                print(f"❌ Failed to load autopilot service: {e.stderr}")
                return False
        except Exception as e:
            print(f"❌ Failed to load autopilot service: {e}")
            return False
    
    def unload(self) -> bool:
        """Unload/stop autopilot service"""
        try:
            result = subprocess.run(
                ['launchctl', 'unload', str(self.plist_target)],
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ Autopilot service unloaded")
            return True
            
        except subprocess.CalledProcessError as e:
            if "not loaded" in e.stderr.lower():
                print("✅ Autopilot service was not loaded")
                return True
            else:
                print(f"❌ Failed to unload autopilot service: {e.stderr}")
                return False
        except Exception as e:
            print(f"❌ Failed to unload autopilot service: {e}")
            return False
    
    def uninstall(self) -> bool:
        """Uninstall autopilot service"""
        # First unload if loaded
        if self.is_loaded():
            if not self.unload():
                return False
        
        # Remove plist file
        try:
            if self.plist_target.exists():
                self.plist_target.unlink()
                print(f"✅ Removed autopilot plist from {self.plist_target}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to uninstall autopilot service: {e}")
            return False
    
    def status(self) -> dict:
        """Get autopilot service status"""
        status = {
            "installed": self.is_installed(),
            "loaded": self.is_loaded(),
            "plist_source": self.plist_source.exists(),
            "plist_target": str(self.plist_target) if self.plist_target.exists() else None
        }
        
        # Get detailed service info if loaded
        if status["loaded"]:
            try:
                result = subprocess.run(
                    ['launchctl', 'list', self.service_label],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # Parse launchctl output for PID and status
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:  # Header + data
                    parts = lines[1].split('\t')
                    if len(parts) >= 3:
                        status["pid"] = parts[0] if parts[0] != '-' else None
                        status["last_exit_code"] = parts[1] if parts[1] != '-' else None
                        status["label"] = parts[2]
                        
            except Exception:
                pass  # Status already shows loaded=True
        
        return status
    
    def print_status(self):
        """Print human-readable status"""
        status = self.status()
        
        print("🤖 TinyIntent Autopilot Status")
        print("=" * 30)
        
        if not status["plist_source"]:
            print("❌ Source configuration missing")
            print(f"   Expected: {self.plist_source}")
            return
        
        print(f"📁 Source config: ✅ {self.plist_source}")
        
        if status["installed"]:
            print(f"📦 Installed: ✅ {status['plist_target']}")
        else:
            print("📦 Installed: ❌ Not installed")
        
        if status["loaded"]:
            print("🟢 Service: Active (scheduled daily at 3:00 AM)")
            if "pid" in status and status["pid"]:
                print(f"   Process ID: {status['pid']}")
            if "last_exit_code" in status:
                exit_code = status["last_exit_code"]
                if exit_code == "0":
                    print("   Last run: ✅ Success")
                elif exit_code and exit_code != "-":
                    print(f"   Last run: ❌ Failed (exit code {exit_code})")
        else:
            print("🔴 Service: Inactive")
        
        print()
        print("💡 Commands:")
        print("   python3 scripts/autopilot_control.py enable   # Start autopilot")
        print("   python3 scripts/autopilot_control.py disable  # Stop autopilot")
        print("   python3 scripts/autopilot_control.py status   # Show this status")
        print("   make autopilot-dry                           # Test run")


def main():
    parser = argparse.ArgumentParser(
        description="Control TinyIntent autopilot scheduling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/autopilot_control.py status   # Show current status
  python3 scripts/autopilot_control.py enable   # Start daily autopilot
  python3 scripts/autopilot_control.py disable  # Stop autopilot
  python3 scripts/autopilot_control.py install  # Install without starting
  
The autopilot runs daily at 3:00 AM and performs:
  1. Export episodes to training data
  2. Retrain router model
  3. Evaluate model performance
  4. Promote model if it meets safety criteria
        """
    )
    
    parser.add_argument(
        'action',
        choices=['status', 'enable', 'disable', 'install', 'uninstall'],
        help='Action to perform'
    )
    
    args = parser.parse_args()
    
    # Find project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    controller = AutopilotController(project_root)
    
    if args.action == 'status':
        controller.print_status()
    elif args.action == 'enable':
        success = controller.load()
        if success:
            controller.print_status()
        sys.exit(0 if success else 1)
    elif args.action == 'disable':
        success = controller.unload()
        if success:
            controller.print_status()
        sys.exit(0 if success else 1)
    elif args.action == 'install':
        success = controller.install()
        if success:
            controller.print_status()
        sys.exit(0 if success else 1)
    elif args.action == 'uninstall':
        success = controller.uninstall()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()