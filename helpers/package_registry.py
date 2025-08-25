"""
TinyIntent Multi-Source Package Registry

Manages helpers from multiple sources: local packages, official registry,
community packages, and direct Git installations.
"""

import os
import json
import yaml
import shutil
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

class PackageSource(Enum):
    LOCAL = "local"
    LEGACY = "legacy"  # Current registry.yaml format
    OFFICIAL = "official"
    COMMUNITY = "community" 
    GIT = "git"

class InstallStatus(Enum):
    SUCCESS = "success"
    ALREADY_INSTALLED = "already_installed"
    VALIDATION_FAILED = "validation_failed"
    DOWNLOAD_FAILED = "download_failed"
    DEPENDENCY_FAILED = "dependency_failed"

@dataclass
class HelperPackage:
    """Represents a helper package from any source."""
    name: str
    version: str
    description: str
    source: PackageSource
    package_dir: Path
    metadata: Dict[str, Any]
    
    # TinyIntent-specific fields
    category: str = "unknown"
    risk_level: str = "medium"
    capabilities: List[str] = None
    can_execute: bool = False
    requires_approval: bool = True
    
    # Package management
    installed: bool = False
    enabled: bool = True
    install_date: Optional[str] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []
    
    @property
    def package_id(self) -> str:
        """Unique identifier for this package."""
        return f"{self.name}@{self.version}"
    
    @property
    def helper_yaml_path(self) -> Path:
        """Path to helper.yaml file."""
        return self.package_dir / "helper.yaml"
    
    @property
    def package_json_path(self) -> Path:
        """Path to package.json file.""" 
        return self.package_dir / "package.json"
    
    def is_compatible(self, tinyintent_version: str = "2.0.0") -> bool:
        """Check if package is compatible with TinyIntent version."""
        supported_versions = self.metadata.get("tinyintent", {}).get("supported_versions", [])
        if not supported_versions:
            return True  # Assume compatible if not specified
        
        # Simple version comparison (can be enhanced)
        for version_spec in supported_versions:
            if version_spec.startswith(">="):
                min_version = version_spec[2:]
                # Basic semver comparison
                return tinyintent_version >= min_version
        return True

@dataclass
class InstallResult:
    """Result of package installation."""
    status: InstallStatus
    package: Optional[HelperPackage] = None
    error: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

class PackageSourceInterface:
    """Interface for package sources."""
    
    def discover_packages(self) -> List[HelperPackage]:
        """Discover available packages from this source."""
        raise NotImplementedError
    
    def install_package(self, package_spec: str, target_dir: Path) -> InstallResult:
        """Install a package from this source."""
        raise NotImplementedError
    
    def search_packages(self, query: str) -> List[HelperPackage]:
        """Search for packages matching query."""
        raise NotImplementedError

class LegacyRegistrySource(PackageSourceInterface):
    """Source for existing registry.yaml helpers."""
    
    def __init__(self, helpers_dir: Path):
        self.helpers_dir = helpers_dir
        self.registry_file = helpers_dir / "registry.yaml"
    
    def discover_packages(self) -> List[HelperPackage]:
        """Convert legacy registry entries to packages."""
        packages = []
        
        if not self.registry_file.exists():
            return packages
        
        try:
            with open(self.registry_file, 'r') as f:
                registry_data = yaml.safe_load(f)
            
            helpers_data = registry_data.get("helpers", {})
            
            for helper_id, helper_info in helpers_data.items():
                try:
                    package = self._convert_legacy_helper(helper_id, helper_info)
                    if package:
                        packages.append(package)
                except Exception as e:
                    print(f"Warning: Failed to convert legacy helper {helper_id}: {e}")
            
        except Exception as e:
            print(f"Error loading legacy registry: {e}")
        
        return packages
    
    def _convert_legacy_helper(self, helper_id: str, helper_info: Dict[str, Any]) -> Optional[HelperPackage]:
        """Convert legacy registry entry to HelperPackage."""
        helper_dir = self.helpers_dir / helper_id
        
        if not helper_dir.exists():
            return None
        
        # Create package metadata from registry info
        metadata = {
            "name": helper_id,
            "version": helper_info.get("version", "1.0.0"),
            "description": helper_info.get("description", ""),
            "author": helper_info.get("maintainer", "Unknown"),
            "tinyintent": {
                "spec_version": "legacy",
                "category": helper_info.get("category", "unknown"),
                "risk_level": helper_info.get("risk_level", "medium"),
                "capabilities": helper_info.get("capabilities", []),
                "can_execute": helper_info.get("can_execute", False),
                "requires_approval": helper_info.get("requires_approval", True),
                "lifecycle": helper_info.get("lifecycle", {"state": "trusted"})
            }
        }
        
        return HelperPackage(
            name=helper_id,
            version=helper_info.get("version", "1.0.0"),
            description=helper_info.get("description", ""),
            source=PackageSource.LEGACY,
            package_dir=helper_dir,
            metadata=metadata,
            category=helper_info.get("category", "unknown"),
            risk_level=helper_info.get("risk_level", "medium"),
            capabilities=helper_info.get("capabilities", []),
            can_execute=helper_info.get("can_execute", False),
            requires_approval=helper_info.get("requires_approval", True),
            installed=True,
            enabled=helper_info.get("enabled", True)
        )
    
    def install_package(self, package_spec: str, target_dir: Path) -> InstallResult:
        """Legacy helpers are already installed."""
        return InstallResult(
            status=InstallStatus.ALREADY_INSTALLED,
            error="Legacy helpers cannot be installed/reinstalled"
        )
    
    def search_packages(self, query: str) -> List[HelperPackage]:
        """Search legacy helpers."""
        all_packages = self.discover_packages()
        query_lower = query.lower()
        
        return [
            pkg for pkg in all_packages
            if query_lower in pkg.name.lower() or query_lower in pkg.description.lower()
        ]

