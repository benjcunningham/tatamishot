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
| `PLEX_URL` | URL of your Plex server — use `http://host.docker.internal:32400` when running via Docker on the same machine as Plex |
| `OUTPUT_DIR` | Absolute path for ffmpeg output inside the container (default: `/output`) |
| `MEDIA_DIR_HOST` | Absolute path to your media library on the host (what Plex returns in file paths, e.g. `/mnt/media`) |
| `MEDIA_DIR` | Path where media is mounted inside the container / visible to the app (default: `/media`) |

### Getting a Plex token

On the Pi, find it in the Plex preferences file:

```bash
grep -r "PlexOnlineToken" "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml"
```

## Running with Docker (recommended)

```bash
make docker/build
make docker/up
```

Logs: `make docker/logs` — Stop: `make docker/down`

After pulling new changes, do a full rebuild:

```bash
make docker/down
git pull
make docker/build
make docker/up
```

## Running locally (without Docker)

```bash
make install
make run
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
