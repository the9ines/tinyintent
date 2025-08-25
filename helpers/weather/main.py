#!/usr/bin/env python3
"""
Weather Helper for TinyIntent

Retrieves real weather data using free APIs:
- Open-Meteo Geocoding API for location resolution
- Open-Meteo Weather API for current conditions
- No API keys required
"""

import json
import re
import sys
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Tuple


class WeatherHelper:
    """Weather data retrieval using free APIs."""
    
    def __init__(self):
        """Initialize weather helper with API endpoints."""
        self.geocoding_api = "https://geocoding-api.open-meteo.com/v1/search"
        self.weather_api = "https://api.open-meteo.com/v1/forecast"
        self.nominatim_api = "https://nominatim.openstreetmap.org/search"
        
        # Weather code mappings (WMO codes used by Open-Meteo)
        self.weather_codes = {
            0: "Clear sky",
            1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            56: "Light freezing drizzle", 57: "Dense freezing drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            66: "Light freezing rain", 67: "Heavy freezing rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            85: "Slight snow showers", 86: "Heavy snow showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
        }
    
    def get_weather(self, location: str, units: str = "imperial", include_forecast: bool = False) -> Dict[str, Any]:
        """
        Get weather data for a location.
        
        Args:
            location: ZIP code, city name, or coordinates
            units: "imperial" or "metric"
            include_forecast: Include forecast data
            
        Returns:
            Weather data dictionary
        """
        try:
            # Step 1: Resolve location to coordinates
            coords, location_name = self._resolve_location(location)
            if not coords:
                return {
                    "status": "error",
                    "error_code": "LOCATION_NOT_FOUND",
                    "error_message": f"Could not resolve location: {location}"
                }
            
            lat, lon = coords
            
            # Step 2: Get weather data
            weather_data = self._get_weather_data(lat, lon, units, include_forecast)
            if not weather_data:
                return {
                    "status": "error", 
                    "error_code": "WEATHER_API_ERROR",
                    "error_message": "Failed to retrieve weather data"
                }
            
            # Step 3: Format response
            return self._format_response(weather_data, location_name, coords, units, include_forecast)
            
        except Exception as e:
            return {
                "status": "error",
                "error_code": "UNEXPECTED_ERROR",
                "error_message": f"Weather helper error: {str(e)}"
            }
    
    def _resolve_location(self, location: str) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Resolve location string to coordinates."""
        location = location.strip()
        
        # Check if already coordinates (lat,lon)
        coord_match = re.match(r'^(-?\d+\.?\d*),\s*(-?\d+\.?\d*)$', location)
        if coord_match:
            lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
            return (lat, lon), f"{lat}, {lon}"
        
        # Try Open-Meteo geocoding first
        coords, name = self._geocode_open_meteo(location)
        if coords:
            return coords, name
        
        # Fallback to Nominatim
        coords, name = self._geocode_nominatim(location)
        if coords:
            return coords, name
        
        return None, None
    
    def _geocode_open_meteo(self, location: str) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Geocode using Open-Meteo geocoding API."""
        try:
            params = urllib.parse.urlencode({
                'name': location,
                'count': 1,
                'language': 'en',
                'format': 'json'
            })
            
            url = f"{self.geocoding_api}?{params}"
            
            with urllib.request.urlopen(url, timeout=8) as response:
                data = json.loads(response.read().decode())
            
            if data.get('results') and len(data['results']) > 0:
                result = data['results'][0]
                lat = result['latitude']
                lon = result['longitude']
                name = result.get('name', location)
                
                # Add admin info if available
                country = result.get('country', '')
                admin1 = result.get('admin1', '')
                
                if admin1 and country:
                    name = f"{name}, {admin1}, {country}"
                elif country:
                    name = f"{name}, {country}"
                
                return (lat, lon), name
            
            return None, None
            
        except Exception:
            return None, None
    
    def _geocode_nominatim(self, location: str) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Fallback geocoding using Nominatim."""
        try:
            params = urllib.parse.urlencode({
                'q': location,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            })
            
            url = f"{self.nominatim_api}?{params}"
            
            # Add user agent as required by Nominatim
            req = urllib.request.Request(url, headers={'User-Agent': 'TinyIntent-WeatherHelper/1.0'})
            
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode())
            
            if data and len(data) > 0:
                result = data[0]
                lat = float(result['lat'])
                lon = float(result['lon'])
                name = result.get('display_name', location)
                
                return (lat, lon), name
            
            return None, None
            
        except Exception:
            return None, None
    
    def _get_weather_data(self, lat: float, lon: float, units: str, include_forecast: bool) -> Optional[Dict]:
        """Get weather data from Open-Meteo API."""
        try:
            # Configure parameters based on units
            temperature_unit = "fahrenheit" if units == "imperial" else "celsius"
            wind_speed_unit = "mph" if units == "imperial" else "kmh"
            
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
                'temperature_unit': temperature_unit,
                'wind_speed_unit': wind_speed_unit,
                'timezone': 'auto'
            }
            
            # Add forecast if requested
            if include_forecast:
                params['hourly'] = 'temperature_2m,weather_code'
                params['forecast_days'] = 1  # Next 24 hours
            
            url = f"{self.weather_api}?{urllib.parse.urlencode(params)}"
            
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            return data
            
        except Exception:
            return None
    
    def _format_response(self, weather_data: Dict, location_name: str, coords: Tuple[float, float], 
                        units: str, include_forecast: bool) -> Dict[str, Any]:
        """Format weather data into response."""
        try:
            current_data = weather_data.get('current', {})
            
            # Extract current weather
            temperature = current_data.get('temperature_2m')
            feels_like = current_data.get('apparent_temperature')
            humidity = current_data.get('relative_humidity_2m')
            weather_code = current_data.get('weather_code', 0)
            wind_speed = current_data.get('wind_speed_10m')
            
            # Get weather description
            description = self.weather_codes.get(weather_code, "Unknown conditions")
            
            # Create human-readable message
            temp_unit = "°F" if units == "imperial" else "°C"
            wind_unit = "mph" if units == "imperial" else "km/h"
            
            message_parts = [
                f"Currently {temperature}{temp_unit}"
            ]
            
            if feels_like and abs(feels_like - temperature) > 2:
                message_parts.append(f"feels like {feels_like}{temp_unit}")
            
            message_parts.extend([
                f"and {description.lower()}",
                f"in {location_name}"
            ])
            
            if humidity:
                message_parts.append(f"with {humidity}% humidity")
            
            if wind_speed and wind_speed > 5:  # Only mention if noticeable wind
                message_parts.append(f"and {wind_speed} {wind_unit} winds")
            
            message = " ".join(message_parts)
            
            # Build response
            response = {
                "status": "success",
                "location": location_name,
                "coordinates": {
                    "latitude": coords[0],
                    "longitude": coords[1]
                },
                "current": {
                    "temperature": temperature,
                    "feels_like": feels_like,
                    "humidity": int(humidity) if humidity else None,
                    "description": description,
                    "wind_speed": wind_speed,
                    "units": units
                },
                "message": message,
                "api_source": "Open-Meteo"
            }
            
            # Add forecast if requested
            if include_forecast and 'hourly' in weather_data:
                hourly = weather_data['hourly']
                forecast = []
                
                times = hourly.get('time', [])
                temps = hourly.get('temperature_2m', [])
                codes = hourly.get('weather_code', [])
                
                # Get next 6 hours (every 2 hours)
                for i in range(0, min(12, len(times)), 2):
                    if i < len(temps) and i < len(codes):
                        forecast.append({
                            "time": times[i],
                            "temperature": temps[i],
                            "description": self.weather_codes.get(codes[i], "Unknown")
                        })
                
                response["forecast"] = forecast
            
            return response
            
        except Exception as e:
            return {
                "status": "error",
                "error_code": "FORMATTING_ERROR", 
                "error_message": f"Failed to format weather data: {str(e)}"
            }


def main():
    """Main entry point for the weather helper."""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Extract parameters
        location = input_data.get('location', '')
        units = input_data.get('units', 'imperial')
        include_forecast = input_data.get('include_forecast', False)
        
        # Check for location from location context (provided by TinyIntent location service)
        if not location and 'coordinates' in input_data:
            location = input_data['coordinates']
        elif not location and 'location_context' in input_data:
            # Use coordinates from location context if available
            location_ctx = input_data['location_context']
            if 'latitude' in location_ctx and 'longitude' in location_ctx:
                location = f"{location_ctx['latitude']},{location_ctx['longitude']}"
        
        if not location:
            result = {
                "status": "error",
                "error_code": "MISSING_LOCATION",
                "error_message": "Location is required (provide location parameter or location context)"
            }
        else:
            # Create weather helper and get data
            weather_helper = WeatherHelper()
            result = weather_helper.get_weather(location, units, include_forecast)
        
        # Output result
        print(json.dumps(result, indent=2))
        
        # Exit with appropriate code
        sys.exit(0 if result.get('status') == 'success' else 1)
        
    except json.JSONDecodeError:
        error_result = {
            "status": "error",
            "error_code": "INVALID_JSON",
            "error_message": "Invalid JSON input"
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error_code": "UNEXPECTED_ERROR",
            "error_message": f"Unexpected error: {str(e)}"
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()