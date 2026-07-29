# 🌐 Network Infrastructure Monitoring

**Enterprise-Grade Network Automation via Voice Commands**

Transform your iPhone into a powerful network engineering control center. Monitor Cisco Enterprise and Ubiquiti devices, detect anomalies, predict failures, and automate configuration backups - all through simple voice commands.

---

## 🎯 Overview

The TinyIntent network monitoring system provides comprehensive automation for enterprise network infrastructure:

- **🔧 Cisco Enterprise Support**: Switches, routers, access points via SNMP v2c/v3
- **📡 Ubiquiti UniFi Integration**: APs, switches, gateways via Controller API
- **🤖 ML Anomaly Detection**: Isolation Forest and One-Class SVM models
- **📊 Rule-Based Alerting**: Immediate alerts for critical thresholds
- **🔮 Predictive Maintenance**: Device failure probability with time estimates
- **💾 Automated Backups**: Configuration backup before predicted failures
- **🔍 Cable Health Analysis**: Link stability and error rate monitoring

---

## 🗣️ Voice Commands

### Network Health Monitoring
- *"Are there any network anomalies?"*
- *"Check my network devices"*
- *"Show me network status"*
- *"Monitor network health"*
- *"What's the network condition?"*

### Device Management
- *"Backup router configurations"*
- *"Check device health"*
- *"Show me network devices"*
- *"Monitor switch performance"*

### Troubleshooting
- *"Check network errors"*
- *"Show me interface status"*
- *"Are there any cable issues?"*
- *"Check network performance"*

---

## 🏗️ Architecture

### Network Monitor Helper Structure

```
helpers/network_monitor/
├── main.py                 # Core monitoring engine (2,100+ lines)
├── helper.yaml            # Helper configuration & capabilities
├── package.json           # npm-style package metadata  
├── input.schema.json      # Input validation (200+ lines)
├── output.schema.json     # Output format specification
├── health.py              # Dependency & system health checks
└── provenance.json        # Cryptographic signature for security
```

### Core Components

1. **NetworkDeviceCollector**: SNMP and API data collection
2. **NetworkAnomalyDetector**: ML and rule-based anomaly detection  
3. **DeviceFailurePrediction**: Predictive failure analysis
4. **ConfigBackupManager**: Automated configuration backups

---

## 🔧 Cisco Enterprise Setup

### SNMP Configuration

#### SNMPv2c Setup (Basic)
```bash
# Configure SNMP community on Cisco device
configure terminal
snmp-server community public RO
snmp-server community private RW
```

#### SNMPv3 Setup (Secure)
```bash
# Create SNMPv3 user with authentication and privacy
configure terminal
snmp-server user tinyintent-monitor GROUP-NAME v3 auth sha AUTH-PASSWORD priv aes 128 PRIV-PASSWORD
snmp-server group GROUP-NAME v3 priv read VIEW-NAME
snmp-server view VIEW-NAME internet included
```

### Voice Command Example

**You say**: *"Check my network devices"*

**TinyIntent executes**:
```python
# Collect metrics via SNMP
cisco_metrics = {
    "device_host": "192.168.1.1",
    "device_type": "cisco",
    "sysUpTime": "1234567890",  # Device uptime
    "cpuUtil": "25",            # 25% CPU usage
    "memoryUtil": "512000000",  # Memory usage in bytes
    "interfaces": {
        "total_interfaces": 48,
        "active_interfaces": 36,
        "error_rate": 0.0005,   # 0.05% error rate
        "utilization_avg": 32.1 # Average utilization
    }
}
```

**You hear**: *"Cisco switch at 192.168.1.1: Running normally with 25% CPU usage and 512MB memory. All 48 interfaces active with 0.05% error rate. No anomalies detected."*

---

## 📡 Ubiquiti UniFi Setup

### Controller API Configuration

1. **UniFi Controller Access**:
   ```bash
   # Access UniFi Controller web interface
   https://unifi.yourdomain.com:8443
   
   # Create dedicated user for TinyIntent
   Username: tinyintent-monitor
   Password: [secure-password]
   Role: Administrator (read-only custom role recommended)
   ```

2. **API Integration**:
   ```python
   # Helper automatically handles:
   - Authentication with Controller
   - Device discovery and enumeration
   - Real-time metrics collection
   - WiFi performance analysis
   ```

### Voice Command Example

**You say**: *"Are there any network anomalies?"*

**TinyIntent executes**:
```python
# Analyze UniFi device metrics
ubiquiti_analysis = {
    "device_host": "192.168.1.10",
    "anomalies_detected": True,
    "anomaly_types": ["wifi_performance_degradation"],
    "wifi_performance": {
        "signal_strength_avg": -55,  # dBm
        "channel_utilization": 78,   # High utilization
        "client_satisfaction": 0.72  # Below normal
    }
}
```

