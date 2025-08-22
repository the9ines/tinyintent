# iOS Shortcuts Voice Interface

TinyIntent provides native iOS Shortcuts integration, enabling voice-activated access to your personal AI assistant. Use Siri to dictate commands, route them through TinyIntent's secure infrastructure, and hear spoken responses.

## Quick Setup

### 1. Configure Environment

Add to your `.env` file:

```bash
# Required: Authentication token for iOS Shortcuts
SHORTCUT_TOKEN=your-secure-random-token-here

# Optional: Maximum input length (default: 800 characters)
SHORTCUT_MAX_LEN=800

# Required for execution: Enable helper execution
TINYINTENT_EXECUTION_ENABLED=1
```

### 2. Create iOS Shortcut

1. Open **Shortcuts** app on iPhone/iPad
2. Tap **+** to create new shortcut
3. Add these actions in sequence:

**Action 1: Dictate Text**
- Add "Dictate Text" action
- Configure: "Stop Listening: After Pause"

**Action 2: Get Contents of URL**
- Add "Get Contents of URL" action
- URL: `http://your-server:8787/shortcut/route`
- Method: `POST`
- Headers:
  - `X-Shortcut-Token`: `your-secure-random-token-here`
  - `Content-Type`: `application/json`
- Request Body (JSON):
  ```json
  {
    "text": "[Dictated Text]",
    "mode": "preview",
    "return_format": "text"
  }
  ```

**Action 3: Get Value for Key**
- Add "Get Value for Key" action
- Key: `speak`

**Action 4: Speak Text**
- Add "Speak Text" action
- Text: [Contents of URL → speak]

### 3. Test the Shortcut

1. Run your shortcut
2. Say: "Show my trading positions"
3. Hear the response: "Found 2 trading positions to review."

## API Reference

### Authentication

All requests require authentication via header:

```
X-Shortcut-Token: your-configured-token
```

### Endpoints

#### GET /shortcut/ping

Health check endpoint to verify connectivity and authentication.

**Response:**
```json
{
  "ok": true,
  "ts": "2024-01-15T10:30:00Z",
  "service": "TinyIntent Bridge",
  "version": "2.0.0"
}
```

#### POST /shortcut/route

Main routing endpoint for voice commands.

**Request:**
```json
{
  "text": "close my ETH position",
  "session_id": "optional-custom-id",
  "mode": "preview|execute",
  "return_format": "text|json"
}
```

**Parameters:**
- `text` (required): Dictated speech as text (max 800 chars by default)
- `session_id` (optional): Custom session identifier
- `mode` (optional): `"preview"` (default) or `"execute"`
- `return_format` (optional): `"text"` (default) or `"json"`

**Response (return_format="text"):**
```json
{
  "speak": "Position closed on ETH at market price.",
  "truncated": false,
  "data": {
    "status": "success",
    "route_used": "act",
    "helper_id": "bot_guard",
    "result": {...}
  }
}
```

**Response (return_format="json"):**
```json
{
  "status": "success",
  "route_used": "act",
  "helper_id": "bot_guard",
  "result": {...}
}
```

## Execution Modes

### Preview Mode (Default)

Safe mode that shows what would happen without executing:

```json
{
  "mode": "preview"
}
```

- Always allowed regardless of `TINYINTENT_EXECUTION_ENABLED`
- Returns preview information and approval tokens
- No side effects or actual execution

### Execute Mode

Actually performs the requested action:

```json
{
  "mode": "execute"
}
```

- Requires `TINYINTENT_EXECUTION_ENABLED=1`
- Respects all security gates (quotas, sandboxing, provenance)
- Returns execution results

## Voice Response Formatting

The `speak` field is optimized for iOS speech synthesis:

### Text Processing

- **Markdown removal**: Strips `**bold**`, `*italic*`, `` `code` ``, etc.
- **URL removal**: Removes `http://` and `www.` links
- **Length limiting**: Caps at ~280 characters for clarity
- **Sentence completion**: Ensures proper punctuation for speech

