# Security

## What midjourney-bridge stores

midjourney-bridge persists exactly one secret: your Midjourney session cookie. It is stored in your OS-native config directory (`platformdirs.user_config_dir("midjourney-bridge")`):

- **macOS:** `~/Library/Application Support/midjourney-bridge/.env`
- **Linux:** `~/.config/midjourney-bridge/.env`
- **Windows:** `%APPDATA%/midjourney-bridge/.env`

The file is created with `chmod 0600` (owner read/write only).

## What it never does

- ❌ Does not log cookie values
- ❌ Does not include cookie values in error messages or stack traces
- ❌ Does not transmit cookies anywhere except `https://www.midjourney.com` and `https://cdn.midjourney.com`
- ❌ Does not phone home, no telemetry, no analytics

The `mj doctor` command redacts the cookie before printing diagnostic info.

## What you should do

1. **Don't commit your `.env`.** Both the project's own `.gitignore` and the OS config dir are excluded by default, but be careful if you copy files around.
2. **Rotate periodically.** Sign out / back in on midjourney.com to invalidate stale tokens. Re-paste with `mj cookie set`.
3. **One cookie per machine.** If you use midjourney-bridge on multiple machines, each gets its own cookie capture. Don't sync the `.env` via cloud storage.
4. **Be careful with screen sharing.** When pasting into `mj cookie set`, the input is not echoed — but any other display of your cookie (DevTools, clipboard managers) is your responsibility.

## Reporting a vulnerability

Found something? Email **academy@likeahuman.ai** with `[midjourney-bridge security]` in the subject. Do not open a public issue. We'll acknowledge within 5 business days.

## Threat model

midjourney-bridge is a single-user tool. The threat model assumes:
- Your local machine is trusted
- Your cookie is as sensitive as your MJ password (treat accordingly)
- TLS protects the wire; we don't add additional encryption
- We are not a service — there is no shared infrastructure to attack

If your cookie leaks, the attacker can use your MJ subscription. They cannot exfiltrate your password or take over your account (the JWT is short-lived; the refresh token is bound to MJ's auth flow).
