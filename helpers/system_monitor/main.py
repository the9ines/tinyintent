#!/usr/bin/env python3
"""
TinyIntent System Monitor Helper

Provides real-time system performance metrics including CPU, memory, disk, and network usage.
Uses psutil for cross-platform system information gathering.
"""

import sys
import json
import time
import platform
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import psutil
except ImportError:
    print(json.dumps({
        "status": "error",
        "message": "psutil library not available. Install with: pip install psutil",
        "error_code": "DEPENDENCY_MISSING"
    }))
    sys.exit(1)


def get_cpu_info() -> Dict[str, Any]:
    """Get detailed CPU information and usage."""
    try:
        # CPU usage over 1 second for accuracy
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)
        
        # CPU frequency info
        cpu_freq = psutil.cpu_freq()
        freq_info = {}
        if cpu_freq:
            freq_info = {
                "current": round(cpu_freq.current, 1) if cpu_freq.current else None,
                "min": round(cpu_freq.min, 1) if cpu_freq.min else None,
                "max": round(cpu_freq.max, 1) if cpu_freq.max else None
            }
        
        # Load averages (Unix systems only)
        load_avg = None
        try:
            load_avg = psutil.getloadavg()
            load_avg = [round(x, 2) for x in load_avg]
        except (AttributeError, OSError):
            pass  # Not available on Windows
        
        return {
            "usage_percent": round(cpu_percent, 1),
            "cores_physical": cpu_count,
            "cores_logical": cpu_count_logical,
            "frequency_mhz": freq_info,
            "load_average": load_avg
        }
    except Exception as e:
        return {"error": f"CPU info unavailable: {e}"}


def get_memory_info() -> Dict[str, Any]:
    """Get memory usage information."""
    try:
        # Virtual memory (RAM)
        virtual_mem = psutil.virtual_memory()
        
        # Swap memory
        swap_mem = psutil.swap_memory()
        
        # Convert bytes to GB for readability
        def bytes_to_gb(bytes_val: int) -> float:
            return round(bytes_val / (1024**3), 2)
        
        return {
            "virtual": {
                "total_gb": bytes_to_gb(virtual_mem.total),
                "available_gb": bytes_to_gb(virtual_mem.available),
                "used_gb": bytes_to_gb(virtual_mem.used),
                "usage_percent": round(virtual_mem.percent, 1),
                "free_gb": bytes_to_gb(virtual_mem.free)
            },
            "swap": {
                "total_gb": bytes_to_gb(swap_mem.total),
                "used_gb": bytes_to_gb(swap_mem.used),
                "free_gb": bytes_to_gb(swap_mem.free),
                "usage_percent": round(swap_mem.percent, 1)
            }
        }
    except Exception as e:
        return {"error": f"Memory info unavailable: {e}"}


def get_disk_info() -> Dict[str, Any]:
    """Get disk usage information for all mounted drives."""
    try:
        disk_info = {}
        
        # Get disk partitions
        partitions = psutil.disk_partitions()
        
        for partition in partitions:
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
                
                # Convert bytes to GB
                def bytes_to_gb(bytes_val: int) -> float:
                    return round(bytes_val / (1024**3), 2)
                
                disk_info[partition.mountpoint] = {
                    "device": partition.device,
                    "filesystem": partition.fstype,
                    "total_gb": bytes_to_gb(partition_usage.total),
                    "used_gb": bytes_to_gb(partition_usage.used),
                    "free_gb": bytes_to_gb(partition_usage.free),
                    "usage_percent": round((partition_usage.used / partition_usage.total) * 100, 1)
                }
            except (OSError, PermissionError):
                # Skip inaccessible partitions
                continue
        
        # Overall disk I/O stats
        try:
            disk_io = psutil.disk_io_counters()
            io_stats = None
            if disk_io:
                io_stats = {
                    "read_count": disk_io.read_count,
                    "write_count": disk_io.write_count,
                    "read_bytes": disk_io.read_bytes,
                    "write_bytes": disk_io.write_bytes,
                    "read_time_ms": disk_io.read_time,
                    "write_time_ms": disk_io.write_time
                }
        except:
            io_stats = None
        
        return {
            "partitions": disk_info,
            "io_stats": io_stats
        }
    except Exception as e:
        return {"error": f"Disk info unavailable: {e}"}


def get_network_info() -> Dict[str, Any]:
    """Get network interface and usage information."""
    try:
        # Network I/O statistics
        net_io = psutil.net_io_counters()
        
        # Network interfaces
        net_interfaces = {}
        for interface_name, addresses in psutil.net_if_addrs().items():
            net_interfaces[interface_name] = []
            for addr in addresses:
                addr_info = {
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast
                }
                net_interfaces[interface_name].append(addr_info)
        
        # Convert bytes to MB for readability
        def bytes_to_mb(bytes_val: int) -> float:
            return round(bytes_val / (1024**2), 2)
        
        io_stats = None
        if net_io:
            io_stats = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "bytes_sent_mb": bytes_to_mb(net_io.bytes_sent),
                "bytes_recv_mb": bytes_to_mb(net_io.bytes_recv)
            }
        
        return {
            "io_stats": io_stats,
            "interfaces": net_interfaces
        }
    except Exception as e:
        return {"error": f"Network info unavailable: {e}"}


