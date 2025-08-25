# ⚡ Weather Helper - Setup & Troubleshooting

The TinyIntent weather helper provides real-time weather data using free APIs. This guide covers setup, troubleshooting, and usage.

## 🚀 Quick Start

### 1. Enable Helper Execution

**REQUIRED**: TinyIntent must be started with execution enabled:

```bash
# Method 1: Environment variable
export TINYINTENT_EXECUTION_ENABLED=1
tinyintent

# Method 2: Inline
TINYINTENT_EXECUTION_ENABLED=1 tinyintent

# Method 3: Add to your shell profile
echo 'export TINYINTENT_EXECUTION_ENABLED=1' >> ~/.zshrc
source ~/.zshrc
tinyintent
```

### 2. Test Weather Functionality

Once TinyIntent is running with execution enabled:

```bash
# Test via iPhone Shortcut:
"What's the weather in 78624?"
"What's the weather like?"
"What are the current conditions?"

# Should return real weather data like:
# "Currently 90°F feels like 86°F and mainly clear in Fredericksburg, Texas"
```

## 🌍 Location Support

### GPS Coordinates (Most Accurate)
- Configure iPhone Shortcut to send GPS coordinates
- Provides precise weather for your exact location
- See `docs/iPhone_Location_Setup.md` for configuration

### ZIP Codes
- Works with US ZIP codes: `"weather in 78624"`
- Automatically resolved to city coordinates

### City Names
- Supports city names: `"weather in Austin Texas"`
- International cities: `"weather in London UK"`

### Current Location Fallback
- Without GPS: Uses default location (Austin, TX)
- With GPS: Uses your exact coordinates

## 🔍 Troubleshooting

### ❌ "Generic LLM response instead of weather data"

**Problem**: TinyIntent gives generic responses like "I'd be happy to help with weather information..."

**Solution**: Start TinyIntent with execution enabled:
```bash
TINYINTENT_EXECUTION_ENABLED=1 tinyintent
```

**Why**: The weather helper requires execution permission to call weather APIs.

### ❌ "Couldn't give me current location"

**Problem**: Weather requests fail when asking for "current location"

**Solutions**:
1. **Add GPS to iPhone Shortcut**: Follow `docs/iPhone_Location_Setup.md`
2. **Use specific location**: `"weather in [your city]"` or `"weather in [your ZIP]"`
3. **Check default location**: Without GPS, uses Austin, TX as fallback

### ❌ "Weather helper not found" or "execution failed"

**Problem**: Helper execution errors

**Check**:
```bash
# 1. Verify helper is registered
ls helpers/weather/
# Should contain: main.py, helper.yaml, input.schema.json, output.schema.json, provenance.json

# 2. Check registry
grep -A 10 "weather:" helpers/registry.yaml
# Should show: enabled: true, can_execute: true

# 3. Test directly
TINYINTENT_SECRET=test TINYINTENT_EXECUTION_ENABLED=1 python3 -c "
from helpers.executor import HelperExecutor
from helpers.registry import HelperRegistry
executor = HelperExecutor(HelperRegistry())
result = executor.execute('weather', {'location': '78624', 'operation': 'current'})
print(result)
"
```

## 📱 iPhone Shortcut Keywords

These phrases trigger the weather helper:

**Core Keywords**: `weather`, `temperature`, `forecast`, `conditions`
**Additional**: `hot`, `cold`, `rain`, `sunny`, `cloudy`

**Examples**:
- ✅ "What's the **weather** like?"
- ✅ "How **hot** is it outside?"
- ✅ "What are the current **conditions**?"
- ✅ "**Temperature** in 78624"
- ✅ "**Forecast** for today"

## ⚙️ Configuration

### Weather Helper Settings
- **API**: Free Open-Meteo API (no keys required)
- **Geocoding**: Open-Meteo + Nominatim fallback
- **Units**: Imperial (°F) by default, metric available
- **Timeout**: 10 seconds for API calls
- **Safety**: Low risk, no system modifications

### Environment Variables (Optional)
```bash
# Customize weather helper behavior
export DEFAULT_UNITS=metric          # Use Celsius instead of Fahrenheit
export WEATHER_TIMEOUT=15           # Increase timeout for slow connections
export MAX_FORECAST_DAYS=3          # Forecast length (when implemented)
```

## 🔧 Technical Details

### API Endpoints Used
- **Geocoding**: `https://geocoding-api.open-meteo.com/v1/search`
- **Weather**: `https://api.open-meteo.com/v1/forecast`
- **Fallback Geocoding**: `https://nominatim.openstreetmap.org/`

### Helper Capabilities
- **Network access**: Required for API calls
- **No authentication**: Uses free APIs
- **Safe execution**: Read-only operations, no system changes
- **Location aware**: Integrates with TinyIntent location service

### Input Schema
```json
{
  "location": "78624 or Austin, TX or 30.27,-97.74 (optional with GPS)",
  "operation": "current or forecast",
  "units": "imperial or metric",
  "include_forecast": true/false
}
```

### Output Format
```json
{
  "status": "success",
  "location": "Fredericksburg, Texas, United States",
  "current": {
    "temperature": 90.0,
    "feels_like": 85.8,
    "humidity": 30,
    "description": "Mainly clear",
    "wind_speed": 13.0
  },
  "message": "Currently 90°F feels like 86°F and mainly clear...",
  "coordinates": {"latitude": 30.2672, "longitude": -97.7431}
}
```

## 🎯 Success Indicators

**Weather helper is working correctly when**:
- ✅ iPhone Shortcut returns real temperature readings
- ✅ Location names are resolved (e.g., "Fredericksburg, Texas")
- ✅ Weather conditions are specific (e.g., "mainly clear", not generic)
- ✅ Responses include humidity, wind speed, "feels like" temperature
- ✅ GPS coordinates are used when available

**Still using LLM fallback when**:
- ❌ Responses are generic: "I'd be happy to help with weather..."
- ❌ No specific temperature readings
- ❌ No location resolution
- ❌ Missing `TINYINTENT_EXECUTION_ENABLED=1` environment variable

---

**Need help?** Check the main TinyIntent documentation or create an issue with your specific error message and setup details.