**You hear**: *"Network anomaly detected on UniFi AP at 192.168.1.10: WiFi performance degradation with 78% channel utilization and client satisfaction at 72%. Consider channel optimization."*

---

## 🤖 Machine Learning Anomaly Detection

### Algorithms

#### Isolation Forest
- **Purpose**: Statistical anomaly detection in device metrics
- **Method**: Isolates anomalies by randomly selecting features and split values
- **Strengths**: Effective with high-dimensional data, unsupervised learning
- **Use Case**: Detecting unusual patterns in CPU, memory, interface utilization

#### One-Class SVM  
- **Purpose**: Learn normal device behavior patterns
- **Method**: Creates decision boundary around normal operating conditions
- **Strengths**: Robust to outliers, works well with small datasets
- **Use Case**: Identifying devices operating outside normal parameters

### Training Process
```python
# Automatic model training on historical data
features = [
    cpu_utilization,
    memory_usage, 
    interface_error_rate,
    link_utilization,
    uptime_stability
]

# Train models with 30 days of historical data
isolation_forest = IsolationForest(contamination=0.1)
isolation_forest.fit(historical_features)

svm_model = OneClassSVM(gamma='scale', nu=0.1)  
svm_model.fit(historical_features)
```

---

## 📊 Rule-Based Detection

### Immediate Alert Thresholds

```python
# Critical thresholds for instant alerts
THRESHOLDS = {
    "cpu_usage": 80,        # 80% CPU utilization
    "memory_usage": 85,     # 85% memory usage
    "error_rate": 0.01,     # 1% interface error rate
    "link_flaps": 3,        # 3+ link flaps per hour
    "response_time": 5000   # 5 second response timeout
}
```

### Anomaly Examples

1. **High CPU Usage**: Device consistently above 80% CPU
2. **Memory Leaks**: Steadily increasing memory consumption
3. **Interface Errors**: Error rate exceeding 1% threshold
4. **Link Instability**: Frequent interface up/down events
5. **Cable Issues**: High error rates on specific interfaces
6. **Performance Degradation**: Decreasing throughput over time

---

## 🔮 Predictive Failure Analysis

### Failure Indicators

#### Cisco Devices
- Increasing CPU usage trends
- Memory leak patterns  
- Interface error rate increases
- Frequent link flap events
- Temperature sensor alerts
- Power supply warnings

#### Ubiquiti Devices  
- WiFi performance degradation
- Client disconnection patterns
- Firmware stability issues
- Hardware sensor alerts

### Prediction Algorithm
```python
def predict_failure(device, metrics_history):
    """Predict device failure probability based on trends."""
    
    # Analyze metric trends over time
    trends = analyze_metric_trends(metrics_history)
    
    failure_score = 0.0
    indicators = []
    
    # Check failure indicators
    if trends.get("cpu_increasing"):
        indicators.append("increasing_cpu_usage")
        failure_score += 0.15
    
    if trends.get("memory_increasing"):
        indicators.append("memory_leak_pattern") 
        failure_score += 0.20
        
    if trends.get("error_increasing"):
        indicators.append("interface_error_increase")
        failure_score += 0.25
    
    # Calculate failure probability (0.0 to 1.0)
    failure_probability = min(failure_score, 1.0)
    
    # Estimate time to failure
    if failure_probability > 0.5:
        time_to_failure = estimate_failure_time(trends)
    else:
        time_to_failure = None
    
    return {
        "failure_probability": failure_probability,
        "time_to_failure": time_to_failure,
        "indicators": indicators,
        "recommendation": get_recommendation(failure_probability)
    }
```

---

## 💾 Automated Configuration Backup

### Backup Triggers
- **Failure Probability > 50%**: Automatic backup before predicted failure
- **Critical Anomaly Detection**: Immediate backup for severe issues
- **Manual Request**: Voice command or scheduled backup
- **Maintenance Windows**: Pre-maintenance configuration snapshots

### Cisco Backup Process
```python
async def backup_cisco_config(device):
    """Backup Cisco device configuration."""
    
    # Methods supported:
    # 1. SNMP + SSH: Get running-config via SSH
    # 2. NETCONF: Structured configuration retrieval  
    # 3. SCP: Copy configuration files
    
    backup_file = f"cisco_{device['host']}_{timestamp}.cfg"
    
    # Example configuration content
    config = """
    !
    version 15.2
    service timestamps debug datetime msec
    !
    hostname cisco-switch-01
    !
    interface GigabitEthernet0/1
     description Link to Core Switch
     switchport mode trunk
     switchport trunk allowed vlan 100,200,300
    !
    """
    
    return {
        "backup_status": "success",
        "backup_file": backup_file,
        "backup_size_bytes": len(config)
    }
```

