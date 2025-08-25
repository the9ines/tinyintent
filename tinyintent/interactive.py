"""
TinyIntent Interactive CLI

Claude-style interactive interface for TinyIntent with SmallIntent routing.
"""

import os
import sys
import signal
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.text import Text
from rich.markdown import Markdown
from rich import box

console = Console()

class OllamaManager:
    """Manages Ollama service lifecycle."""
    
    def __init__(self):
        self.ollama_process = None
        self.is_running = False
    
    def check_ollama_available(self) -> bool:
        """Check if Ollama is available on the system."""
        try:
            result = subprocess.run(['which', 'ollama'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def check_ollama_running(self) -> bool:
        """Check if Ollama service is already running."""
        try:
            result = subprocess.run(['ollama', 'list'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def start_ollama_service(self) -> bool:
        """Start Ollama service if not running."""
        if self.check_ollama_running():
            console.print("✅ Ollama is already running")
            self.is_running = True
            return True
        
        if not self.check_ollama_available():
            console.print("[red]❌ Ollama not found. Please install Ollama first.[/red]")
            console.print("💡 Visit: https://ollama.ai")
            return False
        
        try:
            console.print("🚀 Starting Ollama service...")
            
            # Start Ollama serve in background
            self.ollama_process = subprocess.Popen(
                ['ollama', 'serve'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            # Wait a moment for startup
            import time
            time.sleep(2)
            
            # Verify it started
            if self.check_ollama_running():
                console.print("✅ Ollama service started successfully")
                self.is_running = True
                return True
            else:
                console.print("[red]❌ Failed to start Ollama service[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]❌ Error starting Ollama: {e}[/red]")
            return False
    
    def stop_ollama_service(self):
        """Stop Ollama service if we started it."""
        if self.ollama_process:
            try:
                # Kill the process group if possible
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(self.ollama_process.pid), signal.SIGTERM)
                else:
                    self.ollama_process.terminate()
                
                self.ollama_process.wait(timeout=5)
                console.print("🛑 Ollama service stopped")
            except (subprocess.TimeoutExpired, ProcessLookupError):
                # Force kill if needed
                try:
                    if hasattr(os, 'killpg'):
                        os.killpg(os.getpgid(self.ollama_process.pid), signal.SIGKILL)
                    else:
                        self.ollama_process.kill()
                except ProcessLookupError:
                    pass  # Already dead
            except Exception as e:
                console.print(f"[yellow]⚠️ Error stopping Ollama: {e}[/yellow]")
            
            self.ollama_process = None
            self.is_running = False

class TinyIntentInteractive:
    """Interactive TinyIntent CLI interface."""
    
    def __init__(self):
        self.ollama_manager = OllamaManager()
        self.session_id = f"interactive-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.setup_environment()
    
    def setup_environment(self):
        """Setup environment for TinyIntent."""
        # Ensure we're in the project root directory
        project_root = Path(__file__).parent.parent
        os.chdir(project_root)
        
        # Add project root to Python path
        sys.path.insert(0, str(project_root))
        
        # Import and setup environment from CLI
        try:
            from .cli import setup_environment
        except ImportError:
            from cli import setup_environment
        setup_environment(quiet=True)
    
    def show_welcome(self):
        """Show welcome message."""
        welcome_text = """
🎯 **TinyIntent Interactive CLI**

Type your queries naturally - TinyIntent will route them intelligently:
• **Information requests** → Local AI generation
• **Helper actions** → Weather, trading, logs, etc.
• **System commands** → Helper management

**Commands:**
• `/help` - Show this help
• `/status` - Show system status  
• `/helper list` - List installed helpers
• `/quit` - Exit TinyIntent

Ready to assist! What would you like to do?
        """
        
        panel = Panel(
            Markdown(welcome_text.strip()),
            title="TinyIntent v2.0.0",
            border_style="cyan",
            box=box.ROUNDED
        )
        console.print(panel)
    
    def show_system_status(self):
        """Show current system status."""
        console.print("\n🔍 **System Status**")
        
        # Check Ollama
        ollama_status = "✅ Running" if self.ollama_manager.check_ollama_running() else "❌ Not running"
        console.print(f"  Ollama: {ollama_status}")
        
        # Check SmallIntent router
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from bridge.router_client import SmallIntentRouter
            router = SmallIntentRouter(require_models=False)
            router_status = "✅ Available" if router.router_available else "❌ Not available"
            models_status = "✅ Loaded" if router.models_available else "❌ Not loaded"
        except Exception:
            router_status = "❌ Error"
            models_status = "❌ Error"
        
        console.print(f"  SmallIntent Router: {router_status}")
        console.print(f"  ML Models: {models_status}")
        
        # Check helpers
        try:
            from package_registry import get_package_registry
            registry = get_package_registry()
            status = registry.get_registry_status()
            console.print(f"  Installed Helpers: {status['installed_packages']}/{status['total_packages']}")
        except Exception:
            console.print("  Helpers: ❌ Error loading registry")
    
    async def process_query(self, query: str) -> str:
        """Process a user query through TinyIntent."""
        try:
            # Add project root to path for imports
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            # Import TinyIntent components
            from bridge.router_client import SmallIntentRouter
            from bridge.gen_client import async_ollama_client
            from bridge.location_service import create_location_context
            
            # Import helper components 
            from helpers.executor import HelperExecutor
            from helpers.registry import HelperRegistry
            
            # Initialize components
            try:
                router_client = SmallIntentRouter(require_models=False)
            except Exception:
                router_client = None
            
            # Route the query
            if router_client and router_client.router_available and router_client.models_available:
                try:
                    route_result = router_client.route_request(query, session_id=self.session_id)
                    route_used = route_result["route"]
                    router_confidence = route_result.get("confidence", 0.0)
                    intent = route_result.get("intent", "unknown")
                    
                    # Override router for helper requests that are misclassified as "gen"
                    query_lower = query.lower()
                    
                    # Weather helper override
                    if (route_used == "gen" and 
                        any(word in query_lower for word in ["weather", "temperature", "forecast", "rain", "hot", "cold", "conditions"]) and
                        router_confidence < 0.8):  # Only override if router is not very confident
                        console.print(f"[dim]🔄 Overriding router decision: {route_used} -> act for weather query[/dim]")
                        route_used = "act"
                        intent = "weather_override"
                    
                    # System monitoring helper override
                    elif (route_used == "gen" and 
                          any(word in query_lower for word in ["cpu", "memory", "ram", "disk", "system", "performance", "monitor", "usage", "stats", "load", "processes"]) and
                          router_confidence < 0.8):
                        console.print(f"[dim]🔄 Overriding router decision: {route_used} -> act for system monitoring query[/dim]")
                        route_used = "act"
                        intent = "system_monitor_override"
                        
                except Exception as e:
                    console.print(f"[yellow]⚠️ Router failed, using fallback: {e}[/yellow]")
                    route_used, router_confidence, intent = self._fallback_routing(query)
            else:
                route_used, router_confidence, intent = self._fallback_routing(query)
            
            # Process based on route
            if route_used == "gen":
                return await self._handle_generation(query, intent, router_confidence)
            elif route_used == "act":
                return await self._handle_action(query, intent, router_confidence)
            else:
                return "I'm not sure how to handle that request."
                
        except Exception as e:
            return f"Error processing query: {e}"
    
    def _fallback_routing(self, query: str) -> tuple:
        """Simple fallback routing logic."""
        query_lower = query.lower()
        
        # Check for action keywords first
        if any(word in query_lower for word in [
            # Weather keywords
            "weather", "temperature", "forecast", "rain", "hot", "cold", "conditions",
            # Trading keywords
            "trade", "position", "crypto", "bot", "close", "buy", "sell", 
            # System monitoring keywords
            "cpu", "memory", "ram", "disk", "system", "performance", "monitor", "usage", "stats", "load", "processes",
            # Log monitoring keywords
            "log", "error", "tail", "check"
        ]):
            return "act", 0.0, "fallback_action"
        
        # Default to generation for questions
        elif any(word in query_lower for word in ["what", "how", "why", "when", "where", "explain", "tell me"]):
            return "gen", 0.0, "fallback_question"
        
        # Default to action for commands
        else:
            return "act", 0.0, "fallback_command"
    
    async def _handle_generation(self, query: str, intent: str, confidence: float) -> str:
        """Handle generation requests."""
        try:
            # Import generation client
            from bridge.gen_client import async_ollama_client
            
            model = os.environ.get('OLLAMA_MODEL', 'llama3.2:3b')
            prompt = f"Answer this question concisely: {query}"
            
            response_text, latency_ms = await async_ollama_client.generate_async(
                model=model,
                prompt=prompt,
                session_id=self.session_id
            )
            
            return response_text.strip()
            
        except Exception as e:
            return f"Generation failed: {e}"
    
    async def _handle_action(self, query: str, intent: str, confidence: float) -> str:
        """Handle action requests."""
        try:
            # Ensure project root is in path for proper imports
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from helpers.executor import HelperExecutor
            from helpers.registry import HelperRegistry
            from bridge.location_service import create_location_context
            
            # Initialize registry with explicit project root
            registry = HelperRegistry()
            executor = HelperExecutor(registry)
            
            # Match helpers based on query keywords
            query_lower = query.lower()
            helper_candidates = []
            
            if any(word in query_lower for word in ["weather", "temperature", "forecast", "rain", "hot", "cold", "conditions"]):
                helper_candidates.append("weather")
            elif any(word in query_lower for word in ["cpu", "memory", "ram", "disk", "system", "performance", "monitor", "usage", "stats", "load", "processes"]):
                helper_candidates.append("system_monitor")
            elif any(word in query_lower for word in ["trade", "position", "crypto", "bot", "close", "buy", "sell"]):
                helper_candidates.append("bot_guard")
            elif any(word in query_lower for word in ["log", "error", "tail", "check"]):
                helper_candidates.append("log_tailer")
            elif any(word in query_lower for word in ["traffic", "route", "drive", "directions"]):
                helper_candidates.append("traffic")
            
            if helper_candidates:
                helper_id = helper_candidates[0]
                
                # Prepare helper input
                helper_input = {"operation": "status", "text": query}
                
                # Special handling for weather
                if helper_id == "weather":
                    helper_input = {
                        "operation": "current",
                        "units": "imperial",
                        "include_forecast": "forecast" in query_lower
                    }
                
                # Special handling for system monitoring
                elif helper_id == "system_monitor":
                    # Determine operation based on query
                    if "cpu" in query_lower:
                        helper_input = {"operation": "cpu", "format": "summary"}
                    elif "memory" in query_lower or "ram" in query_lower:
                        helper_input = {"operation": "memory", "format": "summary"}
                    elif "disk" in query_lower:
                        helper_input = {"operation": "disk", "format": "summary"}
                    elif "processes" in query_lower:
                        helper_input = {"operation": "processes", "format": "summary", "process_limit": 5}
                    else:
                        helper_input = {"operation": "overview", "format": "summary"}
                
                # Special handling for trading
                elif helper_id == "bot_guard":
                    if "close" in query_lower:
                        helper_input["operation"] = "close_position"
                    elif "position" in query_lower or "status" in query_lower:
                        helper_input["operation"] = "get_positions"
                
                # Special handling for traffic
                elif helper_id == "traffic":
                    helper_input = {"operation": "current_traffic"}
                
                # Create default location context
                location_context = create_location_context()
                
                # Execute helper (use execute for safe helpers that don't modify system state)
                if helper_id in ["weather", "system_monitor"]:
                    # These helpers are safe - they only read data
                    result = executor.execute(helper_id, helper_input, 
                                            session_id=self.session_id, 
                                            location_context=location_context)
                else:
                    # Use preview for other helpers that might modify system state
                    result = executor.preview(helper_id, helper_input, 
                                            session_id=self.session_id, 
                                            location_context=location_context)
                
                if result.get("status") == "success":
                    # For weather helper, get the detailed message
                    if helper_id == "weather" and "result" in result:
                        weather_result = result["result"]
                        return weather_result.get("message", result.get("message", f"Weather information retrieved"))
                    # For system_monitor helper, get the summary
                    elif helper_id == "system_monitor" and "result" in result:
                        system_result = result["result"]
                        if "summary" in system_result:
                            return system_result["summary"]
                        else:
                            return result.get("message", "System monitoring completed")
                    else:
                        return result.get("message", f"Action completed: {query}")
                else:
                    return f"Action failed: {result.get('message', 'Unknown error')}"
            
            else:
                return f"I understand you want to take an action: '{query}'. However, I'm not sure which specific helper to use. Try being more specific (weather, trading, logs, etc.)."
                
        except Exception as e:
            return f"Action failed: {e}"
    
    def handle_command(self, command: str) -> bool:
        """Handle special commands. Returns True if command was handled."""
        if command.startswith("/"):
            cmd = command[1:].strip().lower()
            
            if cmd == "help":
                self.show_welcome()
                return True
            
            elif cmd == "status":
                self.show_system_status()
                return True
            
            elif cmd == "quit" or cmd == "exit":
                return False  # Signal to exit
            
            elif cmd.startswith("helper "):
                # Route to helper CLI
                try:
                    try:
                        from .helper_cli import main as helper_main
                    except ImportError:
                        from helper_cli import main as helper_main
                    args = cmd.split()[1:]  # Remove 'helper' prefix
                    helper_main(args)
                except Exception as e:
                    console.print(f"[red]Helper command failed: {e}[/red]")
                return True
            
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                console.print("Type `/help` for available commands.")
                return True
        
        return False  # Not a command
    
    async def run_interactive_loop(self):
        """Main interactive loop."""
        try:
            while True:
                # Get user input
                query = Prompt.ask("\n[bold cyan]TinyIntent[/bold cyan]", default="")
                
                if not query.strip():
                    continue
                
                # Handle special commands
                if self.handle_command(query):
                    if query.lower() in ["/quit", "/exit"]:
                        break
                    continue
                
                # Process query with loading indicator
                with console.status("[bold green]Processing...") as status:
                    response = await self.process_query(query)
                
                # Display response
                response_panel = Panel(
                    response,
                    title="Response",
                    border_style="green",
                    box=box.ROUNDED
                )
                console.print(response_panel)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
        except Exception as e:
            console.print(f"[red]Error in interactive loop: {e}[/red]")
    
    async def start(self):
        """Start the interactive TinyIntent session."""
        # Start Ollama service
        if not self.ollama_manager.start_ollama_service():
            console.print("[yellow]⚠️ Continuing without Ollama (some features may be limited)[/yellow]")
        
        # Show welcome
        self.show_welcome()
        
        try:
            # Run interactive loop
            await self.run_interactive_loop()
        finally:
            # Cleanup
            self.ollama_manager.stop_ollama_service()
    
    def stop(self):
        """Stop the interactive session."""
        self.ollama_manager.stop_ollama_service()

def run_interactive():
    """Entry point for interactive mode."""
    interactive = TinyIntentInteractive()
    
    def signal_handler(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        interactive.stop()
        sys.exit(0)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(interactive.start())
    except KeyboardInterrupt:
        pass
    finally:
        interactive.stop()

if __name__ == "__main__":
    run_interactive()