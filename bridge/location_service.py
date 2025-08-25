#!/usr/bin/env python3
"""
M12.0: TinyIntent Location Service

Provides modular location awareness for all helpers and agents.
Supports GPS coordinates, address resolution, and location context enrichment.
"""

import json
import re
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class LocationContext:
    """Standardized location context object for TinyIntent helpers."""
    
    # Core location data
    latitude: float
    longitude: float
    accuracy: Optional[float] = None  # GPS accuracy in meters
    
    # Resolved location information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    
    # Source and metadata
    source: str = "unknown"  # gps, address, ip, default
    resolved_at: Optional[str] = None
    confidence: float = 1.0  # Confidence in location accuracy (0.0-1.0)
    
    # Additional context
    timezone: Optional[str] = None
    elevation: Optional[float] = None
    
    def __post_init__(self):
        """Set resolved timestamp."""
        if not self.resolved_at:
            self.resolved_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for helper input, excluding None values."""
        result = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "resolved_at": self.resolved_at,
            "confidence": self.confidence
        }
        
        # Only include non-None values
        if self.accuracy is not None:
            result["accuracy"] = self.accuracy
        if self.address is not None:
            result["address"] = self.address
        if self.city is not None:
            result["city"] = self.city
        if self.state is not None:
            result["state"] = self.state
        if self.country is not None:
            result["country"] = self.country
        if self.postal_code is not None:
            result["postal_code"] = self.postal_code
        if self.timezone is not None:
            result["timezone"] = self.timezone
        if self.elevation is not None:
            result["elevation"] = self.elevation
            
        return result
    
    def coordinates_string(self) -> str:
        """Get coordinates as comma-separated string."""
        return f"{self.latitude},{self.longitude}"
    
    def is_accurate(self) -> bool:
        """Check if location is accurate enough for precise operations."""
        if self.source == "gps" and self.accuracy and self.accuracy <= 50:
            return True  # GPS within 50 meters
        elif self.source == "address" and self.confidence >= 0.8:
            return True  # High confidence address resolution
        return False
    
    def display_name(self) -> str:
        """Get human-readable location name."""
        if self.address:
            return self.address
        elif self.city and self.state:
            return f"{self.city}, {self.state}"
        elif self.city:
            return self.city
        else:
            return f"{self.latitude:.4f}, {self.longitude:.4f}"


class LocationService:
    """Centralized location service for TinyIntent."""
    
    def __init__(self):
        """Initialize location service with geocoding APIs."""
        # Free geocoding APIs (no keys required)
        self.open_meteo_geocoding = "https://geocoding-api.open-meteo.com/v1/search"
        self.nominatim_api = "https://nominatim.openstreetmap.org/search"
        self.nominatim_reverse = "https://nominatim.openstreetmap.org/reverse"
        
        # Default location fallback (Austin, TX)
        self.default_location = LocationContext(
            latitude=30.2672,
            longitude=-97.7431,
            address="Austin, Texas, United States",
            city="Austin",
            state="Texas", 
            country="United States",
            postal_code="78701",
            source="default",
            confidence=0.5
        )
    
    def create_location_context(self, 
                               latitude: Optional[float] = None,
                               longitude: Optional[float] = None,
                               accuracy: Optional[float] = None,
                               address: Optional[str] = None,
                               source: str = "unknown") -> LocationContext:
        """
        Create location context from available information.
        
        Args:
            latitude: GPS latitude
            longitude: GPS longitude  
            accuracy: GPS accuracy in meters
            address: Text address/location
            source: Source of location data
            
        Returns:
            LocationContext object with resolved information
        """
        try:
            # GPS coordinates provided
            if latitude is not None and longitude is not None:
                if self._validate_coordinates(latitude, longitude):
                    context = LocationContext(
                        latitude=latitude,
                        longitude=longitude,
                        accuracy=accuracy,
                        source=source if source != "unknown" else "gps",
                        confidence=1.0 if accuracy and accuracy <= 10 else 0.9
                    )
                    
                    # Try to reverse geocode to get address
                    self._enrich_location_context(context)
                    return context
                else:
                    logger.warning(f"Invalid GPS coordinates: {latitude}, {longitude}")
            
            # Address/text location provided
            elif address:
                context = self._geocode_address(address)
                if context:
                    context.source = source if source != "unknown" else "address"
                    return context
                else:
                    logger.warning(f"Could not geocode address: {address}")
            
            # Fallback to default location
            logger.info("Using default location (Austin, TX)")
            return self.default_location
            
        except Exception as e:
            logger.error(f"Location context creation failed: {e}")
            return self.default_location
    
    def _validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """Validate GPS coordinates."""
        return (-90 <= latitude <= 90) and (-180 <= longitude <= 180)
    
    def _geocode_address(self, address: str) -> Optional[LocationContext]:
        """Geocode text address to coordinates."""
        # Try Open-Meteo first
        result = self._geocode_open_meteo(address)
        if result:
            return result
        
        # Fallback to Nominatim
        result = self._geocode_nominatim(address)
        if result:
            return result
        
        return None
    
    def _geocode_open_meteo(self, address: str) -> Optional[LocationContext]:
        """Geocode using Open-Meteo API."""
        try:
            params = urllib.parse.urlencode({
                'name': address,
                'count': 1,
                'language': 'en',
                'format': 'json'
            })
            
            url = f"{self.open_meteo_geocoding}?{params}"
            
            with urllib.request.urlopen(url, timeout=8) as response:
                data = json.loads(response.read().decode())
            
            if data.get('results') and len(data['results']) > 0:
                result = data['results'][0]
                
                # Extract location components
                city = result.get('name', '')
                admin1 = result.get('admin1', '')  # State/Province
                country = result.get('country', '')
                
                # Build display address
                address_parts = [city, admin1, country]
                display_address = ", ".join(p for p in address_parts if p)
                
                return LocationContext(
                    latitude=result['latitude'],
                    longitude=result['longitude'],
                    address=display_address,
                    city=city,
                    state=admin1,
                    country=country,
                    source="address",
                    confidence=0.8
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Open-Meteo geocoding failed: {e}")
            return None
    
    def _geocode_nominatim(self, address: str) -> Optional[LocationContext]:
        """Geocode using Nominatim API."""
        try:
            params = urllib.parse.urlencode({
                'q': address,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            })
            
            url = f"{self.nominatim_api}?{params}"
            req = urllib.request.Request(url, headers={'User-Agent': 'TinyIntent-LocationService/1.0'})
            
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode())
            
            if data and len(data) > 0:
                result = data[0]
                address_details = result.get('address', {})
                
                return LocationContext(
                    latitude=float(result['lat']),
                    longitude=float(result['lon']),
                    address=result.get('display_name', address),
                    city=address_details.get('city') or address_details.get('town') or address_details.get('village'),
                    state=address_details.get('state'),
                    country=address_details.get('country'),
                    postal_code=address_details.get('postcode'),
                    source="address",
                    confidence=0.7
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Nominatim geocoding failed: {e}")
            return None
    
    def _enrich_location_context(self, context: LocationContext) -> None:
        """Enrich location context with reverse geocoding."""
        try:
            address_info = self._reverse_geocode(context.latitude, context.longitude)
            if address_info:
                context.address = address_info.get('address', context.address)
                context.city = address_info.get('city', context.city)
                context.state = address_info.get('state', context.state)
                context.country = address_info.get('country', context.country)
                context.postal_code = address_info.get('postal_code', context.postal_code)
                
        except Exception as e:
            logger.debug(f"Location enrichment failed: {e}")
    
    def _reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, str]]:
        """Reverse geocode coordinates to address."""
        try:
            params = urllib.parse.urlencode({
                'lat': latitude,
                'lon': longitude,
                'format': 'json',
                'addressdetails': 1,
                'zoom': 14
            })
            
            url = f"{self.nominatim_reverse}?{params}"
            req = urllib.request.Request(url, headers={'User-Agent': 'TinyIntent-LocationService/1.0'})
            
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode())
            
            if 'address' in data:
                address_details = data['address']
                return {
                    'address': data.get('display_name', ''),
                    'city': address_details.get('city') or address_details.get('town') or address_details.get('village'),
                    'state': address_details.get('state'),
                    'country': address_details.get('country'),
                    'postal_code': address_details.get('postcode')
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Reverse geocoding failed: {e}")
            return None
    
    def find_nearby_locations(self, context: LocationContext, query: str, radius_km: float = 10) -> List[Dict[str, Any]]:
        """
        Find nearby locations/places of interest.
        
        Args:
            context: Location context to search around
            query: Search query (e.g., "restaurants", "gas stations", "hospitals")
            radius_km: Search radius in kilometers
            
        Returns:
            List of nearby locations
        """
        try:
            # Use Nominatim for nearby search
            params = urllib.parse.urlencode({
                'q': query,
                'format': 'json',
                'limit': 10,
                'addressdetails': 1,
                'bounded': 1,
                'viewbox': self._get_bounding_box(context.latitude, context.longitude, radius_km)
            })
            
            url = f"{self.nominatim_api}?{params}"
            req = urllib.request.Request(url, headers={'User-Agent': 'TinyIntent-LocationService/1.0'})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            nearby_locations = []
            for item in data:
                try:
                    lat = float(item['lat'])
                    lon = float(item['lon'])
                    distance = self._calculate_distance(context.latitude, context.longitude, lat, lon)
                    
                    if distance <= radius_km:
                        nearby_locations.append({
                            'name': item.get('display_name', 'Unknown'),
                            'latitude': lat,
                            'longitude': lon,
                            'distance_km': round(distance, 2),
                            'type': item.get('type', 'unknown'),
                            'address': item.get('display_name', '')
                        })
                except ValueError:
                    continue
            
            # Sort by distance
            nearby_locations.sort(key=lambda x: x['distance_km'])
            return nearby_locations
            
        except Exception as e:
            logger.error(f"Nearby location search failed: {e}")
            return []
    
    def _get_bounding_box(self, lat: float, lon: float, radius_km: float) -> str:
        """Get bounding box for search area."""
        # Rough conversion: 1 degree ≈ 111 km
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * abs(lat) / 90.0 + 1)  # Adjust for latitude
        
        min_lon = lon - lon_delta
        min_lat = lat - lat_delta
        max_lon = lon + lon_delta
        max_lat = lat + lat_delta
        
        return f"{min_lon},{min_lat},{max_lon},{max_lat}"
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        import math
        
        R = 6371  # Earth radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def get_location_for_helper(self, helper_id: str, context: LocationContext) -> Dict[str, Any]:
        """
        Get location information formatted for specific helper types.
        
        Args:
            helper_id: ID of the helper requesting location
            context: Location context
            
        Returns:
            Helper-specific location information
        """
        base_info = {
            "location_context": context.to_dict(),
            "coordinates": context.coordinates_string(),
            "display_name": context.display_name(),
            "is_accurate": context.is_accurate()
        }
        
        # Helper-specific formatting
        if helper_id == "weather":
            return {
                **base_info,
                "location": context.coordinates_string() if context.is_accurate() else context.display_name()
            }
        
        elif helper_id == "traffic":
            return {
                **base_info,
                "origin": context.coordinates_string(),
                "location_name": context.display_name()
            }
        
        elif helper_id == "nearby":
            return {
                **base_info,
                "search_center": context.coordinates_string(),
                "search_radius_km": 10 if context.is_accurate() else 25
            }
        
        else:
            # Generic location info for any helper
            return base_info


# Global location service instance
location_service = LocationService()


def create_location_context(**kwargs) -> LocationContext:
    """Convenience function to create location context."""
    return location_service.create_location_context(**kwargs)


def get_location_for_helper(helper_id: str, context: LocationContext) -> Dict[str, Any]:
    """Convenience function to get helper-specific location info."""
    return location_service.get_location_for_helper(helper_id, context)