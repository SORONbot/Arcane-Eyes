# Arcane Eyes

Arcane Eyes is a desktop IP camera manager built around RTSP and ONVIF. It discovers cameras on the local network, shows live feeds, exposes PTZ controls when available, and records video with audio-aware stream handling.

The goal is to provide one simple control panel for cameras that otherwise depend on fragmented vendor tools.

## Features

- **Network discovery**: Scans a configured network range and adds cameras as they are found.
- **ONVIF capability probing**: Reads device info, media profiles, stream URIs, PTZ availability, and service warnings when ONVIF is available.
- **Validated stream profiles**: Probes RTSP streams with PyAV/FFmpeg and trusts the actual media tracks over loose ONVIF metadata.
- **Smart profile selection**: Uses lower-resolution streams for the multi-feed dashboard and higher-resolution streams for Feed Details and recording.
- **Feed Details view**: Shows stream profiles, codec/resolution/audio details, ONVIF identity, PTZ state, and probe warnings.
- **PTZ controls**: Uses ONVIF PTZ when the camera reports usable support.
- **Recording**: Prefers audio embedded in the selected RTSP stream and falls back to the legacy TCP audio path only when needed.
- **CSV cache**: Stores cameras, credentials, selected profiles, and capability metadata in `.eye_cache`.

## Setup

This project uses `uv`.

```bash
uv pip install -e .
arcane-eyes
```

Common environment settings:

```bash
SCAN_RANGE=192.168.100.0/24
RTSP_TRANSPORT=tcp
ONVIF_DEFAULT_USER=admin
ONVIF_DEFAULT_PASSWORD=
ONVIF_PORT=80
```

See `.env.example` for the full list.

## Cache

`.eye_cache` remains a CSV file. Older three-column cache files are migrated automatically the next time the app saves cameras.

Newer cache rows include ONVIF capability metadata as JSON inside a CSV cell. If that metadata is missing or malformed, the app keeps the camera row and re-probes capabilities.

## Tested Cameras

- TG1/YQC13/DF2427196 family cameras

These cameras expose TAS/Ginatex-style RTSP behavior and ONVIF media profiles. The implementation is intended to stay brand-agnostic, so unsupported or partial ONVIF behavior should appear as warnings rather than hard failures.

## Current Limitations

- ONVIF camera configuration is read-only for now.
- Non-ONVIF PTZ is not implemented.
- Some vendor-specific controls such as night vision, motion detection, and IR settings are displayed as unavailable until a standard or vendor-specific control path is added.
