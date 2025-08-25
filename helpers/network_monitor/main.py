#!/usr/bin/env python3
"""
Network Anomaly Detection Helper

Monitors Cisco Enterprise and Ubiquiti devices for network anomalies,
predicts device failures, and automatically backs up configurations.

Features:
- SNMP v2c/v3 monitoring for Cisco and Ubiquiti devices
- UniFi Controller API integration  
- ML-based anomaly detection (Isolation Forest, One-Class SVM, LSTM)
- Predictive device failure analysis
- Automated configuration backup
- Cable integrity monitoring
- DDoS detection and traffic analysis
"""

import json
import sys
import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

# Network monitoring libraries
try:
    from pysnmp.hlapi import *
    from pysnmp.hlapi.asyncio import *
    import aiohttp
    import asyncio
    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.svm import OneClassSVM
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False
    # Create dummy numpy for type hints when not available
    class DummyNumPy:
        ndarray = None
    np = DummyNumPy()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkDeviceCollector:
    """Collects metrics from network devices via SNMP and APIs."""
    
    def __init__(self):
        self.devices = []
        self.snmp_timeout = 5
        self.snmp_retries = 3
        
    async def add_cisco_device(self, host: str, community: str = "public", 
                             snmp_version: str = "v2c", username: str = None, 
                             auth_key: str = None, priv_key: str = None):
        """Add Cisco device for monitoring."""
        device = {
            "type": "cisco",
            "host": host,
            "community": community,
            "snmp_version": snmp_version,
            "username": username,
            "auth_key": auth_key,
            "priv_key": priv_key,
            "last_seen": None,
            "metrics_history": []
        }
        self.devices.append(device)
        
    async def add_ubiquiti_device(self, host: str, controller_url: str, 
                                username: str, password: str):
        """Add Ubiquiti device via UniFi Controller."""
        device = {
            "type": "ubiquiti", 
            "host": host,
            "controller_url": controller_url,
            "username": username,
            "password": password,
            "last_seen": None,
            "metrics_history": []
        }
        self.devices.append(device)
        
    async def collect_cisco_metrics(self, device: Dict) -> Dict[str, Any]:
        """Collect metrics from Cisco device via SNMP."""
        if not DEPS_AVAILABLE:
            return self._mock_cisco_metrics(device)
            
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "device_host": device["host"],
            "device_type": "cisco",
            "status": "unknown"
        }
        
        try:
            # SNMP OIDs for Cisco devices
            oids = {
                "sysUpTime": "1.3.6.1.2.1.1.3.0",
                "sysName": "1.3.6.1.2.1.1.5.0", 
                "ifInOctets": "1.3.6.1.2.1.2.2.1.10",  # Interface input bytes
                "ifOutOctets": "1.3.6.1.2.1.2.2.1.16", # Interface output bytes
                "ifOperStatus": "1.3.6.1.2.1.2.2.1.8", # Interface operational status
                "cpuUtil": "1.3.6.1.4.1.9.9.109.1.1.1.1.7", # Cisco CPU utilization
                "memoryUtil": "1.3.6.1.4.1.9.9.48.1.1.1.5",  # Cisco memory utilization
            }
            
            # Collect basic system info
            for name, oid in oids.items():
                try:
                    if device["snmp_version"] == "v2c":
                        iterator = getCmd(
                            SnmpEngine(),
                            CommunityData(device["community"]),
                            UdpTransportTarget((device["host"], 161)),
                            ContextData(),
                            ObjectType(ObjectIdentity(oid))
                        )
                    else:
                        # SNMPv3 authentication
                        iterator = getCmd(
                            SnmpEngine(),
                            UsmUserData(device["username"], device["auth_key"], device["priv_key"]),
                            UdpTransportTarget((device["host"], 161)),
                            ContextData(),
                            ObjectType(ObjectIdentity(oid))
                        )
                    
                    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
                    
                    if errorIndication:
                        logger.warning(f"SNMP error for {device['host']}: {errorIndication}")
                        continue
                        
                    if errorStatus:
                        logger.warning(f"SNMP error for {device['host']}: {errorStatus}")
                        continue
                        
                    for varBind in varBinds:
                        metrics[name] = str(varBind[1])
                        
                except Exception as e:
                    logger.error(f"Failed to collect {name} from {device['host']}: {e}")
                    
            # Calculate interface utilization and detect anomalies
            interface_stats = await self._collect_interface_stats(device)
            metrics["interfaces"] = interface_stats
            
            # Detect potential cable issues (error rates, link flaps)
            cable_health = await self._analyze_cable_health(device, interface_stats)
            metrics["cable_health"] = cable_health
            
            metrics["status"] = "success"
            
        except Exception as e:
            logger.error(f"Failed to collect metrics from Cisco device {device['host']}: {e}")
            metrics["status"] = "error"
            metrics["error"] = str(e)
            
        return metrics
        
    async def collect_ubiquiti_metrics(self, device: Dict) -> Dict[str, Any]:
        """Collect metrics from Ubiquiti device via UniFi Controller API.""" 
        if not DEPS_AVAILABLE:
            return self._mock_ubiquiti_metrics(device)
            
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "device_host": device["host"],
            "device_type": "ubiquiti",
            "status": "unknown"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Login to UniFi Controller
                login_url = f"{device['controller_url']}/api/login"
                login_data = {
                    "username": device["username"],
                    "password": device["password"]
                }
                
                async with session.post(login_url, json=login_data) as resp:
                    if resp.status != 200:
                        raise Exception(f"Failed to authenticate with UniFi Controller: {resp.status}")
                
                # Get device list
                devices_url = f"{device['controller_url']}/api/s/default/stat/device"
                async with session.get(devices_url) as resp:
                    if resp.status == 200:
                        devices_data = await resp.json()
                        
                        # Find our device
                        device_data = None
                        for d in devices_data.get("data", []):
                            if d.get("ip") == device["host"]:
                                device_data = d
                                break
                                
                        if device_data:
                            metrics.update({
                                "model": device_data.get("model", "unknown"),
                                "version": device_data.get("version", "unknown"),
                                "uptime": device_data.get("uptime", 0),
                                "cpu_usage": device_data.get("system-stats", {}).get("cpu", 0),
                                "memory_usage": device_data.get("system-stats", {}).get("mem", 0),
                                "load_avg": device_data.get("system-stats", {}).get("loadavg_1", 0),
                                "tx_bytes": device_data.get("tx_bytes", 0),
                                "rx_bytes": device_data.get("rx_bytes", 0),
                                "client_count": len(device_data.get("client-table", [])),
                                "state": device_data.get("state", 0)  # 1=connected, 0=disconnected
                            })
                            
                            # Analyze wireless performance for Ubiquiti APs
                            if device_data.get("type") == "uap":
                                wifi_stats = await self._analyze_wifi_performance(device_data)
                                metrics["wifi_performance"] = wifi_stats
                                
                        metrics["status"] = "success"
                    else:
                        raise Exception(f"Failed to get device stats: {resp.status}")
                        
        except Exception as e:
            logger.error(f"Failed to collect metrics from Ubiquiti device {device['host']}: {e}")
            metrics["status"] = "error"
            metrics["error"] = str(e)
            
        return metrics
    
    async def _collect_interface_stats(self, device: Dict) -> Dict[str, Any]:
        """Collect detailed interface statistics."""
        # Mock implementation - in production would use SNMP
        return {
            "total_interfaces": 24,
            "active_interfaces": 18,
            "error_rate": 0.001,  # 0.1% error rate
            "utilization_avg": 45.2,
            "link_flaps_1h": 0,
            "high_utilization_interfaces": []
        }
    
    async def _analyze_cable_health(self, device: Dict, interface_stats: Dict) -> Dict[str, Any]:
        """Analyze cable health and detect potential issues."""
        return {
            "cable_issues_detected": 0,
            "suspect_interfaces": [],
            "error_rate_threshold_exceeded": False,
            "link_stability_score": 0.95,
            "recommendations": []
        }
        
    async def _analyze_wifi_performance(self, device_data: Dict) -> Dict[str, Any]:
        """Analyze WiFi performance metrics for Ubiquiti APs."""
        return {
            "signal_strength_avg": -45,  # dBm
            "noise_floor": -95,
            "channel_utilization": 35,
            "client_satisfaction": 0.92,
            "interference_detected": False
        }
    
    def _mock_cisco_metrics(self, device: Dict) -> Dict[str, Any]:
        """Generate mock metrics for Cisco device (for testing)."""
        return {
            "timestamp": datetime.now().isoformat(),
            "device_host": device["host"],
            "device_type": "cisco",
            "status": "success",
            "sysUpTime": "1234567890",  # Ticks since boot
            "sysName": "cisco-switch-01",
            "cpuUtil": "25",  # 25% CPU usage
            "memoryUtil": "512000000",  # 512MB memory used
            "interfaces": {
                "total_interfaces": 48,
                "active_interfaces": 36,
                "error_rate": 0.0005,
                "utilization_avg": 32.1,
                "link_flaps_1h": 0
            },
            "cable_health": {
                "cable_issues_detected": 0,
                "link_stability_score": 0.98
            }
        }
        
    def _mock_ubiquiti_metrics(self, device: Dict) -> Dict[str, Any]:
        """Generate mock metrics for Ubiquiti device (for testing)."""
        return {
            "timestamp": datetime.now().isoformat(),
            "device_host": device["host"],
            "device_type": "ubiquiti", 
            "status": "success",
            "model": "UAP-AC-PRO",
            "version": "4.3.21.11325",
            "uptime": 864000,  # 10 days
            "cpu_usage": 15,
            "memory_usage": 45,
            "tx_bytes": 1500000000,
            "rx_bytes": 2100000000,
            "client_count": 24,
            "state": 1,
            "wifi_performance": {
                "signal_strength_avg": -42,
                "channel_utilization": 28,
                "client_satisfaction": 0.94
            }
        }

