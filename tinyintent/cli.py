"""
TinyIntent CLI - Simple Command Interface

Single command to start TinyIntent with sensible defaults.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def setup_environment(quiet: bool = False):
    """Setup environment with auto-generated secure credentials."""
    from .credentials import apply_credentials_to_environment
    
    # Auto-generate and apply secure credentials if not manually set
    credentials_applied = False
    if 'TINYINTENT_SECRET' not in os.environ or 'SHORTCUT_TOKEN' not in os.environ:
        try:
            secret, token = apply_credentials_to_environment(quiet=True)  # Suppress credential loading logs
            credentials_applied = True
        except Exception as e:
            if not quiet:
                console.print(f"⚠️  [yellow]Failed to load credentials: {e}[/yellow]")
            # Fallback to temporary credentials
            import secrets
            os.environ['TINYINTENT_SECRET'] = secrets.token_urlsafe(48)
            os.environ['SHORTCUT_TOKEN'] = secrets.token_urlsafe(24)
    
    # Set other default environment variables
    defaults = {
        'TINYINTENT_ALLOW_DEV_LOCAL': '1',
        'TINYINTENT_EXECUTION_ENABLED': '1',
        'TINYINTENT_BIND': '0.0.0.0',
        'TINYINTENT_PORT': '8787',
        'TINYINTENT_LOG_LEVEL': 'warning',  # Reduce default log level
        'SHORTCUT_MAX_LEN': '800',
        'NODE_ENV': 'development'
    }
    
    for key, value in defaults.items():
        if key not in os.environ:
            os.environ[key] = value
    
    # Only show warnings for manually set weak credentials
    if not quiet and os.environ.get('TINYINTENT_SECRET', '').startswith('tinyintent-default'):
        console.print("🚨 [red bold]SECURITY WARNING: Using default secret! Set TINYINTENT_SECRET for production![/red bold]")
    
    # Show credentials info if auto-generated (for iPhone setup)
    if credentials_applied and not quiet:
        shortcut_token = os.environ.get('SHORTCUT_TOKEN', '')
        # Truncate token for display (show first 8 and last 4 chars)
        if len(shortcut_token) > 12:
            display_token = f"{shortcut_token[:8]}...{shortcut_token[-4:]}"
        else:
            display_token = shortcut_token
        console.print(f"🔑 [green]iPhone Shortcut Token: {display_token}[/green]")
        console.print("💡 [dim]Use 'tinyintent show-credentials' for full setup info[/dim]")

def show_status():
    """Show TinyIntent system status."""
    console.print("\n🎯 TinyIntent System Status", style="bold blue")
    
    # Environment info
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Server Port", os.environ.get('TINYINTENT_PORT', '8787'))
    table.add_row("Execution Enabled", os.environ.get('TINYINTENT_EXECUTION_ENABLED', 'No'))
    table.add_row("Shortcut Token", "***" + os.environ.get('SHORTCUT_TOKEN', 'not-set')[-4:])
    table.add_row("Environment", os.environ.get('TINYINTENT_ENVIRONMENT', 'development'))
    
    console.print(table)
    
    # Instructions
    instructions = [
        "📱 iPhone Shortcut URL: http://YOUR_IP:8787/shortcut/route",
        "🔑 Use X-Shortcut-Token header with your configured token",
        "📋 API Documentation: http://YOUR_IP:8787/docs",
        "🏥 Health Check: http://YOUR_IP:8787/health"
    ]
    
    console.print("\n📋 Quick Start:", style="bold")
    for instruction in instructions:
        console.print(f"  {instruction}")


def show_credentials(show_secret: bool = False):
    """Show credential information for iPhone setup."""
    from .credentials import get_credential_info
    
    console.print("\n🔑 TinyIntent Credentials", style="bold blue")
    
    try:
        info = get_credential_info(show_secret=show_secret)
        
        if "status" in info:
            console.print(f"❌ {info['status']}")
            console.print("💡 Run 'tinyintent' to generate credentials automatically")
            return
        
        # Credentials table
        table = Table(title="Credential Information")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("iPhone Shortcut Token", info["shortcut_token"])
        table.add_row("API Secret", info["secret_status"])
        table.add_row("Generated At", info["generated_at"])
        table.add_row("Auto Generated", "Yes" if info["auto_generated"] else "No")
        table.add_row("Secret Length", f"{info['secret_length']} characters")
        table.add_row("Token Length", f"{info['token_length']} characters")
        
        console.print(table)
        
        # iPhone setup instructions
        console.print("\n📱 iPhone Shortcut Setup:", style="bold")
        instructions = [
            "1. Open iOS Shortcuts app",
            "2. Create new shortcut with these actions:",
            "   • Dictate Text",
            "   • Get Contents of URL (POST)",
            "   • Speak Text",
            "3. Configure HTTP request:",
            f"   • URL: http://YOUR_IP:8787/shortcut/route",
            f"   • Method: POST",
            f"   • Headers: X-Shortcut-Token: {info['shortcut_token']}",
            f"   • Headers: Content-Type: application/json",
            f"   • Body: {{\"text\": \"[Dictated Text]\"}}"
        ]
        
        for instruction in instructions:
            console.print(f"  {instruction}")
            
        if not show_secret:
            console.print("\n💡 Use 'tinyintent show-credentials --show-secret' to reveal API secret")
        
    except Exception as e:
        console.print(f"❌ Failed to load credentials: {e}")


def regenerate_credentials():
    """Regenerate secure credentials."""
    from .credentials import regenerate_credentials as regen_creds
    
    console.print("\n🔄 Regenerating Credentials", style="bold blue")
    
    try:
        # Confirm action
        console.print("⚠️  This will replace your current credentials.")
        console.print("   iPhone Shortcuts will need to be updated with the new token.")
        
        confirm = console.input("Continue? [y/N]: ")
        if confirm.lower() not in ['y', 'yes']:
            console.print("❌ Cancelled")
            return
        
        # Regenerate
        credentials = regen_creds()
        
        console.print("✅ New credentials generated!")
        console.print(f"🔑 New iPhone Token: {credentials['shortcut_token']}")
        console.print("💡 Use 'tinyintent show-credentials' for full setup info")
        
    except Exception as e:
        console.print(f"❌ Failed to regenerate credentials: {e}")

def start_server(host: str = None, port: int = None, reload: bool = False, quiet: bool = False):
    """Start the TinyIntent bridge server."""
    # Setup environment FIRST before any imports
    setup_environment(quiet=quiet)
    
    # Use environment or provided values
    server_host = host or os.environ.get('TINYINTENT_BIND', '0.0.0.0')
    server_port = port or int(os.environ.get('TINYINTENT_PORT', '8787'))
    log_level = os.environ.get('TINYINTENT_LOG_LEVEL', 'info')
    
    # Show startup info with shortcut token (unless quiet mode)
    if not quiet:
        shortcut_token = os.environ.get('SHORTCUT_TOKEN', '')
        if len(shortcut_token) > 12:
            display_token = f"{shortcut_token[:8]}...{shortcut_token[-4:]}"
        else:
            display_token = shortcut_token
            
        panel = Panel.fit(
            f"🚀 Starting TinyIntent Bridge\n\n"
            f"📡 Server: http://{server_host}:{server_port}\n"
            f"📱 Shortcut: /shortcut/route\n"
            f"🔑 Token: {display_token}\n"
            f"📋 API Docs: /docs\n"
            f"🏥 Health: /health",
            title="TinyIntent v2.0.0",
            border_style="green"
        )
        console.print(panel)
    
    try:
        # Add project root to path for bridge imports
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # Import the FastAPI app from bridge/tinyrpc.py (environment is now set)
        from bridge.tinyrpc import app
        if not quiet:
            console.print("✅ Starting full TinyIntent Bridge...", style="green")
        
        # Configure uvicorn logging to be less verbose
        uvicorn_config = {
            "host": server_host,
            "port": server_port,
            "log_level": log_level,
            "reload": reload,
            "access_log": log_level in ["debug", "info"]  # Disable access logs except in debug/info mode
        }
        
        uvicorn.run(app, **uvicorn_config)
    except ImportError as e:
        # Fallback to simple server if full app not available
        if not quiet:
            console.print(f"⚠️  Full TinyIntent app not available ({e}), starting simple server...", style="yellow")
        from .simple_server import create_simple_app
        app = create_simple_app()
        
        uvicorn_config = {
            "host": server_host,
            "port": server_port,
            "log_level": log_level,
            "reload": reload,
            "access_log": log_level in ["debug", "info"]
        }
        
        uvicorn.run(app, **uvicorn_config)

def main():
    """Main CLI entry point."""
    # Check if no arguments provided - start interactive mode
    if len(sys.argv) == 1:
        from .interactive import run_interactive
        return run_interactive()
    
    # Check if first argument is 'helper' for helper management
    if len(sys.argv) > 1 and sys.argv[1] == 'helper':
        # Route to helper CLI
        from .helper_cli import main as helper_main
        # Pass remaining args to helper CLI
        return helper_main(sys.argv[2:])
    
    parser = argparse.ArgumentParser(
        description="TinyIntent - Voice-Activated AI Assistant Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tinyintent                          # Start interactive CLI (default)
  tinyintent serve                    # Start HTTP server
  tinyintent --port 9000              # Start server on custom port  
  tinyintent --host 127.0.0.1         # Start server on localhost only
  tinyintent --reload                 # Start with auto-reload for development
  tinyintent status                   # Show system status
  tinyintent helper search weather    # Search for helper packages
  tinyintent helper install weather   # Install a helper package
  tinyintent helper list              # List installed helpers
        """
    )
    
    parser.add_argument(
        'command', 
        nargs='?', 
        default='interactive',
        choices=['interactive', 'serve', 'start', 'status', 'help', 'show-credentials', 'regenerate-credentials', 'helper'],
        help='Command to run (default: interactive)'
    )
    
    parser.add_argument(
        '--host',
        default=None,
        help='Server bind address (default: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=None,
        help='Server port (default: 8787)'
    )
    
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimal console output'
    )
    
    parser.add_argument(
        '--show-secret',
        action='store_true',
        help='Show full API secret (use with show-credentials)'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        os.environ['TINYINTENT_LOG_LEVEL'] = 'debug'
    elif args.quiet:
        logging.basicConfig(level=logging.ERROR)
        os.environ['TINYINTENT_LOG_LEVEL'] = 'error'
    
    if args.command == 'status':
        show_status()
    elif args.command == 'help':
        parser.print_help()
    elif args.command == 'show-credentials':
        show_credentials(show_secret=args.show_secret)
    elif args.command == 'regenerate-credentials':
        regenerate_credentials()
    elif args.command == 'helper':
        # This case handles 'tinyintent helper' with no subcommand
        from .helper_cli import main as helper_main
        return helper_main([])  # Show helper help
    elif args.command == 'interactive':
        # Interactive mode
        from .interactive import run_interactive
        return run_interactive()
    elif args.command in ['serve', 'start']:
        # Server mode
        start_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            quiet=args.quiet
        )
    else:
        # Default to interactive
        from .interactive import run_interactive
        return run_interactive()

if __name__ == '__main__':
    main()