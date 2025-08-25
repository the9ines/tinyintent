"""
TinyIntent Helper Management CLI

Commands for managing modular helper packages.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich import box

# Add helpers to path for imports
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

from package_registry import get_package_registry, PackageSource, InstallStatus

console = Console()

class HelperCLI:
    """Command-line interface for helper package management."""
    
    def __init__(self):
        self.registry = get_package_registry()
    
    def search(self, query: str, category: str = None, show_details: bool = False) -> None:
        """Search for helper packages."""
        console.print(f"🔍 Searching for helpers matching: [bold cyan]{query}[/bold cyan]")
        
        if category:
            console.print(f"   Filtering by category: [yellow]{category}[/yellow]")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("Searching packages...", total=None)
            results = self.registry.search_packages(query, category)
            progress.remove_task(task)
        
        if not results:
            console.print("[red]❌ No helpers found matching your search.[/red]")
            return
        
        console.print(f"[green]✅ Found {len(results)} helper(s):[/green]")
        
        if show_details:
            self._show_detailed_results(results)
        else:
            self._show_simple_results(results)
    
    def _show_simple_results(self, packages: List) -> None:
        """Show simple table of search results."""
        table = Table(box=box.ROUNDED)
        table.add_column("Name", style="cyan", min_width=15)
        table.add_column("Version", style="yellow", min_width=8)
        table.add_column("Category", style="green", min_width=10)
        table.add_column("Risk", style="orange1", min_width=6)
        table.add_column("Source", style="blue", min_width=8)
        table.add_column("Status", style="magenta", min_width=10)
        table.add_column("Description", min_width=30)
        
        for pkg in packages:
            status = "✅ Installed" if pkg.installed else "📥 Available"
            risk_color = {
                "low": "[green]Low[/green]",
                "medium": "[yellow]Medium[/yellow]", 
                "high": "[red]High[/red]"
            }.get(pkg.risk_level, pkg.risk_level)
            
            table.add_row(
                pkg.name,
                pkg.version,
                pkg.category.title(),
                risk_color,
                pkg.source.value.title(),
                status,
                pkg.description[:50] + "..." if len(pkg.description) > 50 else pkg.description
            )
        
        console.print(table)
    
    def _show_detailed_results(self, packages: List) -> None:
        """Show detailed information for each package."""
        for i, pkg in enumerate(packages):
            if i > 0:
                console.print()
            
            status_icon = "✅" if pkg.installed else "📥"
            console.print(f"{status_icon} [bold cyan]{pkg.name}[/bold cyan] v{pkg.version}")
            console.print(f"   [dim]Description:[/dim] {pkg.description}")
            console.print(f"   [dim]Category:[/dim] {pkg.category.title()}")
            console.print(f"   [dim]Risk Level:[/dim] {pkg.risk_level.title()}")
            console.print(f"   [dim]Source:[/dim] {pkg.source.value.title()}")
            console.print(f"   [dim]Capabilities:[/dim] {', '.join(pkg.capabilities) or 'None'}")
            
            if pkg.metadata.get("author"):
                console.print(f"   [dim]Author:[/dim] {pkg.metadata['author']}")
    
    def list(self, category: str = None, show_all: bool = False) -> None:
        """List installed or all available helper packages."""
        console.print("📦 TinyIntent Helper Packages")
        
        if show_all:
            packages = self.registry.get_available_packages()
            console.print(f"[dim]Showing all {len(packages)} available packages[/dim]")
        else:
            packages = self.registry.get_installed_packages()
            console.print(f"[dim]Showing {len(packages)} installed packages[/dim]")
        
        if category:
            packages = [pkg for pkg in packages if pkg.category == category]
            console.print(f"[dim]Filtered by category: {category}[/dim]")
        
        if not packages:
            if show_all:
                console.print("[yellow]⚠️ No packages available.[/yellow]")
            else:
                console.print("[yellow]⚠️ No packages installed. Use 'tinyintent helper search' to find packages.[/yellow]")
            return
        
        # Group by category
        by_category = {}
        for pkg in packages:
            if pkg.category not in by_category:
                by_category[pkg.category] = []
            by_category[pkg.category].append(pkg)
        
        for category, cat_packages in sorted(by_category.items()):
            console.print(f"\n[bold green]📁 {category.title()}[/bold green]")
            
            for pkg in sorted(cat_packages, key=lambda p: p.name):
                status_icon = "✅" if pkg.installed else "📥"
                risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(pkg.risk_level, "⚪")
                
                console.print(f"  {status_icon} [cyan]{pkg.name}[/cyan] v{pkg.version} {risk_icon}")
                console.print(f"    [dim]{pkg.description}[/dim]")
                
                if pkg.source == PackageSource.LEGACY:
                    console.print(f"    [dim]Source: Legacy (built-in)[/dim]")
                else:
                    console.print(f"    [dim]Source: {pkg.source.value.title()}[/dim]")
    
    def install(self, package_spec: str, force: bool = False) -> None:
        """Install a helper package."""
        console.print(f"📥 Installing helper package: [bold cyan]{package_spec}[/bold cyan]")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("Installing package...", total=None)
            result = self.registry.install_package(package_spec)
            progress.remove_task(task)
        
        if result.status == InstallStatus.SUCCESS:
            console.print(f"[green]✅ Successfully installed {result.package.name} v{result.package.version}[/green]")
            
            # Show package info
            self._show_package_summary(result.package)
            
            # Show warnings if any
            if result.warnings:
                console.print("\n[yellow]⚠️ Warnings:[/yellow]")
                for warning in result.warnings:
                    console.print(f"  • {warning}")
        
        elif result.status == InstallStatus.ALREADY_INSTALLED:
            console.print(f"[yellow]⚠️ Package is already installed: {package_spec}[/yellow]")
        
        elif result.status == InstallStatus.VALIDATION_FAILED:
            console.print(f"[red]❌ Installation failed - Validation error:[/red]")
            console.print(f"  {result.error}")
        
        elif result.status == InstallStatus.DOWNLOAD_FAILED:
            console.print(f"[red]❌ Installation failed - Download error:[/red]")
            console.print(f"  {result.error}")
        
        else:
            console.print(f"[red]❌ Installation failed:[/red]")
            console.print(f"  {result.error or 'Unknown error'}")
    
    def _show_package_summary(self, package) -> None:
        """Show summary of installed package."""
        console.print(f"\n[bold]Package Summary:[/bold]")
        console.print(f"  Name: {package.name}")
        console.print(f"  Version: {package.version}")
        console.print(f"  Description: {package.description}")
        console.print(f"  Category: {package.category.title()}")
        console.print(f"  Risk Level: {package.risk_level.title()}")
        console.print(f"  Capabilities: {', '.join(package.capabilities) or 'None'}")
        console.print(f"  Can Execute: {'✅ Yes' if package.can_execute else '❌ No (preview only)'}")
        console.print(f"  Requires Approval: {'✅ Yes' if package.requires_approval else '❌ No'}")
    
    def remove(self, package_name: str, force: bool = False) -> None:
        """Remove an installed helper package."""
        # Check if package exists and is installed
        package_info = self.registry.get_package_info(package_name)
        
        if not package_info:
            console.print(f"[red]❌ Package '{package_name}' not found.[/red]")
            return
        
        if not package_info.installed:
            console.print(f"[yellow]⚠️ Package '{package_name}' is not installed.[/yellow]")
            return
        
        if package_info.source == PackageSource.LEGACY:
            console.print(f"[red]❌ Cannot remove built-in helper '{package_name}'.[/red]")
            console.print("   Built-in helpers are part of the core TinyIntent installation.")
            return
        
        # Confirm removal unless forced
        if not force:
            if not Confirm.ask(f"Are you sure you want to remove {package_name}?"):
                console.print("Cancelled.")
                return
        
        console.print(f"🗑️ Removing helper package: [bold cyan]{package_name}[/bold cyan]")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("Removing package...", total=None)
            success = self.registry.uninstall_package(package_name)
            progress.remove_task(task)
        
        if success:
            console.print(f"[green]✅ Successfully removed {package_name}[/green]")
        else:
            console.print(f"[red]❌ Failed to remove {package_name}[/red]")
    
    def info(self, package_name: str) -> None:
        """Show detailed information about a package."""
        package_info = self.registry.get_package_info(package_name)
        
        if not package_info:
            console.print(f"[red]❌ Package '{package_name}' not found.[/red]")
            return
        
        # Header
        status_icon = "✅" if package_info.installed else "📥"
        console.print(f"{status_icon} [bold cyan]{package_info.name}[/bold cyan] v{package_info.version}")
        
        # Basic info
        table = Table(show_header=False, box=box.MINIMAL_DOUBLE_HEAD, pad_edge=False)
        table.add_column("Property", style="dim", min_width=15)
        table.add_column("Value", min_width=30)
        
        table.add_row("Description", package_info.description)
        table.add_row("Category", package_info.category.title())
        table.add_row("Risk Level", package_info.risk_level.title())
        table.add_row("Source", package_info.source.value.title())
        table.add_row("Status", "✅ Installed" if package_info.installed else "📥 Available")
        table.add_row("Can Execute", "✅ Yes" if package_info.can_execute else "❌ Preview only")
        table.add_row("Requires Approval", "✅ Yes" if package_info.requires_approval else "❌ No")
        table.add_row("Capabilities", ", ".join(package_info.capabilities) or "None")
        
        # Metadata from package.json
        if package_info.metadata.get("author"):
            table.add_row("Author", package_info.metadata["author"])
        
        if package_info.metadata.get("license"):
            table.add_row("License", package_info.metadata["license"])
        
        if package_info.metadata.get("homepage"):
            table.add_row("Homepage", package_info.metadata["homepage"])
        
        if package_info.install_date:
            table.add_row("Installed", package_info.install_date.split("T")[0])
        
        console.print(table)
        
        # Show file structure
        if package_info.installed and package_info.package_dir.exists():
            console.print(f"\n[bold]Package Files:[/bold]")
            self._show_package_files(package_info.package_dir)
    
    def _show_package_files(self, package_dir: Path, max_depth: int = 2) -> None:
        """Show package file structure."""
        def show_tree(path: Path, prefix: str = "", depth: int = 0):
            if depth >= max_depth:
                return
            
            items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                
                if item.is_dir():
                    icon = "📁"
                    connector = "└── " if is_last else "├── "
                    console.print(f"{prefix}{connector}{icon} [blue]{item.name}/[/blue]")
                    
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    show_tree(item, next_prefix, depth + 1)
                else:
                    icon = self._get_file_icon(item.suffix)
                    connector = "└── " if is_last else "├── "
                    console.print(f"{prefix}{connector}{icon} {item.name}")
        
        show_tree(package_dir)
    
    def _get_file_icon(self, suffix: str) -> str:
        """Get icon for file type."""
        icons = {
            ".py": "🐍",
            ".js": "🟨",
            ".json": "📋",
            ".yaml": "📄",
            ".yml": "📄",
            ".md": "📝",
            ".txt": "📄",
            ".sh": "⚡"
        }
        return icons.get(suffix.lower(), "📄")
    
    def status(self) -> None:
        """Show registry status and statistics."""
        console.print("📊 [bold]TinyIntent Helper Registry Status[/bold]")
        
        status = self.registry.get_registry_status()
        
        # Overview
        console.print(f"\n[bold]Overview:[/bold]")
        console.print(f"  Total Packages: {status['total_packages']}")
        console.print(f"  Installed: {status['installed_packages']}")
        console.print(f"  Available: {status['total_packages'] - status['installed_packages']}")
        
        # Sources
        console.print(f"\n[bold]Sources:[/bold]")
        for source_name, source_stats in status["sources"].items():
            if source_stats["total"] > 0:
                console.print(f"  {source_name.title()}: {source_stats['installed']}/{source_stats['total']} installed")
        
        # Categories
        console.print(f"\n[bold]Categories:[/bold]")
        for category, cat_stats in sorted(status["categories"].items()):
            icon = {"information": "ℹ️", "trading": "💰", "monitoring": "📈", "infrastructure": "⚙️"}.get(category, "📦")
            console.print(f"  {icon} {category.title()}: {cat_stats['installed']}/{cat_stats['total']} installed")
    
    def categories(self) -> None:
        """List all available categories."""
        categories = self.registry.list_categories()
        
        console.print("📁 [bold]Available Categories:[/bold]")
        
        for category in categories:
            # Count packages in this category
            packages = self.registry.search_packages("", category)
            installed_count = len([p for p in packages if p.installed])
            total_count = len(packages)
            
            icon = {"information": "ℹ️", "trading": "💰", "monitoring": "📈", "infrastructure": "⚙️"}.get(category, "📦")
            console.print(f"  {icon} [cyan]{category.title()}[/cyan] ({installed_count}/{total_count} installed)")
    
    def generate(self, template: str = None, from_description: str = None) -> None:
        """Generate a new helper package using AI assistance."""
        from .helper_generator import HelperGenerator
        
        console.print("🎯 [bold cyan]TinyIntent Helper Generator[/bold cyan]")
        
        if from_description:
            console.print(f"Generating helper from description: [italic]{from_description}[/italic]")
            # TODO: Implement description-based generation
            console.print("[yellow]⚠️ Description-based generation coming soon![/yellow]")
            console.print("For now, use interactive mode.")
            return
        
        if template:
            console.print(f"Using template: [cyan]{template}[/cyan]")
            # TODO: Implement template-based generation
            console.print("[yellow]⚠️ Template-based generation coming soon![/yellow]")
            console.print("For now, use interactive mode.")
            return
        
        # Interactive generation
        generator = HelperGenerator()
        package_dir = generator.interactive_generate()
        
        if package_dir:
            # Auto-install the generated helper
            if Confirm.ask("Install the generated helper now?", default=True):
                self.install(package_dir, force=False)

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for helper CLI."""
    parser = argparse.ArgumentParser(
        prog="tinyintent helper",
        description="Manage TinyIntent helper packages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tinyintent helper search weather          # Search for weather-related helpers
  tinyintent helper install weather_helper # Install a specific helper
  tinyintent helper list                    # List installed helpers
  tinyintent helper info weather_helper     # Get detailed info about a helper
  tinyintent helper remove old_helper       # Remove an installed helper
  tinyintent helper status                  # Show registry statistics
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for helper packages")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--category", help="Filter by category")
    search_parser.add_argument("--details", action="store_true", help="Show detailed results")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List helper packages")
    list_parser.add_argument("--category", help="Filter by category") 
    list_parser.add_argument("--all", action="store_true", help="Show all available packages, not just installed")
    
    # Install command
    install_parser = subparsers.add_parser("install", help="Install a helper package")
    install_parser.add_argument("package", help="Package name, local path, or github:user/repo")
    install_parser.add_argument("--force", action="store_true", help="Force installation")
    
    # Remove command
    remove_parser = subparsers.add_parser("remove", aliases=["uninstall"], help="Remove a helper package")
    remove_parser.add_argument("package", help="Package name to remove")
    remove_parser.add_argument("--force", action="store_true", help="Skip confirmation")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show detailed package information")
    info_parser.add_argument("package", help="Package name")
    
    # Status command
    subparsers.add_parser("status", help="Show registry status")
    
    # Categories command
    subparsers.add_parser("categories", help="List all available categories")
    
    # Generate command
    generate_parser = subparsers.add_parser("generate", help="Generate a new helper package using AI")
    generate_parser.add_argument("--template", help="Use a specific template (python, node, api, etc.)")
    generate_parser.add_argument("--from-description", help="Generate from natural language description")
    
    return parser

def main(args: List[str] = None) -> int:
    """Main entry point for helper CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if not parsed_args.command:
        parser.print_help()
        return 1
    
    cli = HelperCLI()
    
    try:
        if parsed_args.command == "search":
            cli.search(parsed_args.query, parsed_args.category, parsed_args.details)
        
        elif parsed_args.command == "list":
            cli.list(parsed_args.category, parsed_args.all)
        
        elif parsed_args.command == "install":
            cli.install(parsed_args.package, parsed_args.force)
        
        elif parsed_args.command in ["remove", "uninstall"]:
            cli.remove(parsed_args.package, parsed_args.force)
        
        elif parsed_args.command == "info":
            cli.info(parsed_args.package)
        
        elif parsed_args.command == "status":
            cli.status()
        
        elif parsed_args.command == "categories":
            cli.categories()
        
        elif parsed_args.command == "generate":
            cli.generate(parsed_args.template, parsed_args.from_description)
        
        else:
            console.print(f"[red]Unknown command: {parsed_args.command}[/red]")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if "--debug" in (args or []):
            raise
        return 1

if __name__ == "__main__":
    sys.exit(main())