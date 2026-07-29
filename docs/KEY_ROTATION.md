# TinyIntent Key Rotation Procedures

This document describes procedures for rotating cryptographic keys used in TinyIntent for agent provenance verification.

## Overview

TinyIntent uses HMAC-SHA256 cryptographic signing for agent provenance verification. The provenance key ensures that helper agents have not been tampered with and can be traced to their source.

## Key Types

### 1. Provenance Key
- **Purpose**: Signs helper manifests to verify integrity
- **Location**: `bridge/keys/provenance.key`
- **Size**: 512 bits (64 bytes)
- **Algorithm**: HMAC-SHA256
- **Permissions**: `0400` (read-only, owner only)

### 2. Application Credentials
- **TINYINTENT_SECRET**: API authentication secret
- **SHORTCUT_TOKEN**: iPhone Shortcut authentication token
- **Location**: `~/.tinyintent/credentials.json`
- **Management**: Use `tinyintent show-credentials` and `tinyintent regenerate-credentials`

## When to Rotate Keys

### Scheduled Rotation
- **Provenance Key**: Quarterly rotation recommended
- **Credentials**: Every 6 months or as needed

### Immediate Rotation Required
1. Key compromise suspected
2. Personnel with key access leaves the team
3. Security incident involving the system
4. Keys accidentally exposed in logs or version control

## Provenance Key Rotation

### Pre-Rotation Checklist

- [ ] Notify team of planned rotation window
- [ ] Backup current key
- [ ] Ensure no active helper deployments in progress
- [ ] Have emergency rollback plan ready

### Standard Rotation Procedure

#### Step 1: Stop TinyIntent Service

```bash
# If using systemd
sudo systemctl stop tinyintent

# If running directly
pkill -f "tinyintent serve"

# Or via CLI
# Ctrl+C in the terminal running tinyintent
```

#### Step 2: Backup Existing Key

```bash
cd /path/to/tinyintent

# Create backup with timestamp
cp bridge/keys/provenance.key \
   bridge/keys/provenance.key.backup.$(date +%Y%m%d)

# Verify backup
ls -la bridge/keys/provenance.key*
```

#### Step 3: Remove Old Key (Forces Regeneration)

```bash
# Remove the key file
rm bridge/keys/provenance.key

# Verify removal
ls bridge/keys/
```

#### Step 4: Start Service (Auto-generates New Key)

```bash
# Start TinyIntent - new key will be generated automatically
tinyintent serve

# The log will show:
# "Generated new provenance key"
```

#### Step 5: Re-sign All Helpers

```bash
# Run the re-signing script
python scripts/resign_all_helpers.py

# Output will show:
#   OK: weather
#   OK: system_monitor
#   OK: bot_guard
#   ...
```

#### Step 6: Verify Provenance

```bash
# Verify all helpers pass provenance check
python scripts/verify_all_provenance.py

# Or check via API
curl http://localhost:8787/helpers/health | jq '.health_checks.results[].provenance_ok'
```

### Post-Rotation Verification

- [ ] All helpers pass provenance verification
- [ ] No execution errors in logs
- [ ] Audit log shows key rotation event
- [ ] Test shortcut integration works
- [ ] Run health check: `curl http://localhost:8787/health`

## Emergency Key Rotation

If key compromise is suspected, follow these steps immediately:

### Step 1: Disable Execution

```bash
# Emergency kill switch - disables all execution
curl -X POST http://localhost:8787/system/emergency/kill \
  -H "X-TinyIntent-Secret: $TINYINTENT_SECRET"
```

### Step 2: Review Audit Logs

```bash
# Check recent audit entries for suspicious activity
tail -100 bridge/logs/audit.log | grep -E "(provenance|signature|execution)"
```

### Step 3: Follow Standard Rotation

Complete the standard rotation procedure above.

### Step 4: Investigate

1. Check when the compromise may have occurred
2. Review which helpers may have been affected
3. Consider rotating application credentials as well
4. Document the incident

## Application Credentials Rotation

### Rotate via CLI

```bash
# Show current credentials
tinyintent show-credentials

# Regenerate with confirmation
tinyintent regenerate-credentials

# Update iPhone Shortcuts with new token
```

### Manual Rotation

```bash
# Remove credentials file
rm ~/.tinyintent/credentials.json

# Restart TinyIntent - new credentials will be generated
tinyintent serve

# Get new token for iPhone Shortcuts
tinyintent show-credentials
```

## Key Storage Best Practices

1. **Never commit keys to version control**
   - Keys directory is in `.gitignore`
   - Verify: `git check-ignore bridge/keys/`

2. **Secure file permissions**
   - Provenance key: `chmod 0400 bridge/keys/provenance.key`
   - Credentials: `chmod 0600 ~/.tinyintent/credentials.json`

3. **Backup encryption**
   - Store key backups in encrypted storage
   - Use macOS Keychain for additional security

4. **Access control**
   - Limit key file access to service account
   - Use separate keys for dev/staging/production

## Automation

### Scheduled Key Rotation Script

Create a cron job for automated key rotation reminders:

```bash
# Add to crontab
# Reminder every quarter (1st of Jan, Apr, Jul, Oct)
0 9 1 1,4,7,10 * /path/to/scripts/key_rotation_reminder.sh
```

### Monitoring Key Age

```bash
# Check key age
stat bridge/keys/provenance.key | grep Modify

# Or via script
python -c "
from pathlib import Path
from datetime import datetime
key_path = Path('bridge/keys/provenance.key')
if key_path.exists():
    age_days = (datetime.now() - datetime.fromtimestamp(key_path.stat().st_mtime)).days
    print(f'Key age: {age_days} days')
    if age_days > 90:
        print('WARNING: Key rotation recommended')
"
```

## Rollback Procedure

If issues occur after key rotation:

1. Stop TinyIntent service
2. Restore backed up key:
   ```bash
   cp bridge/keys/provenance.key.backup.YYYYMMDD bridge/keys/provenance.key
   chmod 0400 bridge/keys/provenance.key
   ```
3. Start TinyIntent service
4. Verify helpers work with old key

## Related Documentation

- [SECURITY.md](./SECURITY.md) - Full security architecture
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment procedures
- [PRODUCTION.md](./PRODUCTION.md) - Production configuration
