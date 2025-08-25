#!/usr/bin/env python3
"""
Traffic Helper for TinyIntent

Provides real-time traffic conditions and routing information.
Uses location context from the TinyIntent location service.
Demonstrates modular location awareness for all helpers.
"""

import json
import sys
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List
import time
import random


class TrafficHelper:
    """Traffic information helper with location awareness."""
    
    def __init__(self):
        """Initialize traffic helper with API endpoints."""
        # Free traffic APIs (demonstrations use mock data for reliability)
        self.openroute_api = "https://api.openrouteservice.org/v2/directions/driving-car"
        
        # Traffic level mappings
        self.traffic_levels = {
            "light": "Light traffic - roads are clear",
            "moderate": "Moderate traffic - expect minor delays", 
            "heavy": "Heavy traffic - significant delays expected",
            "severe": "Severe traffic - major delays and congestion"
        }
    
    def get_traffic_info(self, operation: str, destination: str = None, 
                        route_preference: str = "fastest",
                        location_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get traffic information based on operation and location context.
        
        Args:
            operation: Type of traffic operation
            destination: Optional destination for routing
            route_preference: Route preference (fastest, shortest, avoid_highways)
            location_context: Location context from TinyIntent location service
            
        Returns:
            Traffic information dictionary
        """
        try:
            # Extract location information from context
            if not location_context:
                return {
                    "status": "error",
                    "error_message": "Location context is required for traffic information"
                }
            
            current_location = location_context.get("display_name", "Unknown location")
            coordinates = location_context.get("coordinates", "")
            is_accurate = location_context.get("is_accurate", False)
            
            if operation == "current_traffic":
                return self._get_current_traffic(current_location, coordinates, is_accurate)
            
            elif operation == "route_time":
                if not destination:
                    return {
                        "status": "error",
                        "error_message": "Destination is required for route time calculation"
                    }
                return self._get_route_time(current_location, destination, route_preference, 
                                          coordinates, is_accurate)
            
            elif operation == "traffic_incidents":
                return self._get_traffic_incidents(current_location, coordinates, is_accurate)
            
            else:
                return {
                    "status": "error",
                    "error_message": f"Unknown operation: {operation}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Traffic helper error: {str(e)}"
            }
    
    def _get_current_traffic(self, location: str, coordinates: str, is_accurate: bool) -> Dict[str, Any]:
        """Get current traffic conditions for the location."""
        try:
            # For demonstration, generate realistic traffic data
            # In production, this would call real traffic APIs
            
            current_hour = time.localtime().tm_hour
            
            # Simulate rush hour traffic patterns
            if 7 <= current_hour <= 9 or 17 <= current_hour <= 19:
                traffic_level = random.choice(["moderate", "heavy", "severe"])
            elif 22 <= current_hour or current_hour <= 6:
                traffic_level = "light"
            else:
                traffic_level = random.choice(["light", "moderate"])
            
            # Generate location-specific message
            accuracy_note = " (GPS location)" if is_accurate else " (approximate location)"
            
            traffic_info = {
                "current_location": location + accuracy_note,
                "traffic_level": traffic_level,
                "travel_time": "Normal conditions",
                "incidents": []
            }
            
            # Add incidents for heavy/severe traffic
            if traffic_level in ["heavy", "severe"]:
                incidents = [
                    "Construction on main roads",
                    "Heavy congestion on highways",
                    "Accident reported nearby"
                ]
                traffic_info["incidents"] = incidents[:random.randint(1, 2)]
            
            message = f"Traffic conditions near {location}: {self.traffic_levels[traffic_level]}"
            if traffic_info["incidents"]:
                message += f". {len(traffic_info['incidents'])} incident(s) reported."
            
            return {
                "status": "success",
                "traffic_info": traffic_info,
                "message": message
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "error_message": f"Failed to get current traffic: {str(e)}"
            }
    
    def _get_route_time(self, origin: str, destination: str, preference: str,
                       coordinates: str, is_accurate: bool) -> Dict[str, Any]:
        """Get estimated travel time to destination."""
        try:
            # For demonstration, generate realistic route data
            # In production, this would call routing APIs like OpenRouteService
            
            # Simulate distance calculation (mock)
            base_distance = random.randint(5, 50)  # miles
            base_time = int(base_distance * 1.5)  # minutes (assuming 40 mph average)
            
            # Adjust for traffic and preference
            current_hour = time.localtime().tm_hour
            traffic_multiplier = 1.0
            
            if 7 <= current_hour <= 9 or 17 <= current_hour <= 19:
                traffic_multiplier = random.uniform(1.3, 2.0)  # Rush hour
            elif preference == "avoid_highways":
                traffic_multiplier = 1.2  # Slower local roads
            elif preference == "shortest":
                base_distance *= 0.9  # Shorter but possibly slower
                traffic_multiplier = 1.1
            
            estimated_time = int(base_time * traffic_multiplier)
            
            # Determine traffic level for route
            if traffic_multiplier > 1.5:
                traffic_level = "heavy"
            elif traffic_multiplier > 1.2:
                traffic_level = "moderate" 
            else:
                traffic_level = "light"
            
            accuracy_note = " (GPS routing)" if is_accurate else " (approximate routing)"
            
            traffic_info = {
                "current_location": origin + accuracy_note,
                "traffic_level": traffic_level,
                "travel_time": f"{estimated_time} minutes",
                "distance": f"{base_distance} miles",
                "route_preference": preference,
                "incidents": []
            }
            
            if traffic_level == "heavy":
                traffic_info["incidents"] = ["Heavy traffic expected on route"]
            
            message = f"Route from {origin} to {destination}: {estimated_time} minutes ({base_distance} miles) with {traffic_level} traffic"
            
            return {
                "status": "success",
                "traffic_info": traffic_info,
                "message": message
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Failed to get route time: {str(e)}"
            }
    
    def _get_traffic_incidents(self, location: str, coordinates: str, is_accurate: bool) -> Dict[str, Any]:
        """Get traffic incidents in the area."""
        try:
            # For demonstration, generate realistic incident data
            # In production, this would call traffic incident APIs
            
            incident_types = [
                "Vehicle breakdown on highway",
                "Construction work causing delays",
                "Traffic accident - lane closure",
                "Road maintenance in progress",
                "Heavy congestion due to events"
            ]
            
            # Randomly generate incidents (0-3)
            num_incidents = random.randint(0, 3)
            incidents = random.sample(incident_types, min(num_incidents, len(incident_types)))
            
            accuracy_note = " (GPS area)" if is_accurate else " (approximate area)"
            
            traffic_info = {
                "current_location": location + accuracy_note,
                "traffic_level": "moderate" if incidents else "light",
                "incidents": incidents
            }
            
            if incidents:
                message = f"Traffic incidents near {location}: {len(incidents)} incident(s) reported. {', '.join(incidents[:2])}"
                if len(incidents) > 2:
                    message += f" and {len(incidents) - 2} more"
            else:
                message = f"No traffic incidents reported near {location}"
            
            return {
                "status": "success",
                "traffic_info": traffic_info,
                "message": message
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Failed to get traffic incidents: {str(e)}"
            }


def main():
    """Main entry point for the traffic helper."""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Extract parameters
        operation = input_data.get('operation', 'current_traffic')
        destination = input_data.get('destination')
        route_preference = input_data.get('route_preference', 'fastest')
        
        # Extract location context (provided by TinyIntent location service)
        location_context = input_data.get('location_context', {})
        
        if not location_context:
            result = {
                "status": "error",
                "error_message": "Location context is required for traffic information"
            }
        else:
            # Create traffic helper and get data
            traffic_helper = TrafficHelper()
            result = traffic_helper.get_traffic_info(
                operation=operation,
                destination=destination,
                route_preference=route_preference,
                location_context=location_context
            )
        
        # Output result
        print(json.dumps(result, indent=2))
        
        # Exit with appropriate code
        sys.exit(0 if result.get('status') == 'success' else 1)
        
    except json.JSONDecodeError:
        error_result = {
            "status": "error",
            "error_message": "Invalid JSON input"
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)
        
    except Exception as e:
        error_result = {
            "status": "error", 
            "error_message": f"Unexpected error: {str(e)}"
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()