class LocalPackageSource(PackageSourceInterface):
    """Source for local package directories."""
    
    def __init__(self, packages_dir: Union[str, Path]):
        self.packages_dir = Path(packages_dir).expanduser()
        self.packages_dir.mkdir(parents=True, exist_ok=True)
    
    def discover_packages(self) -> List[HelperPackage]:
        """Discover locally installed packages."""
        packages = []
        
        for package_dir in self.packages_dir.iterdir():
            if package_dir.is_dir():
                try:
                    package = self._load_local_package(package_dir)
                    if package:
                        packages.append(package)
                except Exception as e:
                    print(f"Warning: Failed to load local package {package_dir.name}: {e}")
        
        return packages
    
    def _load_local_package(self, package_dir: Path) -> Optional[HelperPackage]:
        """Load a local package from directory."""
        package_json = package_dir / "package.json"
        helper_yaml = package_dir / "helper.yaml"
        
        if not package_json.exists() or not helper_yaml.exists():
            return None
        
        try:
            # Load package.json
            with open(package_json, 'r') as f:
                metadata = json.load(f)
            
            # Extract TinyIntent-specific metadata
            tinyintent_meta = metadata.get("tinyintent", {})
            
            return HelperPackage(
                name=metadata["name"],
                version=metadata["version"],
                description=metadata.get("description", ""),
                source=PackageSource.LOCAL,
                package_dir=package_dir,
                metadata=metadata,
                category=tinyintent_meta.get("category", "unknown"),
                risk_level=tinyintent_meta.get("risk_level", "medium"),
                capabilities=tinyintent_meta.get("capabilities", []),
                can_execute=tinyintent_meta.get("can_execute", False),
                requires_approval=tinyintent_meta.get("requires_approval", True),
                installed=True,
                enabled=True,
                install_date=datetime.now().isoformat()
            )
        
        except Exception as e:
            print(f"Error loading package {package_dir.name}: {e}")
            return None
    
    def install_package(self, package_spec: str, target_dir: Path) -> InstallResult:
        """Install package from local source (copy/symlink)."""
        source_path = Path(package_spec).expanduser()
        
        if not source_path.exists():
            return InstallResult(
                status=InstallStatus.DOWNLOAD_FAILED,
                error=f"Source path does not exist: {source_path}"
            )
        
        if not source_path.is_dir():
            return InstallResult(
                status=InstallStatus.VALIDATION_FAILED,
                error=f"Source must be a directory: {source_path}"
            )
        
        # Load package metadata to get name
        package_json = source_path / "package.json"
        if not package_json.exists():
            return InstallResult(
                status=InstallStatus.VALIDATION_FAILED,
                error="Missing package.json file"
            )
        
        try:
            with open(package_json, 'r') as f:
                metadata = json.load(f)
            
            package_name = metadata["name"]
            target_path = target_dir / package_name
            
            # Check if already installed
            if target_path.exists():
                return InstallResult(
                    status=InstallStatus.ALREADY_INSTALLED,
                    error=f"Package {package_name} is already installed"
                )
            
            # Copy package to target directory
            shutil.copytree(source_path, target_path)
            
            # Load the installed package
            package = self._load_local_package(target_path)
            
            return InstallResult(
                status=InstallStatus.SUCCESS,
                package=package
            )
            
        except Exception as e:
            return InstallResult(
                status=InstallStatus.VALIDATION_FAILED,
                error=f"Failed to install package: {e}"
            )
    
    def search_packages(self, query: str) -> List[HelperPackage]:
        """Search local packages."""
        all_packages = self.discover_packages()
        query_lower = query.lower()
        
        return [
            pkg for pkg in all_packages
            if query_lower in pkg.name.lower() or 
               query_lower in pkg.description.lower() or
               query_lower in pkg.category.lower()
        ]