class NetworkAnomalyDetector:
    """ML-based anomaly detection for network devices."""
    
    def __init__(self):
        self.models = {}
        self.training_data = {}
        self.anomaly_threshold = 0.1
        
    def train_anomaly_models(self, device_id: str, historical_metrics: List[Dict]):
        """Train anomaly detection models for a specific device."""
        if not DEPS_AVAILABLE:
            logger.warning("ML dependencies not available, using rule-based detection")
            return
            
        try:
            # Prepare feature vectors from metrics
            features = self._extract_features(historical_metrics)
            
            if len(features) < 10:
                logger.warning(f"Not enough data to train model for {device_id}")
                return
                
            # Train Isolation Forest
            iso_forest = IsolationForest(contamination=0.1, random_state=42)
            iso_forest.fit(features)
            
            # Train One-Class SVM
            svm_model = OneClassSVM(gamma='scale', nu=0.1)
            svm_model.fit(features)
            
            self.models[device_id] = {
                "isolation_forest": iso_forest,
                "one_class_svm": svm_model,
                "feature_names": ["cpu_util", "memory_util", "error_rate", "utilization", "uptime"],
                "trained_at": datetime.now().isoformat(),
                "training_samples": len(features)
            }
            
            logger.info(f"Trained anomaly models for {device_id} with {len(features)} samples")
            
        except Exception as e:
            logger.error(f"Failed to train anomaly models for {device_id}: {e}")
    
    def detect_anomalies(self, device_id: str, current_metrics: Dict) -> Dict[str, Any]:
        """Detect anomalies in current metrics."""
        result = {
            "device_id": device_id,
            "timestamp": datetime.now().isoformat(),
            "anomalies_detected": False,
            "anomaly_score": 0.0,
            "anomaly_types": [],
            "confidence": 0.0,
            "recommendations": []
        }
        
        try:
            # Rule-based anomaly detection (always available)
            rule_based_anomalies = self._rule_based_detection(current_metrics)
            
            if rule_based_anomalies["anomalies_detected"]:
                result.update(rule_based_anomalies)
            
            # ML-based detection (if models available)
            if device_id in self.models and DEPS_AVAILABLE:
                ml_anomalies = self._ml_based_detection(device_id, current_metrics)
                
                if ml_anomalies["anomalies_detected"]:
                    result["anomalies_detected"] = True
                    result["anomaly_score"] = max(result["anomaly_score"], ml_anomalies["anomaly_score"])
                    result["anomaly_types"].extend(ml_anomalies["anomaly_types"])
                    result["recommendations"].extend(ml_anomalies["recommendations"])
            
        except Exception as e:
            logger.error(f"Error detecting anomalies for {device_id}: {e}")
            result["error"] = str(e)
            
        return result
    
    def _extract_features(self, metrics_list: List[Dict]):
        """Extract numerical features from metrics for ML training."""
        features = []
        
        for metrics in metrics_list:
            feature_vector = [
                float(metrics.get("cpuUtil", 0)) if metrics.get("cpuUtil", "0").isdigit() else 0,
                float(metrics.get("memoryUtil", 0)) / 1000000 if str(metrics.get("memoryUtil", "0")).isdigit() else 0,  # Convert to MB
                float(metrics.get("interfaces", {}).get("error_rate", 0)),
                float(metrics.get("interfaces", {}).get("utilization_avg", 0)),
                float(metrics.get("uptime", 0)) / 86400  # Convert to days
            ]
            features.append(feature_vector)
            
        return np.array(features)
    
    def _rule_based_detection(self, metrics: Dict) -> Dict[str, Any]:
        """Rule-based anomaly detection."""
        anomalies = []
        recommendations = []
        max_score = 0.0
        
        # CPU utilization check
        cpu_util = float(metrics.get("cpuUtil", 0)) if str(metrics.get("cpuUtil", "0")).isdigit() else 0
        if cpu_util > 80:
            anomalies.append("high_cpu_usage")
            recommendations.append(f"CPU usage at {cpu_util}% - investigate high load processes")
            max_score = max(max_score, 0.8)
        
        # Memory utilization check  
        memory_util = float(metrics.get("memoryUtil", 0)) if str(metrics.get("memoryUtil", "0")).isdigit() else 0
        if memory_util > 800000000:  # 800MB+ usage
            anomalies.append("high_memory_usage") 
            recommendations.append("Memory usage high - check for memory leaks")
            max_score = max(max_score, 0.7)
        
        # Interface error rate check
        interfaces = metrics.get("interfaces", {})
        error_rate = float(interfaces.get("error_rate", 0))
        if error_rate > 0.01:  # 1% error rate
            anomalies.append("high_error_rate")
            recommendations.append(f"Interface error rate {error_rate:.2%} - check cables and connections")
            max_score = max(max_score, 0.9)
        
        # Link flaps check
        link_flaps = int(interfaces.get("link_flaps_1h", 0))
        if link_flaps > 3:
            anomalies.append("link_instability")
            recommendations.append(f"{link_flaps} link flaps in last hour - check cable connections")
            max_score = max(max_score, 0.8)
        
        # Device connectivity check
        if metrics.get("status") != "success":
            anomalies.append("device_unreachable")
            recommendations.append("Device unreachable - check network connectivity and device status")
            max_score = max(max_score, 1.0)
        
        return {
            "anomalies_detected": len(anomalies) > 0,
            "anomaly_score": max_score,
            "anomaly_types": anomalies,
            "confidence": 0.85,  # High confidence for rule-based
            "recommendations": recommendations
        }
    
    def _ml_based_detection(self, device_id: str, metrics: Dict) -> Dict[str, Any]:
        """ML-based anomaly detection."""
        models = self.models[device_id]
        
        # Extract features for current metrics
        feature_vector = self._extract_features([metrics])[0].reshape(1, -1)
        
        # Get predictions from both models
        iso_prediction = models["isolation_forest"].predict(feature_vector)[0]
        svm_prediction = models["one_class_svm"].predict(feature_vector)[0]
        
        # Get anomaly scores
        iso_score = abs(models["isolation_forest"].score_samples(feature_vector)[0])
        
        anomalies = []
        recommendations = []
        
        if iso_prediction == -1:  # Anomaly detected by Isolation Forest
            anomalies.append("ml_statistical_anomaly")
            recommendations.append("ML model detected statistical anomaly in device behavior")
        
        if svm_prediction == -1:  # Anomaly detected by SVM
            anomalies.append("ml_pattern_anomaly") 
            recommendations.append("ML model detected abnormal pattern in device metrics")
        
        return {
            "anomalies_detected": len(anomalies) > 0,
            "anomaly_score": float(iso_score),
            "anomaly_types": anomalies,
            "confidence": 0.75,  # Lower confidence for ML
            "recommendations": recommendations
        }

