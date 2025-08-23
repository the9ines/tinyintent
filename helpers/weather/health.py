#!/usr/bin/env python3
"""
Weather Helper Health Check

Tests the weather helper's ability to connect to APIs and retrieve data.
"""

import json
import sys
import urllib.request
from typing import Dict, Any


def check_health() -> Dict[str, Any]:
    """
    Perform health check on weather helper.
    
    Returns:
        Health check results
    """
    results = {
        "status": "healthy",
        "checks": {},
        "timestamp": None
    }
    
    # Test 1: Open-Meteo Geocoding API
    geocoding_status = _test_geocoding()
    results["checks"]["geocoding"] = geocoding_status
    
    # Test 2: Open-Meteo Weather API  
    weather_status = _test_weather_api()
    results["checks"]["weather_api"] = weather_status
    
    # Test 3: Full integration test
    integration_status = _test_integration()
    results["checks"]["integration"] = integration_status
    
    # Determine overall health
    all_healthy = all(
        check.get("status") == "healthy" 
        for check in results["checks"].values()
    )
    
    if not all_healthy:
        results["status"] = "degraded"
        
        # Check if any critical failures
        critical_failures = [
            check for check in results["checks"].values()
            if check.get("status") == "error"
        ]
        
        if critical_failures:
            results["status"] = "unhealthy"
    
    return results


def _test_geocoding() -> Dict[str, Any]:
    """Test geocoding API connectivity."""
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search?name=Austin&count=1&format=json"
        
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
        
        if data.get('results') and len(data['results']) > 0:
            return {
                "status": "healthy",
                "message": "Geocoding API accessible",
                "response_time_ms": None  # Could add timing
            }
        else:
            return {
                "status": "degraded", 
                "message": "Geocoding API returned no results"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Geocoding API failed: {str(e)}"
        }


def _test_weather_api() -> Dict[str, Any]:
    """Test weather API connectivity."""
    try:
        # Test with Austin coordinates
        url = "https://api.open-meteo.com/v1/forecast?latitude=30.27&longitude=-97.74&current=temperature_2m"
        
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
        
        if 'current' in data and 'temperature_2m' in data['current']:
            temp = data['current']['temperature_2m']
            return {
                "status": "healthy",
                "message": f"Weather API accessible (sample temp: {temp}°C)",
                "sample_data": {"temperature": temp}
            }
        else:
            return {
                "status": "degraded",
                "message": "Weather API returned incomplete data"
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Weather API failed: {str(e)}"
        }


def _test_integration() -> Dict[str, Any]:
    """Test full weather helper integration."""
    try:
        # Import and test the main weather helper
        sys.path.insert(0, '/Users/oberfelder/Projects/tinyintent/helpers/weather')
        from main import WeatherHelper
        
        weather_helper = WeatherHelper()
        result = weather_helper.get_weather("Austin, TX", "imperial", False)
        
        if result.get("status") == "success":
            current = result.get("current", {})
            temp = current.get("temperature")
            location = result.get("location", "Unknown")
            
            return {
                "status": "healthy",
                "message": f"Full integration working ({temp}°F in {location})",
                "sample_result": {
                    "location": location,
                    "temperature": temp,
                    "description": current.get("description")
                }
            }
        else:
            return {
                "status": "error",
                "message": f"Integration test failed: {result.get('error_message', 'Unknown error')}"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Integration test error: {str(e)}"
        }


def main():
    """Main health check entry point."""
    try:
        health_results = check_health()
        print(json.dumps(health_results, indent=2))
        
        # Exit with appropriate code
        sys.exit(0 if health_results["status"] in ["healthy", "degraded"] else 1)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "message": f"Health check failed: {str(e)}"
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()