### Ubiquiti Backup Process  
```python
async def backup_ubiquiti_config(device):
    """Backup Ubiquiti configuration via UniFi Controller."""
    
    # Controller API methods:
    # 1. Site Export: Complete site configuration
    # 2. Device Config: Individual device settings
    # 3. Network Settings: VLAN, firewall rules
    
    backup_file = f"ubiquiti_{device['host']}_{timestamp}.json"
    
    config = {
        "site_info": {
            "name": "main_site",
            "description": "Primary network site"
        },
        "devices": [...],  # Device configurations
        "networks": [...], # Network/VLAN settings  
        "firewall": [...]  # Security rules
    }
    
    return {
        "backup_status": "success",
        "backup_file": backup_file,
        "backup_method": "unifi_api"
    }
```

---

## 🎛️ Operations Guide

### Available Operations

#### Device Management
```python
# Add Cisco device for monitoring
{
    "operation": "add_cisco_device",
    "host": "192.168.1.1",
    "community": "public",
    "snmp_version": "v2c"
}

# Add Ubiquiti device via UniFi Controller  
{
    "operation": "add_ubiquiti_device", 
    "host": "192.168.1.10",
    "controller_url": "https://unifi.local:8443",
    "username": "admin",
    "password": "password"
}
```

#### Monitoring Operations
```python
# Collect real-time metrics
{
    "operation": "collect_metrics",
    "device": {
        "type": "cisco",
        "host": "192.168.1.1",
        "community": "public"
    }
}

# Detect anomalies in current metrics
{
    "operation": "detect_anomalies",
    "device_id": "192.168.1.1",
    "current_metrics": {...}
}

# Predict device failure risk
{
    "operation": "predict_failure",
    "device": {...},
    "metrics_history": [...]
}
```

#### Automation Operations
```python
# Backup device configuration
{
    "operation": "backup_config",
    "device": {
        "type": "cisco", 
        "host": "192.168.1.1"
    }
}

# Complete monitoring workflow
{
    "operation": "full_monitoring",
    "devices": [
        {"type": "cisco", "host": "192.168.1.1"},
        {"type": "ubiquiti", "host": "192.168.1.10"}
    ],
    "auto_backup": true,
    "backup_threshold": 0.5
}
```

---

## 📈 Response Examples

### Successful Monitoring Response
```json
{
  "status": "success",
  "operation": "full_monitoring",
  "timestamp": "2025-08-25T10:30:00Z",
  "monitoring_results": [
    {
      "device": {
        "type": "cisco",
        "host": "192.168.1.1"
      },
      "metrics": {
        "status": "success",
        "cpuUtil": "25",
        "memoryUtil": "512000000",
        "interfaces": {
          "total_interfaces": 48,
          "active_interfaces": 46,
          "error_rate": 0.0008
        }
      },
      "anomalies": {
        "anomalies_detected": false,
        "anomaly_score": 0.02
      },
      "failure_prediction": {
        "failure_probability": 0.15,
        "time_to_failure": null,
        "recommendation": "monitor"
      }
    }
  ],
  "summary": {
    "total_devices": 1,
    "devices_with_anomalies": 0,
    "high_risk_devices": 0,
    "backups_created": 0
  },
  "message": "Network monitoring completed successfully"
}
```

### Anomaly Detection Response
```json
{
  "status": "success", 
  "operation": "detect_anomalies",
  "anomalies": {
    "device_id": "192.168.1.1",
    "anomalies_detected": true,
    "anomaly_score": 0.85,
    "anomaly_types": [
      "high_cpu_usage",
      "interface_error_increase"
    ],
    "confidence": 0.92,
    "recommendations": [
      "CPU usage at 87% - investigate high load processes",
      "Interface error rate 1.2% - check cable connections"
    ]
  },
  "message": "Critical anomalies detected on device 192.168.1.1"
}
```

---

## 🔒 Security Considerations

### Network Access Security
- **SNMP Community Strings**: Use strong, unique community strings
- **SNMPv3**: Prefer SNMPv3 with authentication and encryption
- **API Credentials**: Secure storage of UniFi Controller credentials
- **Network Segmentation**: Monitor from dedicated management network

### TinyIntent Security
- **Sandboxed Execution**: Network monitor runs in isolated container
- **Capability Controls**: Explicit network and filesystem permissions
- **Audit Logging**: Complete audit trail of all monitoring operations
- **Encrypted Storage**: Configuration backups encrypted at rest

