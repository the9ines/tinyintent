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

def setup_environment():
    """Setup default environment variables if not set."""
    defaults = {
        'TINYINTENT_SECRET': 'tinyintent-default-secret-change-in-production-32chars',
        'TINYINTENT_ALLOW_DEV_LOCAL': '1',
        'TINYINTENT_EXECUTION_ENABLED': '1',
        'TINYINTENT_BIND': '0.0.0.0',
        'TINYINTENT_PORT': '8787',
        'TINYINTENT_LOG_LEVEL': 'info',
        'SHORTCUT_TOKEN': 'tinyintent-shortcut-token-123',
        'SHORTCUT_MAX_LEN': '800',
        'NODE_ENV': 'development'
    }
    
    for key, value in defaults.items():
        if key not in os.environ:
            os.environ[key] = value

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

def start_server(host: str = None, port: int = None, reload: bool = False):
    """Start the TinyIntent bridge server."""
    setup_environment()
    
    # Use environment or provided values
    server_host = host or os.environ.get('TINYINTENT_BIND', '0.0.0.0')
    server_port = port or int(os.environ.get('TINYINTENT_PORT', '8787'))
    log_level = os.environ.get('TINYINTENT_LOG_LEVEL', 'info')
    
    # Show startup info
    panel = Panel.fit(
        f"🚀 Starting TinyIntent Bridge\n\n"
        f"📡 Server: http://{server_host}:{server_port}\n"
        f"📱 Shortcut: /shortcut/route\n"
        f"📋 API Docs: /docs\n"
        f"🏥 Health: /health",
        title="TinyIntent v2.0.0",
        border_style="green"
    )
    console.print(panel)
    
    try:
        # Try full bridge app first
        sys.path.insert(0, str(Path(__file__).parent.parent / "bridge"))
        from tinyrpc import app
        console.print("✅ Starting full TinyIntent Bridge...", style="green")
        
        uvicorn.run(
            app,
            host=server_host,
            port=server_port,
            log_level=log_level,
            reload=reload
        )
    except ImportError as e:
        # Fallback to simple server if full app not available
        console.print(f"⚠️  Full TinyIntent app not available ({e}), starting simple server...", style="yellow")
        from .simple_server import create_simple_app
        app = create_simple_app()
        
        uvicorn.run(
            app,
            host=server_host,
            port=server_port,
            log_level=log_level,
            reload=reload
        )

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="TinyIntent - Voice-Activated AI Assistant Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tinyintent                    # Start with defaults
  tinyintent --port 9000        # Start on custom port  
  tinyintent --host 127.0.0.1   # Start on localhost only
  tinyintent --reload           # Start with auto-reload for development
  tinyintent status             # Show system status
        """
    )
    
    parser.add_argument(
        'command', 
        nargs='?', 
        default='start',
        choices=['start', 'status', 'help'],
        help='Command to run (default: start)'
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
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    if args.command == 'status':
        show_status()
    elif args.command == 'help':
        parser.print_help()
    else:  # start
        start_server(
            host=args.host,
            port=args.port,
            reload=args.reload
        )

if __name__ == '__main__':
    main()