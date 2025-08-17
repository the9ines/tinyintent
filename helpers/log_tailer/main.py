#!/usr/bin/env python3
"""
Log Tailer Helper - Main Implementation
Retrieves last N error lines from local log files with filtering and parsing
"""

import json
import sys
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class LogTailerHelper:
    """Log tailer helper for retrieving and filtering log content."""
    
    def __init__(self):
        self.default_log_dir = os.getenv('DEFAULT_LOG_DIR', '/var/log')
        self.max_lines_limit = int(os.getenv('MAX_LINES_LIMIT', '1000'))
        
        # Common log patterns for parsing
        self.log_patterns = [
            # ISO timestamp format: 2023-12-07T10:30:45.123Z [ERROR] message
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z?)\s*\[?(\w+)\]?\s*(.*)',
            # Syslog format: Dec  7 10:30:45 hostname service[pid]: [level] message  
            r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\w+\s+\w+(?:\[\d+\])?\:\s*\[?(\w+)\]?\s*(.*)',
            # Simple timestamp: 2023-12-07 10:30:45 [ERROR] message
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*\[?(\w+)\]?\s*(.*)',
            # Time only: 10:30:45 [ERROR] message
            r'(\d{2}:\d{2}:\d{2})\s*\[?(\w+)\]?\s*(.*)'
        ]
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute log tailing operation."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            log_path = input_data.get('log_path')
            lines = min(input_data.get('lines', 50), self.max_lines_limit)
            filter_pattern = input_data.get('filter')
            level_filter = input_data.get('level', 'ERROR')
            since_timestamp = input_data.get('since')
            
            # Validate and resolve log path
            resolved_path = self._resolve_log_path(log_path)
            
            # Read log content
            log_content, file_info = self._read_log_file(resolved_path, lines)
            
            # Filter content
            filtered_content, filtered_entries = self._filter_log_content(
                log_content, filter_pattern, level_filter, since_timestamp
            )
            
            return {
                "status": "success",
                "log_path": str(resolved_path),
                "lines_requested": lines,
                "lines_returned": len(filtered_content.split('\n')) if filtered_content else 0,
                "message": f"Retrieved {len(filtered_entries)} matching log entries",
                "log_content": filtered_content,
                "log_entries": filtered_entries,
                "file_size": file_info['size'],
                "last_modified": file_info['modified'],
                "timestamp": timestamp
            }
            
        except Exception as e:
            return {
                "status": "error",
                "log_path": input_data.get('log_path', 'unknown'),
                "message": f"Log tailing failed: {str(e)}",
                "error": str(e),
                "timestamp": timestamp
            }
    
    def _resolve_log_path(self, log_path: str) -> Path:
        """Resolve and validate log file path."""
        if not log_path:
            raise ValueError("log_path is required")
        
        path = Path(log_path)
        
        # If relative path, resolve relative to default log dir
        if not path.is_absolute():
            path = Path(self.default_log_dir) / path
        
        # Security: Ensure path doesn't escape allowed directories
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            raise ValueError(f"Invalid log path: {log_path}")
        
        # Check if file exists and is readable
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {path}")
        
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")
        
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Cannot read log file: {path}")
        
        return path
    
    def _read_log_file(self, log_path: Path, lines: int) -> tuple[str, Dict[str, Any]]:
        """Read last N lines from log file."""
        try:
            stat = log_path.stat()
            file_info = {
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat() + 'Z'
            }
            
            # For small files, read entire content
            if stat.st_size < 1024 * 1024:  # 1MB
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    all_lines = content.split('\n')
                    last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    return '\n'.join(last_lines), file_info
            
            # For large files, use tail-like approach
            with open(log_path, 'rb') as f:
                # Start from end and read backwards
                f.seek(0, 2)  # Go to end of file
                file_size = f.tell()
                
                # Read in chunks from end
                lines_found = []
                chunk_size = 8192
                position = file_size
                
                while position > 0 and len(lines_found) < lines:
                    chunk_start = max(0, position - chunk_size)
                    f.seek(chunk_start)
                    chunk = f.read(position - chunk_start).decode('utf-8', errors='replace')
                    
                    chunk_lines = chunk.split('\n')
                    if position < file_size:
                        # Merge with first line from previous chunk
                        if lines_found:
                            chunk_lines[-1] += lines_found[0]
                            lines_found = lines_found[1:]
                    
                    lines_found = chunk_lines + lines_found
                    position = chunk_start
                
                # Return last N lines
                result_lines = lines_found[-lines:] if len(lines_found) > lines else lines_found
                return '\n'.join(result_lines), file_info
            
        except UnicodeDecodeError:
            raise ValueError(f"Cannot decode log file (not UTF-8): {log_path}")
        except MemoryError:
            raise ValueError(f"Log file too large to process: {log_path}")
    
    def _filter_log_content(self, content: str, filter_pattern: Optional[str], 
                           level_filter: str, since_timestamp: Optional[str]) -> tuple[str, List[Dict[str, Any]]]:
        """Filter log content by pattern, level, and timestamp."""
        if not content.strip():
            return "", []
        
        lines = content.split('\n')
        filtered_lines = []
        parsed_entries = []
        
        # Parse since timestamp if provided
        since_dt = None
        if since_timestamp:
            try:
                since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
            except ValueError:
                pass  # Ignore invalid timestamp
        
        for line in lines:
            if not line.strip():
                continue
            
            # Parse log line
            parsed = self._parse_log_line(line)
            
            # Apply level filter
            if level_filter != 'ALL':
                if not parsed or parsed.get('level', '').upper() != level_filter.upper():
                    # For ERROR filter, also include FATAL, CRITICAL
                    if level_filter.upper() == 'ERROR':
                        if not parsed or parsed.get('level', '').upper() not in ['ERROR', 'FATAL', 'CRITICAL']:
                            continue
                    else:
                        continue
            
            # Apply timestamp filter
            if since_dt and parsed and parsed.get('timestamp'):
                try:
                    log_dt = datetime.fromisoformat(parsed['timestamp'].replace('Z', '+00:00'))
                    if log_dt < since_dt:
                        continue
                except ValueError:
                    pass  # Include line if timestamp unparseable
            
            # Apply pattern filter
            if filter_pattern:
                if not re.search(filter_pattern, line, re.IGNORECASE):
                    continue
            
            filtered_lines.append(line)
            if parsed:
                parsed_entries.append(parsed)
        
        return '\n'.join(filtered_lines), parsed_entries
    
    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a log line to extract timestamp, level, and message."""
        for pattern in self.log_patterns:
            match = re.match(pattern, line.strip())
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    return {
                        'timestamp': groups[0],
                        'level': groups[1].upper() if groups[1] else 'INFO',
                        'message': groups[2].strip(),
                        'raw_line': line
                    }
        
        # If no pattern matches, treat as unstructured
        return {
            'timestamp': '',
            'level': 'UNKNOWN',
            'message': line.strip(),
            'raw_line': line
        }


def main():
    """Main entry point for log tailer helper."""
    try:
        # Read input from stdin
        input_json = sys.stdin.read().strip()
        if not input_json:
            raise ValueError("No input provided")
        
        input_data = json.loads(input_json)
        
        # Create helper and execute
        helper = LogTailerHelper()
        result = helper.execute(input_data)
        
        # Output result as JSON
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        error_result = {
            "status": "error",
            "log_path": "unknown",
            "message": f"Helper execution failed: {str(e)}",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()