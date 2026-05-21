# 🛋️ Tatami Shot

Detect what's playing in Plex, grab a frame or clip, share it from your phone.

The name comes from Yasujirō Ozu's _tatami shot_, his signature low-angle compositions filmed from floor level. The goal of this software is to replace the philistine's version of the tatami shot: slumping into the couch, pointing your phone up to the TV, trying to take a bootleg-quality picture of a frame you like.

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

Logs are structured JSON. `make docker/logs` runs `docker compose logs -f --no-log-prefix` — the `--no-log-prefix` flag strips the `tatamishot  | ` container prefix so lines are pure JSON. Pipe through `grep '^{'` to skip any non-JSON startup lines, then into `jq`:

```bash
# live tail, pretty-printed
make docker/logs | grep '^{' | jq .

# only warnings and errors
make docker/logs | grep '^{' | jq 'select(.level == "warning" or .level == "error")'

# watch ffmpeg commands as they fire
make docker/logs | grep '^{' | jq 'select(.event == "clip_cmd" or .event == "frame_cmd")'

# follow a specific job
make docker/logs | grep '^{' | jq 'select(.job_id == "<id>")'

# follow a specific request
make docker/logs | grep '^{' | jq 'select(.["X-Request-ID"] == "<id>")'
```

`make docker/logs` is an alias for `docker compose logs -f --no-log-prefix tatamishot`. You can also run that directly if you want to pass extra flags (e.g. `--since 10m`).

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