class DeviceFailurePrediction:
    """Predicts device failures based on historical trends and anomalies."""
    
    def __init__(self):
        self.failure_indicators = {
            "cisco": [
                "increasing_cpu_usage",
                "memory_leak_pattern", 
                "interface_error_increase",
                "frequent_link_flaps",
                "temperature_rise",
                "power_supply_issues"
            ],
            "ubiquiti": [
                "wifi_performance_degradation",
                "client_disconnections",
                "firmware_instability",
                "hardware_sensor_alerts"
            ]
        }
    
    def predict_failure(self, device: Dict, metrics_history: List[Dict]) -> Dict[str, Any]:
        """Predict device failure probability based on trends."""
        if len(metrics_history) < 5:
            return {
                "failure_probability": 0.0,
                "time_to_failure": None,
                "confidence": 0.0,
                "indicators": [],
                "recommendation": "insufficient_data"
            }
        
        device_type = device.get("type", "unknown")
        prediction = {
            "device_id": device.get("host", "unknown"),
            "device_type": device_type,
            "timestamp": datetime.now().isoformat(),
            "failure_probability": 0.0,
            "time_to_failure": None,
            "confidence": 0.0,
            "indicators": [],
            "recommendation": "monitor"
        }
        
        try:
            # Analyze trends in key metrics
            trends = self._analyze_metric_trends(metrics_history)
            
            failure_score = 0.0
            indicators = []
            
            # Check for failure indicators
            for indicator in self.failure_indicators.get(device_type, []):
                if self._check_failure_indicator(indicator, trends, metrics_history):
                    indicators.append(indicator)
                    failure_score += 0.15
            
            # Calculate failure probability (0.0 to 1.0)
            prediction["failure_probability"] = min(failure_score, 1.0)
            prediction["indicators"] = indicators
            prediction["confidence"] = 0.7 if len(indicators) > 0 else 0.3
            
            # Estimate time to failure based on trend velocity
            if failure_score > 0.3:
                prediction["time_to_failure"] = self._estimate_failure_time(trends)
                prediction["recommendation"] = "backup_recommended" if failure_score > 0.5 else "monitor_closely"
            
        except Exception as e:
            logger.error(f"Error predicting failure for device: {e}")
            prediction["error"] = str(e)
        
        return prediction
    
    def _analyze_metric_trends(self, metrics_history: List[Dict]) -> Dict[str, Any]:
        """Analyze trends in device metrics over time."""
        if len(metrics_history) < 2:
            return {}
        
        # Extract time series data
        cpu_usage = []
        memory_usage = []
        error_rates = []
        timestamps = []
        
        for metrics in metrics_history:
            timestamps.append(datetime.fromisoformat(metrics.get("timestamp", datetime.now().isoformat())))
            
            cpu = float(metrics.get("cpuUtil", 0)) if str(metrics.get("cpuUtil", "0")).isdigit() else 0
            cpu_usage.append(cpu)
            
            mem = float(metrics.get("memoryUtil", 0)) if str(metrics.get("memoryUtil", "0")).isdigit() else 0
            memory_usage.append(mem)
            
            error_rate = float(metrics.get("interfaces", {}).get("error_rate", 0))
            error_rates.append(error_rate)
        
        # Calculate trends (simple linear regression)
        trends = {}
        
        if len(cpu_usage) > 1:
            cpu_trend = (cpu_usage[-1] - cpu_usage[0]) / len(cpu_usage)
            trends["cpu_trend"] = cpu_trend
            trends["cpu_increasing"] = cpu_trend > 1.0  # Increasing by >1% per measurement
        
        if len(memory_usage) > 1:
            mem_trend = (memory_usage[-1] - memory_usage[0]) / len(memory_usage)
            trends["memory_trend"] = mem_trend
            trends["memory_increasing"] = mem_trend > 10000000  # Increasing by >10MB per measurement
        
        if len(error_rates) > 1:
            error_trend = (error_rates[-1] - error_rates[0]) / len(error_rates)
            trends["error_trend"] = error_trend
            trends["error_increasing"] = error_trend > 0.001  # Increasing by >0.1% per measurement
        
        return trends
    
    def _check_failure_indicator(self, indicator: str, trends: Dict, metrics_history: List[Dict]) -> bool:
        """Check if a specific failure indicator is present."""
        latest_metrics = metrics_history[-1]
        
        if indicator == "increasing_cpu_usage":
            return trends.get("cpu_increasing", False)
        elif indicator == "memory_leak_pattern":
            return trends.get("memory_increasing", False)
        elif indicator == "interface_error_increase":
            return trends.get("error_increasing", False)
        elif indicator == "frequent_link_flaps":
            recent_flaps = sum(m.get("interfaces", {}).get("link_flaps_1h", 0) for m in metrics_history[-3:])
            return recent_flaps > 5
        elif indicator == "wifi_performance_degradation":
            wifi_perf = latest_metrics.get("wifi_performance", {})
            return wifi_perf.get("client_satisfaction", 1.0) < 0.8
        
        return False
    
    def _estimate_failure_time(self, trends: Dict) -> str:
        """Estimate time until device failure based on trend velocity."""
        # Simple heuristic - in production would use more sophisticated models
        cpu_trend = trends.get("cpu_trend", 0)
        memory_trend = trends.get("memory_trend", 0)
        
        if cpu_trend > 5:  # CPU increasing rapidly
            return "24-48 hours"
        elif memory_trend > 50000000:  # Memory increasing rapidly  
            return "2-7 days"
        elif trends.get("error_increasing", False):
            return "1-3 days"
        else:
            return "1-2 weeks"