class OfficialRegistrySource(PackageSourceInterface):
    """Source for official TinyIntent package registry."""
    
    def __init__(self, registry_url: str = "https://registry.tinyintent.ai"):
        self.registry_url = registry_url
        self.cache_dir = Path.home() / ".tinyintent" / "cache" / "official"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def discover_packages(self) -> List[HelperPackage]:
        """Discover packages from official registry."""
        # TODO: Implement registry API calls
        return []
    
    def install_package(self, package_spec: str, target_dir: Path) -> InstallResult:
        """Install package from official registry."""
        # TODO: Implement official registry installation
        return InstallResult(
            status=InstallStatus.DOWNLOAD_FAILED,
            error="Official registry not yet implemented"
        )
    
    def search_packages(self, query: str) -> List[HelperPackage]:
        """Search official registry."""
        # TODO: Implement registry search API
        return []

class MultiSourceRegistry:
    """Main registry that manages multiple package sources."""
    
    def __init__(self, helpers_dir: Optional[Path] = None):
        if helpers_dir is None:
            project_root = Path(__file__).parent.parent
            helpers_dir = project_root / "helpers"
        
        self.helpers_dir = Path(helpers_dir)
        self.packages_dir = Path.home() / ".tinyintent" / "packages"
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize sources
        self.sources = {
            PackageSource.LEGACY: LegacyRegistrySource(self.helpers_dir),
            PackageSource.LOCAL: LocalPackageSource(self.packages_dir),
            PackageSource.OFFICIAL: OfficialRegistrySource()
        }
        
        self._package_cache: Dict[str, HelperPackage] = {}
        self._last_refresh = None
    
    def refresh_packages(self, force: bool = False) -> None:
        """Refresh package cache from all sources."""
        if not force and self._last_refresh:
            # Cache for 5 minutes
            age = (datetime.now() - self._last_refresh).total_seconds()
            if age < 300:
                return
        
        self._package_cache.clear()
        
        for source_type, source in self.sources.items():
            try:
                packages = source.discover_packages()
                for package in packages:
                    # Use package@version as key to handle multiple versions
                    key = f"{package.name}@{package.version}"
                    self._package_cache[key] = package
            except Exception as e:
                print(f"Warning: Failed to refresh {source_type.value} packages: {e}")
        
        self._last_refresh = datetime.now()
    
    def get_installed_packages(self) -> List[HelperPackage]:
        """Get all installed packages."""
        self.refresh_packages()
        return [pkg for pkg in self._package_cache.values() if pkg.installed]
    
    def get_available_packages(self) -> List[HelperPackage]:
        """Get all available packages (installed and available for install)."""
        self.refresh_packages()
        return list(self._package_cache.values())
    
    def search_packages(self, query: str, category: Optional[str] = None) -> List[HelperPackage]:
        """Search packages across all sources."""
        results = []
        
        for source in self.sources.values():
            try:
                source_results = source.search_packages(query)
                results.extend(source_results)
            except Exception as e:
                print(f"Warning: Search failed for source: {e}")
        
        # Filter by category if specified
        if category:
            results = [pkg for pkg in results if pkg.category == category]
        
        # Remove duplicates (prefer local/installed over remote)
        seen_names = set()
        filtered_results = []
        
        # Sort by priority: LOCAL > LEGACY > OFFICIAL > COMMUNITY > GIT
        priority_order = [PackageSource.LOCAL, PackageSource.LEGACY, 
                         PackageSource.OFFICIAL, PackageSource.COMMUNITY, PackageSource.GIT]
        
        results.sort(key=lambda pkg: priority_order.index(pkg.source))
        
        for pkg in results:
            if pkg.name not in seen_names:
                filtered_results.append(pkg)
                seen_names.add(pkg.name)
        
        return filtered_results
    
    def install_package(self, package_spec: str) -> InstallResult:
        """
        Install a package from any source.
        
        Supports:
        - package_name (search all sources)
        - package_name@version (specific version)
        - ./local/path (local directory)
        - github:user/repo (Git repository)
        """
        # Determine source and normalize spec
        if package_spec.startswith("./") or package_spec.startswith("/"):
            # Local directory
            source = self.sources[PackageSource.LOCAL]
            return source.install_package(package_spec, self.packages_dir)
        
        elif package_spec.startswith("github:"):
            # GitHub repository
            return InstallResult(
                status=InstallStatus.DOWNLOAD_FAILED,
                error="GitHub installation not yet implemented"
            )
        
        else:
            # Package name - search all sources
            return self._install_from_search(package_spec)
    
    def _install_from_search(self, package_spec: str) -> InstallResult:
        """Install package by searching all sources."""
        # Parse package@version format
        if "@" in package_spec:
            name, version = package_spec.split("@", 1)
        else:
            name, version = package_spec, None
        
        # Search for package
        candidates = self.search_packages(name)
        
        if not candidates:
            return InstallResult(
                status=InstallStatus.DOWNLOAD_FAILED,
                error=f"Package '{name}' not found in any source"
            )
        
        # Find matching version or latest
        target_package = None
        if version:
            target_package = next((pkg for pkg in candidates if pkg.version == version), None)
            if not target_package:
                return InstallResult(
                    status=InstallStatus.DOWNLOAD_FAILED,
                    error=f"Version {version} not found for package '{name}'"
                )
        else:
            # Get latest version (simple string comparison for now)
            target_package = max(candidates, key=lambda pkg: pkg.version)
        
        # Check if already installed
        if target_package.installed:
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                package=target_package
            )
        
        # Install from appropriate source
        source = self.sources[target_package.source]
        return source.install_package(package_spec, self.packages_dir)
    
    def uninstall_package(self, package_name: str) -> bool:
        """Uninstall a package."""
        self.refresh_packages()
        
        # Find installed package
        installed_pkg = None
        for pkg in self._package_cache.values():
            if pkg.name == package_name and pkg.installed:
                installed_pkg = pkg
                break
        
        if not installed_pkg:
            return False
        
        if installed_pkg.source == PackageSource.LEGACY:
            # Cannot uninstall legacy helpers
            return False
        
        try:
            # Remove package directory
            if installed_pkg.package_dir.exists():
                shutil.rmtree(installed_pkg.package_dir)
            
            # Remove from cache
            cache_key = f"{installed_pkg.name}@{installed_pkg.version}"
            if cache_key in self._package_cache:
                del self._package_cache[cache_key]
            
            return True
            
        except Exception as e:
            print(f"Failed to uninstall package {package_name}: {e}")
            return False
    
    def get_package_info(self, package_name: str) -> Optional[HelperPackage]:
        """Get detailed information about a package."""
        self.refresh_packages()
        
        # Find latest version of the package
        candidates = [pkg for pkg in self._package_cache.values() if pkg.name == package_name]
        if not candidates:
            return None
        
        # Return latest version
        return max(candidates, key=lambda pkg: pkg.version)
    
    def list_categories(self) -> List[str]:
        """List all available categories."""
        self.refresh_packages()
        categories = set()
        for pkg in self._package_cache.values():
            categories.add(pkg.category)
        return sorted(categories)
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get status of all package sources."""
        self.refresh_packages()
        
        status = {
            "total_packages": len(self._package_cache),
            "installed_packages": len([pkg for pkg in self._package_cache.values() if pkg.installed]),
            "sources": {},
            "categories": {}
        }
        
        # Count by source
        for source_type in PackageSource:
            source_packages = [pkg for pkg in self._package_cache.values() if pkg.source == source_type]
            status["sources"][source_type.value] = {
                "total": len(source_packages),
                "installed": len([pkg for pkg in source_packages if pkg.installed])
            }
        
        # Count by category
        for pkg in self._package_cache.values():
            if pkg.category not in status["categories"]:
                status["categories"][pkg.category] = {"total": 0, "installed": 0}
            status["categories"][pkg.category]["total"] += 1
            if pkg.installed:
                status["categories"][pkg.category]["installed"] += 1
        
        return status

# Global registry instance
_global_registry = None

def get_package_registry() -> MultiSourceRegistry:
    """Get the global package registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = MultiSourceRegistry()
    return _global_registry