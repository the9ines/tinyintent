# 📱 iPhone Shortcut Location Configuration

TinyIntent now supports automatic location awareness for all helpers and agents. This guide shows how to configure your iPhone Shortcut to send GPS coordinates for more accurate responses.

## 🌍 Benefits of Location-Aware TinyIntent

With location data, TinyIntent can provide:
- **Weather**: Accurate weather for your exact location without asking "where"
- **Traffic**: Real-time traffic conditions and route planning
- **Nearby**: Find restaurants, gas stations, and points of interest around you
- **Future helpers**: Any location-aware functionality automatically works

## 🔧 iPhone Shortcut Configuration

### Method 1: Simple Location Setup (Recommended)

1. **Open Shortcuts app** on your iPhone
2. **Find your TinyIntent shortcut** (or create a new one)
3. **Add these actions before the HTTP request**:

```
1. Get My Location
   - Accuracy: Best
   - Privacy: Select "Allow Once" or "Allow While Using App"

2. Get Details of Location (from Get My Location)
   - Detail: Latitude  

3. Get Details of Location (from Get My Location) 
   - Detail: Longitude

4. Get Details of Location (from Get My Location)
   - Detail: Horizontal Accuracy
```

4. **Update your HTTP request** to include location data:

```
URL: http://YOUR_IP:8787/shortcut/route
Method: POST
Headers:
  X-Shortcut-Token: your-token-here
  Content-Type: application/json

Request Body (JSON):
{
  "text": [Dictated Text],
  "latitude": [Latitude from Get Details],
  "longitude": [Longitude from Get Details], 
  "location_accuracy": [Horizontal Accuracy from Get Details],
  "return_format": "minimal"
}
```

### Method 2: Advanced Location Setup

For more control, you can:
- Use "Get Current Location" with custom accuracy settings
- Add location caching to avoid repeated GPS requests  
- Include location context in text ("What's the weather **here**")

## 🎯 Example Shortcut Flow

```
1. Dictate Text → "What's the weather like?"
2. Get My Location → (GPS coordinates)
3. Get Details of Location → Latitude: 30.2672
4. Get Details of Location → Longitude: -97.7431  
5. Get Details of Location → Accuracy: 5 meters
6. HTTP Request → POST /shortcut/route with location
7. Get Response → "Currently 79°F and clear sky in Austin, Texas"
8. Speak Text → (Weather announcement)
```

## 📍 Location Privacy & Permission

- **First run**: iPhone will ask for location permission
- **Choose**: "Allow While Using App" for best experience
- **Privacy**: Location is only sent to your TinyIntent server
- **Accuracy**: GPS accuracy of 5-15 meters gives best results

## 🚀 Voice Commands That Benefit

With location awareness, these commands become much more useful:

- **"What's the weather?"** → Gets weather for your exact location
- **"How's traffic?"** → Shows traffic conditions around you  
- **"Route to Dallas"** → Calculates travel time from your location
- **"Find nearby restaurants"** → Searches around your current area

## 🛠 Troubleshooting

**No location data sent?**
- Check location permissions in Settings → Privacy & Security → Location Services
- Verify "Get My Location" action is before the HTTP request
- Make sure location accuracy is reasonable (< 100 meters)

**Location not accurate?**  
- Use "Best" accuracy setting in "Get My Location"
- Wait a few seconds after opening Shortcut for GPS lock
- Avoid using indoors where GPS signal is weak

**Still asking for location?**
- Check that latitude/longitude are properly passed to JSON
- Verify your TinyIntent server is receiving location data in logs

## 📋 Complete JSON Structure

```json
{
  "text": "What's the weather like?",
  "latitude": 30.2672,
  "longitude": -97.7431,
  "location_accuracy": 15.0,
  "session_id": "optional-session-id",
  "mode": "preview",
  "return_format": "minimal"
}
```

## 🎉 Ready to Go!

Your iPhone Shortcut now automatically provides location context to TinyIntent, making all interactions more intelligent and personalized to your location!

For questions or issues, check the TinyIntent documentation or create an issue on GitHub.