### Smart Truncation

For long responses:

```json
{
  "speak": "Position closed successfully. See full details in the app.",
  "truncated": true,
  "data": {...full response...}
}
```

Advanced Shortcuts can check `truncated` and conditionally display full data.

## Error Handling

All errors return appropriate HTTP status codes with voice-friendly messages:

### 401 Unauthorized
```json
{
  "detail": "Missing X-Shortcut-Token header"
}
```

### 403 Forbidden
```json
{
  "speak": "Execution is currently disabled. Only previews are available.",
  "error": "EXECUTION_DISABLED",
  "truncated": false
}
```

### 400 Bad Request
```json
{
  "speak": "Input text too long. Please try a shorter command.",
  "error": "VALIDATION_ERROR",
  "details": {"text_length": 900, "max_length": 800}
}
```

### 429 Too Many Requests
```json
{
  "speak": "Too many requests. Please wait before trying again.",
  "error": "RATE_LIMIT",
  "truncated": false
}
```

## Security Features

### Authentication
- Required `X-Shortcut-Token` header prevents unauthorized access
- Token validation on every request

### Input Validation
- Length limits prevent abuse (configurable via `SHORTCUT_MAX_LEN`)
- Control character filtering
- Text sanitization

### Execution Gates
- Respects `TINYINTENT_EXECUTION_ENABLED` setting
- Full integration with quotas, sandboxing, and provenance checks
- Rate limiting and abuse protection

### Audit Logging
All shortcut requests are logged with:
- Session ID and mode
- Success/failure status
- Error codes and details
- Input validation results

## Advanced Usage

### Custom Session Management

Maintain conversation context across multiple shortcut invocations:

```json
{
  "text": "What's my portfolio value?",
  "session_id": "portfolio-session-123",
  "mode": "preview"
}
```

### JSON Mode for Advanced Shortcuts

Get full structured data for complex processing:

```json
{
  "text": "Show positions",
  "return_format": "json"
}
```

Returns the complete TinyIntent response for advanced Shortcuts that can parse JSON and create custom presentations.

### Conditional Execution

Build Shortcuts that preview first, then optionally execute:

1. **Step 1**: Send with `"mode": "preview"`
2. **Step 2**: Show preview to user
3. **Step 3**: Ask for confirmation
4. **Step 4**: If confirmed, send with `"mode": "execute"`

## Troubleshooting

### "Missing X-Shortcut-Token header"
- Verify token is configured in Shortcut headers
- Check that `SHORTCUT_TOKEN` environment variable is set

### "Execution is currently disabled"
- Set `TINYINTENT_EXECUTION_ENABLED=1` in environment
- Use `"mode": "preview"` for safe testing

### "Input text too long"
- Keep voice commands under 800 characters (or configured limit)
- Break complex requests into multiple commands

### "Too many requests"
- Respect rate limits (see bridge configuration)
- Space out requests to avoid hitting quotas

### No response or timeout
- Check network connectivity
- Verify TinyIntent bridge is running
- Use `/shortcut/ping` to test connectivity

## Example Shortcuts

### Basic Position Check
```
Voice: "Show my crypto positions"
Response: "Found 3 trading positions: BTC, ETH, and SOL."
```

### Execute with Confirmation
```
Voice: "Close my ETH position"
Mode: preview
Response: "Ready to close ETH position at market price. Use execute mode to confirm."
```

### Error Handling
```
Voice: "Do something impossible"
Response: "I don't understand that request. Try asking about your positions or available commands."
```

## Integration with TinyIntent Flow

The Shortcuts interface is a lightweight facade that routes through the complete TinyIntent infrastructure:

1. **Router**: Speech text analyzed by SmallIntent.mlmodel
2. **Actions**: Helper execution with full sandboxing
3. **Generation**: LLM responses via Ollama
4. **Security**: All gates (quotas, provenance, capabilities) enforced
5. **Audit**: Complete logging and episode tracking

This ensures consistent behavior between voice commands and full TinyIntent usage while maintaining all security guarantees.