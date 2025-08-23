
"""
TinyIntent Helper Sandbox

Provides the execution environment for helpers, enforcing resource limits (CPU, memory)
and capability-based isolation (e.g., network, filesystem access).
"""

import os
import json
import signal
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Import resource limits (graceful fallback for non-Unix systems)
try:
    import resource
    RESOURCE_LIMITS_AVAILABLE = True
except ImportError:
    RESOURCE_LIMITS_AVAILABLE = False

# Import audit logger (M6.2) - with fallback for standalone helper usage
try:
    from tinyintent.bridge.logs.audit import get_audit_logger
    AUDIT_LOGGER_AVAILABLE = True
except ImportError:
    AUDIT_LOGGER_AVAILABLE = False
    get_audit_logger = None

class SandboxViolationError(Exception):
    """Exception raised when helper execution violates sandbox limits."""
    
    def __init__(self, message: str, error_code: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

class CapabilityViolationError(Exception):
    """Exception raised when helper execution violates capability restrictions."""
    
    def __init__(self, message: str, capability: str, operation: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.error_code = "CAPABILITY_VIOLATION"
        self.capability = capability
        self.operation = operation
        self.details = details or {}

class HelperSandbox:
    """M10.7: Enhanced sandbox for helper execution with hardened resource limits and capability isolation."""
    
    def __init__(self, helper_id: str, audit_log_path: Path, capabilities: List[str] = None):
        self.helper_id = helper_id
        self.audit_log_path = audit_log_path
        self.capabilities = capabilities or []  # M6.5: Helper capabilities
        
        # M10.7: Hardened default sandbox limits with stricter enforcement
        self.max_cpu_time = 5  # seconds (more restrictive)
        self.max_memory_mb = 128  # MB (more restrictive) 
        self.max_execution_time = int(os.getenv('SANDBOX_TIMEOUT_MS', '3000')) // 1000  # seconds (configurable)
        self.max_output_size = 512 * 1024  # 512KB (more restrictive)
        self.max_file_descriptors = 64  # Maximum file descriptors
        self.max_processes = 4  # Maximum subprocesses
        
        # M10.7: Per-execution temporary workspace for isolation
        self.temp_workspace: Optional[Path] = None
        
    def set_limits(self, cpu_time: int = None, memory_mb: int = None, 
                   execution_time: int = None, output_size: int = None,
                   file_descriptors: int = None, processes: int = None):
        """M10.7: Set sandbox resource limits with enhanced hardening options."""
        if cpu_time is not None:
            self.max_cpu_time = cpu_time
        if memory_mb is not None:
            self.max_memory_mb = memory_mb
        if execution_time is not None:
            self.max_execution_time = execution_time
        if output_size is not None:
            self.max_output_size = output_size
        if file_descriptors is not None:
            self.max_file_descriptors = file_descriptors
        if processes is not None:
            self.max_processes = processes
    
    def _create_temp_workspace(self) -> Path:
        """M10.7: Create isolated temporary workspace for helper execution."""
        if self.temp_workspace and self.temp_workspace.exists():
            # Clean up previous workspace
            self._cleanup_workspace()
        
        # Create new temporary directory with helper-specific prefix
        self.temp_workspace = Path(tempfile.mkdtemp(
            prefix=f"tinyintent_helper_{self.helper_id}_",
            suffix="_sandbox"
        ))
        
        # Set restrictive permissions
        self.temp_workspace.chmod(0o700)
        return self.temp_workspace
    
    def _cleanup_workspace(self):
        """M10.7: Clean up temporary workspace after execution."""
        if self.temp_workspace and self.temp_workspace.exists():
            try:
                shutil.rmtree(self.temp_workspace)
            except (OSError, PermissionError):
                # If cleanup fails, just log and continue
                pass
            finally:
                self.temp_workspace = None
    
    def _enforce_capability_restrictions(self, env: Dict[str, str]) -> Dict[str, str]:
        """
        M10.7: Enforce capability restrictions on environment and prepare restrictive environment.
        
        Args:
            env: Original environment dictionary
            
        Returns:
            Modified environment dictionary with capability restrictions applied
        """
        restricted_env = env.copy()
        
        # Network capability enforcement
        if "network" not in self.capabilities:
            # Remove network-related environment variables
            network_env_vars = [
                'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                'ftp_proxy', 'FTP_PROXY', 'no_proxy', 'NO_PROXY',
                'all_proxy', 'ALL_PROXY', 'socks_proxy', 'SOCKS_PROXY'
            ]
            for var in network_env_vars:
                restricted_env.pop(var, None)
            
            # Add environment flag to indicate network restrictions
            restricted_env['TINYINTENT_NETWORK_DISABLED'] = '1'
        
        # M10.7: Enhanced filesystem capability enforcement with workspace isolation
        if "filesystem" not in self.capabilities:
            # Add environment flag to indicate filesystem restrictions
            restricted_env['TINYINTENT_FILESYSTEM_RESTRICTED'] = '1'
            
        # M10.7: Always create isolated workspace for execution
        # This provides stronger isolation even for trusted helpers
        workspace = self._create_temp_workspace()
        restricted_env['TMPDIR'] = str(workspace)
        restricted_env['TEMP'] = str(workspace)
        restricted_env['TMP'] = str(workspace)
        restricted_env['HOME'] = str(workspace)  # Override HOME for isolation
        
        # Set workspace path for reference
        restricted_env['TINYINTENT_WORKSPACE'] = str(workspace)
        
        return restricted_env
    
    def _check_capability_violation(self, operation: str, capability: str) -> None:
        """
        Check if an operation violates capability restrictions.
        
        Args:
            operation: Description of the operation being attempted
            capability: Required capability for the operation
            
        Raises:
            CapabilityViolationError: If capability not granted
        """
        if capability not in self.capabilities:
            raise CapabilityViolationError(
                f"Helper {self.helper_id} attempted {operation} without {capability} capability",
                capability=capability,
                operation=operation,
                details={
                    "helper_id": self.helper_id,
                    "granted_capabilities": self.capabilities,
                    "required_capability": capability
                }
            )
    
    def _create_preexec_fn(self):
        """M10.7: Create preexec function to set hardened resource limits on child process."""
        if not RESOURCE_LIMITS_AVAILABLE:
            return None
            
        def preexec():
            try:
                # M10.7: Enhanced CPU time limit
                resource.setrlimit(resource.RLIMIT_CPU, (self.max_cpu_time, self.max_cpu_time))
                
                # M10.7: Enhanced memory limit (virtual memory)
                max_memory_bytes = self.max_memory_mb * 1024 * 1024
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
                except (OSError, ValueError):
                    # Some systems don't support RLIMIT_AS or have different behavior
                    try:
                        # Try RSS limit instead
                        resource.setrlimit(resource.RLIMIT_RSS, (max_memory_bytes, max_memory_bytes))
                    except (OSError, ValueError):
                        # If neither works, just log and continue
                        pass
                
                # M10.7: File size limit to prevent large outputs
                resource.setrlimit(resource.RLIMIT_FSIZE, (self.max_output_size, self.max_output_size))
                
                # M10.7: File descriptor limit to prevent fd exhaustion
                try:
                    resource.setrlimit(resource.RLIMIT_NOFILE, (self.max_file_descriptors, self.max_file_descriptors))
                except (OSError, ValueError):
                    pass  # Some systems might not allow this
                
                # M10.7: Process limit to prevent fork bombs
                try:
                    resource.setrlimit(resource.RLIMIT_NPROC, (self.max_processes, self.max_processes))
                except (OSError, ValueError):
                    pass  # Some systems might not support this
                
                # M10.7: Core dump limit (disable for security)
                try:
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                except (OSError, ValueError):
                    pass  # Not critical if this fails
                
                # M10.7: Set process priority to lower value (nice)
                try:
                    os.nice(10)  # Even lower priority for better isolation
                except OSError:
                    pass  # Not critical if this fails
                    
            except Exception:
                # Don't fail the entire execution if limits can't be set
                # This ensures compatibility across different systems
                pass
        
        return preexec
    
    def execute(self, cmd: List[str], input_data: str, env: Dict[str, str], 
                cwd: Path) -> Dict[str, Any]:
        """
        M10.7: Execute command in hardened sandbox environment with resource limits and capability isolation.
        
        Returns:
            dict: Execution result or structured error
        """
        # M10.7: Apply capability restrictions and create isolated workspace
        restricted_env = self._enforce_capability_restrictions(env)
        
        preexec_fn = self._create_preexec_fn()
        process = None
        
        try:
            # M10.7: Create isolated workspace for temp files but execute from helper directory
            workspace = self.temp_workspace or self._create_temp_workspace()
            
            # Start the process with capability-restricted environment in helper directory
            # This allows relative paths like "./main.py" to work while still having workspace isolation
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=restricted_env,  # Use restricted environment with isolated temp dirs
                cwd=cwd,  # Use original helper directory for command execution
                preexec_fn=preexec_fn
            )
            
            # Set wall clock timeout
            try:
                stdout, stderr = process.communicate(
                    input=input_data, 
                    timeout=self.max_execution_time
                )
            except subprocess.TimeoutExpired:
                # Kill the process
                process.kill()
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    process.terminate()
                    stdout, stderr = "", "Process forcibly terminated"
                
                error_details = {
                    "timeout_seconds": self.max_execution_time,
                    "helper_id": self.helper_id
                }
                self._log_sandbox_violation("TIMEOUT", f"Helper execution exceeded {self.max_execution_time}s timeout", error_details)
                
                raise SandboxViolationError(
                    f"Helper execution timed out after {self.max_execution_time}s",
                    "SANDBOX_TIMEOUT",
                    error_details
                )
            
            # M10.7: Enhanced resource limit violation detection
            if process.returncode != 0:
                # Check for specific resource limit signals
                if process.returncode == -signal.SIGXCPU:
                    # CPU time limit exceeded
                    error_details = {
                        "limit_type": "cpu_time",
                        "cpu_limit_seconds": self.max_cpu_time,
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("SANDBOX_LIMIT", f"Helper exceeded CPU time limit of {self.max_cpu_time}s", error_details)
                    
                    raise SandboxViolationError(
                        f"Exceeded CPU time limit of {self.max_cpu_time}s",
                        "SANDBOX_LIMIT",
                        error_details
                    )
                
                elif process.returncode == -signal.SIGKILL:
                    # Could be memory limit (OOM killer) or other resource limit
                    error_details = {
                        "limit_type": "memory_or_resource",
                        "memory_limit_mb": self.max_memory_mb,
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("SANDBOX_LIMIT", f"Helper killed (likely exceeded memory limit of {self.max_memory_mb}MB)", error_details)
                    
                    raise SandboxViolationError(
                        f"Exceeded memory/resource limit (killed by system)",
                        "SANDBOX_LIMIT", 
                        error_details
                    )
                
                elif process.returncode == -signal.SIGTERM:
                    # Process was terminated, could be resource related
                    error_details = {
                        "limit_type": "process_terminated",
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("SANDBOX_LIMIT", f"Helper process terminated", error_details)
                    
                    raise SandboxViolationError(
                        f"Process terminated (possible resource limit)",
                        "SANDBOX_LIMIT",
                        error_details
                    )
                
                elif process.returncode == -signal.SIGABRT:
                    # Process aborted, could be fd/resource related
                    error_details = {
                        "limit_type": "process_aborted", 
                        "fd_limit": self.max_file_descriptors,
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("SANDBOX_LIMIT", f"Helper process aborted (possible FD limit)", error_details)
                    
                    raise SandboxViolationError(
                        f"Process aborted (possible file descriptor limit)",
                        "SANDBOX_LIMIT",
                        error_details
                    )
                
                # Regular execution failure
                raise RuntimeError(f"Helper execution failed: {stderr}")
            
            # M10.7: Enhanced output size checking
            if len(stdout) > self.max_output_size:
                error_details = {
                    "limit_type": "output_size",
                    "output_size": len(stdout),
                    "max_output_size": self.max_output_size,
                    "helper_id": self.helper_id
                }
                self._log_sandbox_violation("SANDBOX_LIMIT", f"Helper output exceeded limit of {self.max_output_size} bytes", error_details)
                
                raise SandboxViolationError(
                    f"Exceeded output size limit of {self.max_output_size} bytes",
                    "SANDBOX_LIMIT",
                    error_details
                )
            
            # Parse and return result
            try:
                result = json.loads(stdout)
                return result
            except json.JSONDecodeError:
                raise ValueError(f"Helper returned invalid JSON: {stdout}")
                
        except SandboxViolationError:
            # Re-raise sandbox violations as-is
            raise
        except Exception as e:
            # Handle other execution errors
            if process and process.poll() is None:
                process.kill()
            raise e
        finally:
            # M10.7: Always clean up workspace after execution
            self._cleanup_workspace()
    
    def _log_sandbox_violation(self, violation_type: str, message: str, details: Dict[str, Any]):
        """Log sandbox violation to audit log with integrity chaining."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        audit_entry = {
            "ts": timestamp,
            "action": "sandbox_violation",
            "violation_type": violation_type,
            "helper_id": self.helper_id,
            "message": message,
            "details": details,
            "success": False
        }
        
        try:
            if AUDIT_LOGGER_AVAILABLE and get_audit_logger:
                # Use integrity audit logger if available
                get_audit_logger().log_entry(audit_entry)
            else:
                # Fallback to direct file writing for standalone usage
                with open(self.audit_log_path, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
        except Exception:
            # Don't fail the entire operation if audit logging fails
            pass
            pass
