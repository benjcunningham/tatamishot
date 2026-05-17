# 🛋️ Tatami Shot

Detect what's playing in Plex, grab a frame or clip, share it from your phone.

## Setup

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `PLEX_TOKEN` | Your Plex auth token (see below) |
| `PLEX_URL` | URL of your Plex server, e.g. `http://localhost:32400` |
| `OUTPUT_DIR` | Absolute path for ffmpeg output, e.g. `/home/ben/tatamishot/output` |

### Getting a Plex token

On the Pi, find it in the Plex preferences file:

```bash
grep -r "PlexOnlineToken" "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml"
```

## Running on the Pi

```bash
make install
mkdir -p output
poetry run uvicorn tatamishot.main:app --host 0.0.0.0 --port 8484
```

## Accessing from your phone

With Tailscale running on both the Pi and your phone:

```bash
tailscale ip -4  # run on the Pi to get its Tailscale IP
```

Then open `http://<tailscale-ip>:8484` on your phone.

## Development

```bash
make install   # install dependencies
make fix       # auto-fix lint errors
make lint      # run ruff + mypy
make test      # run tests
```