### Best Practices
1. **Least Privilege**: Use read-only SNMP communities where possible
2. **Regular Rotation**: Rotate API credentials and SNMP strings regularly  
3. **Network Monitoring**: Monitor the monitoring system itself
4. **Backup Security**: Encrypt and secure configuration backups

---

## 🚀 Getting Started

### Quick Setup (Development)
```bash
# 1. Start TinyIntent
tinyintent

# 2. Test network monitoring
curl -X POST http://localhost:8787/route \
  -H "X-TinyIntent-Secret: your-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "check my network devices", 
    "route": "act",
    "helper_id": "network_monitor"
  }'
```

### Production Deployment
1. **Configure SNMP**: Set up SNMPv3 on all Cisco devices
2. **UniFi Integration**: Create monitoring user in UniFi Controller  
3. **Network Access**: Ensure TinyIntent can reach all devices
4. **Security Setup**: Configure proper authentication and encryption
5. **Voice Integration**: Set up iPhone Shortcuts for voice commands

### Voice Command Setup
Add these to your iPhone Shortcut:

- Voice Input: "Check my network"
- HTTP Request to: `http://your-ip:8787/shortcut/route`  
- Body: `{"text": "[voice input]", "return_format": "minimal"}`
- Speak the response for hands-free network monitoring

---

## 🎯 Use Cases

### Network Operations Center (NOC)
- **24/7 Monitoring**: Continuous anomaly detection across enterprise infrastructure
- **Proactive Maintenance**: Predict and prevent device failures
- **Incident Response**: Immediate alerts for critical network issues
- **Configuration Management**: Automated backup before maintenance

### Field Engineers
- **Remote Diagnostics**: Voice-activated network health checks
- **Troubleshooting**: Quick identification of problematic devices
- **Maintenance Planning**: Failure predictions guide maintenance schedules
- **Documentation**: Automated configuration backups for compliance

### IT Administrators  
- **Daily Health Checks**: Morning network status briefings via voice
- **Performance Monitoring**: Ongoing infrastructure performance tracking
- **Capacity Planning**: Trend analysis for network capacity management
- **Security Monitoring**: Anomaly detection for potential security issues

---

## 🛠️ Troubleshooting

### Common Issues

#### SNMP Connectivity
```bash
# Test SNMP connectivity
snmpwalk -v2c -c public 192.168.1.1 1.3.6.1.2.1.1.1.0

# Expected output: Device system description
```

#### UniFi Controller Access
```bash
# Test Controller API access
curl -k https://unifi.local:8443/api/login \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}'
```

#### Dependency Issues
```bash
# Install required Python packages
pip install pysnmp aiohttp scikit-learn numpy

# Test dependencies
python3 helpers/network_monitor/health.py
```

### Debug Mode
```bash
# Enable detailed logging
TINYINTENT_LOG_LEVEL=debug tinyintent
```

---

## 📊 Monitoring Metrics

### Key Performance Indicators

#### Device Health
- **Uptime**: Device availability and stability
- **CPU Utilization**: Processing load and capacity
- **Memory Usage**: RAM consumption and potential leaks
- **Interface Status**: Link state and operational status

#### Network Performance  
- **Error Rates**: Interface errors and packet loss
- **Utilization**: Bandwidth usage and capacity planning
- **Latency**: Response times and network delay
- **Throughput**: Data transfer rates and performance

#### Anomaly Detection
- **Detection Rate**: Percentage of actual anomalies identified
- **False Positive Rate**: Incorrect anomaly classifications
- **Prediction Accuracy**: Failure prediction success rate
- **Response Time**: Time from anomaly to alert

---

## 🎉 Advanced Features

### Custom Alerting
```python
# Define custom alert thresholds
CUSTOM_THRESHOLDS = {
    "critical_cpu": 90,
    "warning_cpu": 75,
    "critical_memory": 95,
    "warning_memory": 80,
    "interface_errors": 0.005
}
```

### Integration Possibilities
- **Slack/Teams**: Send alerts to collaboration platforms
- **ITSM Tools**: Create tickets in ServiceNow, Jira
- **Monitoring Dashboards**: Feed data to Grafana, Datadog
- **Network Management**: Integration with SolarWinds, PRTG

### Extensibility  
- **Additional Vendors**: Add support for Aruba, Juniper, etc.
- **Custom Metrics**: Define domain-specific monitoring parameters
- **ML Model Tuning**: Adjust anomaly detection sensitivity
- **Backup Integrations**: Support additional backup destinations

---

**Ready to transform your network monitoring with voice automation?** 

Start with the quick setup guide and experience enterprise-grade network infrastructure management through simple iPhone voice commands!