def get_process_info(limit: int = 5) -> Dict[str, Any]:
    """Get top processes by CPU and memory usage."""
    try:
        processes = []
        
        # Get all processes
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cpu_percent': round(proc.info['cpu_percent'], 1),
                    'memory_percent': round(proc.info['memory_percent'], 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by CPU usage
        top_cpu = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:limit]
        
        # Sort by memory usage
        top_memory = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:limit]
        
        return {
            "top_cpu": top_cpu,
            "top_memory": top_memory,
            "total_processes": len(processes)
        }
    except Exception as e:
        return {"error": f"Process info unavailable: {e}"}


def get_system_info() -> Dict[str, Any]:
    """Get general system information."""
    try:
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime_seconds = time.time() - psutil.boot_time()
        
        # Convert uptime to human readable format
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "processor": platform.processor(),
            "architecture": platform.architecture()[0],
            "hostname": platform.node(),
            "boot_time": boot_time.isoformat(),
            "uptime": f"{days}d {hours}h {minutes}m",
            "uptime_seconds": int(uptime_seconds)
        }
    except Exception as e:
        return {"error": f"System info unavailable: {e}"}


def format_summary(data: Dict[str, Any]) -> str:
    """Create a human-readable summary of system status."""
    lines = []
    
    # System info
    if "system" in data and "error" not in data["system"]:
        sys_info = data["system"]
        lines.append(f"🖥️  System: {sys_info.get('system')} on {sys_info.get('hostname')}")
        lines.append(f"⏱️  Uptime: {sys_info.get('uptime')}")
    
    # CPU info
    if "cpu" in data and "error" not in data["cpu"]:
        cpu = data["cpu"]
        lines.append(f"⚡ CPU: {cpu.get('usage_percent')}% ({cpu.get('cores_logical')} cores)")
    
    # Memory info
    if "memory" in data and "error" not in data["memory"]:
        mem = data["memory"]["virtual"]
        lines.append(f"💾 Memory: {mem.get('usage_percent')}% ({mem.get('used_gb')}/{mem.get('total_gb')} GB)")
    
    # Disk info
    if "disk" in data and "error" not in data["disk"] and data["disk"].get("partitions"):
        # Show main partition (usually /)
        main_partition = None
        for mount, info in data["disk"]["partitions"].items():
            if mount in ["/", "C:\\"]:
                main_partition = info
                break
        
        if not main_partition and data["disk"]["partitions"]:
            # Fallback to first partition
            main_partition = list(data["disk"]["partitions"].values())[0]
        
        if main_partition:
            lines.append(f"💿 Disk: {main_partition.get('usage_percent')}% ({main_partition.get('used_gb')}/{main_partition.get('total_gb')} GB)")
    
    # Network info
    if "network" in data and "error" not in data["network"] and data["network"].get("io_stats"):
        net = data["network"]["io_stats"]
        lines.append(f"🌐 Network: ↓{net.get('bytes_recv_mb')} MB ↑{net.get('bytes_sent_mb')} MB")
    
    return "\n".join(lines)


def main():
    """Main entry point for the system monitor helper."""
    try:
        # Read input from stdin
        input_data = json.loads(sys.stdin.read())
        
        operation = input_data.get("operation", "overview")
        format_type = input_data.get("format", "summary")  # summary, detailed, json
        include_processes = input_data.get("include_processes", False)
        process_limit = input_data.get("process_limit", 5)
        
        # Collect system data based on operation
        system_data = {}
        
        if operation in ["overview", "all", "cpu"]:
            system_data["cpu"] = get_cpu_info()
        
        if operation in ["overview", "all", "memory", "mem"]:
            system_data["memory"] = get_memory_info()
        
        if operation in ["overview", "all", "disk", "storage"]:
            system_data["disk"] = get_disk_info()
        
        if operation in ["overview", "all", "network", "net"]:
            system_data["network"] = get_network_info()
        
        if operation in ["overview", "all", "system", "info"]:
            system_data["system"] = get_system_info()
        
        if include_processes or operation == "processes":
            system_data["processes"] = get_process_info(process_limit)
        
        # Format output
        if format_type == "json":
            message = "System monitoring data (JSON format)"
            result = system_data
        elif format_type == "detailed":
            message = "Detailed system performance metrics"
            result = {
                "data": system_data,
                "summary": format_summary(system_data)
            }
        else:  # summary format
            message = format_summary(system_data)
            result = {
                "summary": message,
                "data": system_data
            }
        
        # Return success response
        response = {
            "status": "success",
            "message": message,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "helper_id": "system_monitor",
            "operation": operation
        }
        
        print(json.dumps(response, indent=2))
        
    except json.JSONDecodeError:
        print(json.dumps({
            "status": "error",
            "message": "Invalid JSON input provided",
            "error_code": "INVALID_INPUT"
        }))
        sys.exit(1)
        
    except Exception as e:
        print(json.dumps({
            "status": "error", 
            "message": f"System monitoring failed: {str(e)}",
            "error_code": "EXECUTION_ERROR"
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()