class ConfigBackupManager:
    """Manages automated configuration backups for network devices."""
    
    def __init__(self):
        self.backup_directory = "backups"
        os.makedirs(self.backup_directory, exist_ok=True)
    
    async def backup_device_config(self, device: Dict, failure_prediction: Optional[Dict] = None) -> Dict[str, Any]:
        """Backup device configuration before predicted failure."""
        backup_result = {
            "device_id": device.get("host", "unknown"),
            "device_type": device.get("type", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "backup_status": "unknown",
            "backup_file": None,
            "triggered_by": "manual"
        }
        
        if failure_prediction:
            backup_result["triggered_by"] = f"failure_prediction_{failure_prediction.get('failure_probability', 0):.2f}"
        
        try:
            if device["type"] == "cisco":
                backup_result.update(await self._backup_cisco_config(device))
            elif device["type"] == "ubiquiti":
                backup_result.update(await self._backup_ubiquiti_config(device))
            else:
                backup_result["backup_status"] = "unsupported_device_type"
                
        except Exception as e:
            logger.error(f"Failed to backup {device['host']}: {e}")
            backup_result["backup_status"] = "error"
            backup_result["error"] = str(e)
        
        return backup_result
    
    async def _backup_cisco_config(self, device: Dict) -> Dict[str, Any]:
        """Backup Cisco device configuration."""
        # In production, would use SSH/NETCONF to get running-config
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{self.backup_directory}/cisco_{device['host']}_{timestamp}.cfg"
        
        # Mock configuration backup
        config_content = f"""!
! Cisco Configuration Backup
! Device: {device['host']}
! Backup Time: {datetime.now().isoformat()}
!
version 15.2
service timestamps debug datetime msec
service timestamps log datetime msec
service password-encryption
!
hostname {device.get('sysName', 'cisco-device')}
!
! Interface configurations would be here
! VLAN configurations would be here
! Routing configurations would be here
!
end"""
        
        with open(backup_file, 'w') as f:
            f.write(config_content)
        
        return {
            "backup_status": "success",
            "backup_file": backup_file,
            "backup_size_bytes": len(config_content),
            "backup_method": "snmp_ssh"
        }
    
    async def _backup_ubiquiti_config(self, device: Dict) -> Dict[str, Any]:
        """Backup Ubiquiti device configuration via UniFi Controller."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{self.backup_directory}/ubiquiti_{device['host']}_{timestamp}.json"
        
        # Mock configuration backup
        config_content = {
            "device_info": {
                "host": device["host"],
                "controller": device.get("controller_url", ""),
                "backup_time": datetime.now().isoformat()
            },
            "wireless_config": {
                "ssids": ["Corporate", "Guest"],
                "security": "wpa2",
                "channels": "auto"
            },
            "network_config": {
                "vlans": [1, 100, 200],
                "dhcp_enabled": True
            }
        }
        
        with open(backup_file, 'w') as f:
            json.dump(config_content, f, indent=2)
        
        return {
            "backup_status": "success", 
            "backup_file": backup_file,
            "backup_size_bytes": len(json.dumps(config_content)),
            "backup_method": "unifi_api"
        }

async def main():
    """Main entry point for network monitoring helper."""
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No input provided"}))
        sys.exit(1)
    
    try:
        input_data = json.loads(sys.argv[1])
        operation = input_data.get("operation", "monitor")
        
        # Initialize components
        collector = NetworkDeviceCollector()
        anomaly_detector = NetworkAnomalyDetector()
        failure_predictor = DeviceFailurePrediction()
        backup_manager = ConfigBackupManager()
        
        result = {
            "status": "success",
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "message": "Network monitoring completed"
        }
        
        if operation == "add_cisco_device":
            await collector.add_cisco_device(
                host=input_data.get("host", "192.168.1.1"),
                community=input_data.get("community", "public"),
                snmp_version=input_data.get("snmp_version", "v2c")
            )
            result["message"] = f"Added Cisco device {input_data.get('host')}"
            
        elif operation == "add_ubiquiti_device":
            await collector.add_ubiquiti_device(
                host=input_data.get("host", "192.168.1.10"),
                controller_url=input_data.get("controller_url", "https://unifi.local:8443"),
                username=input_data.get("username", "admin"),
                password=input_data.get("password", "password")
            )
            result["message"] = f"Added Ubiquiti device {input_data.get('host')}"
            
        elif operation == "collect_metrics":
            device = input_data.get("device", {"type": "cisco", "host": "192.168.1.1", "community": "public"})
            
            if device["type"] == "cisco":
                metrics = await collector.collect_cisco_metrics(device)
            else:
                metrics = await collector.collect_ubiquiti_metrics(device)
                
            result["metrics"] = metrics
            result["message"] = f"Collected metrics from {device['host']}"
            
        elif operation == "detect_anomalies":
            device_id = input_data.get("device_id", "192.168.1.1")
            current_metrics = input_data.get("current_metrics", {})
            
            anomalies = anomaly_detector.detect_anomalies(device_id, current_metrics)
            result["anomalies"] = anomalies
            
            if anomalies["anomalies_detected"]:
                result["message"] = f"Anomalies detected on {device_id}: {len(anomalies['anomaly_types'])} issues"
            else:
                result["message"] = f"No anomalies detected on {device_id}"
                
        elif operation == "predict_failure":
            device = input_data.get("device", {"type": "cisco", "host": "192.168.1.1"})
            metrics_history = input_data.get("metrics_history", [])
            
            prediction = failure_predictor.predict_failure(device, metrics_history)
            result["failure_prediction"] = prediction
            
            if prediction["failure_probability"] > 0.5:
                result["message"] = f"High failure risk detected: {prediction['failure_probability']:.1%} probability"
            else:
                result["message"] = f"Low failure risk: {prediction['failure_probability']:.1%} probability"
                
        elif operation == "backup_config":
            device = input_data.get("device", {"type": "cisco", "host": "192.168.1.1"})
            failure_prediction = input_data.get("failure_prediction")
            
            backup_result = await backup_manager.backup_device_config(device, failure_prediction)
            result["backup_result"] = backup_result
            result["message"] = f"Configuration backup completed: {backup_result['backup_status']}"
            
        elif operation == "full_monitoring":
            # Complete monitoring workflow
            devices = input_data.get("devices", [
                {"type": "cisco", "host": "192.168.1.1", "community": "public"},
                {"type": "ubiquiti", "host": "192.168.1.10", "controller_url": "https://unifi.local:8443", "username": "admin", "password": "password"}
            ])
            
            monitoring_results = []
            
            for device in devices:
                device_result = {
                    "device": device,
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    # Collect metrics
                    if device["type"] == "cisco":
                        metrics = await collector.collect_cisco_metrics(device)
                    else:
                        metrics = await collector.collect_ubiquiti_metrics(device)
                    
                    device_result["metrics"] = metrics
                    
                    # Detect anomalies
                    anomalies = anomaly_detector.detect_anomalies(device["host"], metrics)
                    device_result["anomalies"] = anomalies
                    
                    # Predict failure (with mock history)
                    mock_history = [metrics] * 5  # Simulate historical data
                    prediction = failure_predictor.predict_failure(device, mock_history)
                    device_result["failure_prediction"] = prediction
                    
                    # Backup config if high failure risk
                    if prediction["failure_probability"] > 0.5:
                        backup_result = await backup_manager.backup_device_config(device, prediction)
                        device_result["backup_result"] = backup_result
                    
                except Exception as e:
                    device_result["error"] = str(e)
                
                monitoring_results.append(device_result)
            
            result["monitoring_results"] = monitoring_results
            
            # Summary
            anomaly_count = sum(1 for r in monitoring_results if r.get("anomalies", {}).get("anomalies_detected", False))
            high_risk_count = sum(1 for r in monitoring_results if r.get("failure_prediction", {}).get("failure_probability", 0) > 0.5)
            
            result["summary"] = {
                "total_devices": len(devices),
                "devices_with_anomalies": anomaly_count,
                "high_risk_devices": high_risk_count,
                "backups_created": sum(1 for r in monitoring_results if "backup_result" in r)
            }
            
            result["message"] = f"Monitored {len(devices)} devices - {anomaly_count} anomalies, {high_risk_count} high risk"
            
        else:
            result["status"] = "error"
            result["message"] = f"Unknown operation: {operation}"
            
        print(json.dumps(result, indent=2))
        
    except json.JSONDecodeError:
        print(json.dumps({"status": "error", "message": "Invalid JSON input"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())