#!/usr/bin/env python3
"""
SSH Operations Helper - Main Implementation
Handles SSH operations for bot management: restart bots, tail logs, check status
"""

import json
import sys
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List


class SSHOpsHelper:
    """SSH operations helper for bot management."""
    
    def __init__(self):
        self.ssh_host = os.getenv('SSH_HOST')
        self.ssh_user = os.getenv('SSH_USER', 'root')
        self.ssh_key_path = os.getenv('SSH_KEY_PATH')
        self.ssh_port = os.getenv('SSH_PORT', '22')
        
        if not self.ssh_host:
            raise ValueError("SSH_HOST environment variable is required")
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SSH operation based on input."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        operation = input_data.get('operation')
        target = input_data.get('target')
        
        try:
            if operation == 'restart_bot':
                result = self._restart_bot(target, input_data)
            elif operation == 'tail_logs':
                result = self._tail_logs(input_data)
            elif operation == 'check_status':
                result = self._check_status(target, input_data)
            elif operation == 'list_processes':
                result = self._list_processes(input_data)
            else:
                raise ValueError(f"Unknown operation: {operation}")
            
            execution_time = time.time() - start_time
            
            # Add standard fields
            result.update({
                "operation": operation,
                "timestamp": timestamp,
                "execution_time": round(execution_time, 3)
            })
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "status": "error",
                "operation": operation,
                "target": target,
                "message": f"Operation failed: {str(e)}",
                "error": str(e),
                "timestamp": timestamp,
                "execution_time": round(execution_time, 3)
            }
    
    def _build_ssh_command(self, remote_command: str, timeout: int = 30) -> List[str]:
        """Build SSH command with proper options."""
        cmd = [
            'ssh',
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-p', self.ssh_port
        ]
        
        if self.ssh_key_path:
            cmd.extend(['-i', self.ssh_key_path])
        
        cmd.append(f"{self.ssh_user}@{self.ssh_host}")
        cmd.append(remote_command)
        
        return cmd
    
    def _execute_ssh_command(self, remote_command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute SSH command and return result."""
        cmd = self._build_ssh_command(remote_command, timeout)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"SSH command timed out after {timeout}s")
        except FileNotFoundError:
            raise RuntimeError("SSH client not found. Please install OpenSSH client.")
    
    def _restart_bot(self, target: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Restart a specific bot via SSH."""
        if not target:
            raise ValueError("Target bot name is required for restart operation")
        
        timeout = input_data.get('timeout', 30)
        
        # Try systemctl first, then fallback to process management
        restart_commands = [
            f"sudo systemctl restart {target}",
            f"sudo service {target} restart",
            f"pkill -f {target} && sleep 2 && nohup {target} &"
        ]
        
        for cmd in restart_commands:
            try:
                result = self._execute_ssh_command(cmd, timeout)
                
                if result['returncode'] == 0:
                    return {
                        "status": "success",
                        "target": target,
                        "message": f"Successfully restarted {target}",
                        "output": result['stdout'].strip()
                    }
                
            except Exception as e:
                continue  # Try next command
        
        # All commands failed
        return {
            "status": "error",
            "target": target,
            "message": f"Failed to restart {target}",
            "error": "All restart methods failed"
        }
    
    def _tail_logs(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Tail log files via SSH."""
        log_path = input_data.get('log_path')
        lines = input_data.get('lines', 50)
        timeout = input_data.get('timeout', 30)
        
        if not log_path:
            raise ValueError("log_path is required for tail_logs operation")
        
        # Build tail command
        remote_command = f"tail -n {lines} {log_path}"
        
        try:
            result = self._execute_ssh_command(remote_command, timeout)
            
            if result['returncode'] == 0:
                return {
                    "status": "success",
                    "target": log_path,
                    "message": f"Retrieved {lines} lines from {log_path}",
                    "output": result['stdout']
                }
            else:
                return {
                    "status": "error",
                    "target": log_path,
                    "message": f"Failed to tail {log_path}",
                    "error": result['stderr']
                }
                
        except Exception as e:
            raise RuntimeError(f"Failed to tail logs: {str(e)}")
    
    def _check_status(self, target: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check status of a specific service/process."""
        timeout = input_data.get('timeout', 30)
        
        if target:
            # Check specific target
            status_commands = [
                f"systemctl is-active {target}",
                f"service {target} status",
                f"pgrep -f {target}"
            ]
            
            for cmd in status_commands:
                try:
                    result = self._execute_ssh_command(cmd, timeout)
                    
                    if result['returncode'] == 0:
                        return {
                            "status": "success",
                            "target": target,
                            "message": f"{target} is running",
                            "output": result['stdout'].strip()
                        }
                        
                except Exception:
                    continue
            
            return {
                "status": "warning",
                "target": target,
                "message": f"{target} is not running or not found",
                "output": ""
            }
        else:
            # General system status
            cmd = "uptime && df -h && free -h"
            result = self._execute_ssh_command(cmd, timeout)
            
            return {
                "status": "success",
                "target": "system",
                "message": "System status retrieved",
                "output": result['stdout']
            }
    
    def _list_processes(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """List running processes via SSH."""
        timeout = input_data.get('timeout', 30)
        
        # Get process list with formatting
        cmd = "ps aux --sort=-%cpu | head -20"
        
        try:
            result = self._execute_ssh_command(cmd, timeout)
            
            if result['returncode'] == 0:
                # Parse process output
                processes = []
                lines = result['stdout'].strip().split('\n')[1:]  # Skip header
                
                for line in lines:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append({
                            "pid": int(parts[1]),
                            "name": parts[10],
                            "status": "running",
                            "cpu": parts[2] + "%",
                            "memory": parts[3] + "%"
                        })
                
                return {
                    "status": "success",
                    "target": "system",
                    "message": f"Retrieved {len(processes)} processes",
                    "output": result['stdout'],
                    "processes": processes
                }
            else:
                return {
                    "status": "error",
                    "target": "system",
                    "message": "Failed to list processes",
                    "error": result['stderr']
                }
                
        except Exception as e:
            raise RuntimeError(f"Failed to list processes: {str(e)}")


def main():
    """Main entry point for SSH operations helper."""
    try:
        # Read input from stdin
        input_json = sys.stdin.read().strip()
        if not input_json:
            raise ValueError("No input provided")
        
        input_data = json.loads(input_json)
        
        # Create helper and execute
        helper = SSHOpsHelper()
        result = helper.execute(input_data)
        
        # Output result as JSON
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        error_result = {
            "status": "error",
            "operation": "unknown",
            "message": f"Helper execution failed: {str(e)}",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()