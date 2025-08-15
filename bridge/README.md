# TinyIntent Bridge (tinyrpc)

A minimal Flask server that receives `{text, route}` from the iPhone Shortcut and calls `agent/neuro_agent`.

## Security
- Requires `X-TinyIntent-Secret` header (set in launchd plist or env).
- Default bind: 127.0.0.1. To accept LAN/Tailscale, set `TINYINTENT_BIND=0.0.0.0` and firewall appropriately.
- Supports Router v2 labels: gen, act, auto (with legacy pattern mapping).
- Caps text length at 8192 chars.
- `TINYINTENT_DRYRUN=1` prints planned commands without executing.

## Make Targets
- `make ios-model` → writes `router/TinyIntent_iOS.mlmodel`
- `make bridge-venv` → creates venv + Flask
- `make bridge` → loads launchd service
- `make bridge-stop` → unloads launchd service
- `make bridge-logs` → tails logs
- `make iphone-test` → sends a sample POST with your secret

## iPhone Shortcut (v1)
1. **Dictate Text** (Language: Auto / On-Device if available)
2. **Run Core ML Model**  
   - Model: `TinyIntent_iOS.mlmodel` (import into Files app or via AirDrop)  
   - Input: the dictated text  
   - Output: a label (string)
3. **Get Contents of URL** (POST)  
   - URL: `http://<your-mac-ip>:8787/route`  
   - Headers: `X-TinyIntent-Secret: <your secret>`  
   - Request Body: JSON  
     ```json
     {
       "text": "<Shortcut variable: Dictated Text>",
       "route": "<Shortcut variable: Core ML Result>"
     }
     ```
4. Optional: Show Result / Notification