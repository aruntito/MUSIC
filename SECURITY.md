# Security Policy

## Overview

Music Library Agent is designed with security as a first-class concern. Because the `acquire` command involves URL resolution, HTTP requests, and file downloads, the following protections are implemented and enforced at the code level.

## Scope

This security policy covers:

- The acquisition pipeline (`music_agent/acquisition.py` and `music_agent/connectors/`)
- File ingestion and ZIP extraction (`music_agent/organizer.py`)
- Phone sync file transfer (`music_agent/phone_sync.py`)

## Security Controls

### SSRF Protection

All URLs processed by the acquisition pipeline are subject to SSRF (Server-Side Request Forgery) validation before any network request is made:

- **DNS pre-resolution**: The hostname is resolved to an IP address before the request is issued.
- **Private range blocking**: Requests are rejected if the resolved IP falls within any of the following:
  - RFC1918 private ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
  - Loopback: `127.0.0.0/8`
  - Link-local: `169.254.0.0/16`
  - IPv6 loopback: `::1`
  - Any other non-routable or reserved block
- **Redirect chain validation**: Every URL in an HTTP redirect chain is re-validated against the same IP range rules. A redirect to an internal IP is rejected even if the original URL was external.
- **Redirect depth limit**: The redirect chain is capped at a maximum depth to prevent infinite redirect loops.

### Domain Allowlist

Only explicitly approved source domains are permitted for acquisition requests. Any URL whose hostname does not match the allowlist is rejected immediately, before DNS resolution.

### Download Size Limit

Files exceeding **250 MB** are rejected before the full download completes. The response `Content-Length` header is checked first; if the actual streamed bytes exceed the limit, the transfer is aborted and the partial file is discarded.

### Staging Containment

All downloads are written to a temporary staging directory isolated from the main library. A file is only promoted to `~/Downloads/Songs/` after:
1. Successful and complete download.
2. Metadata validation by the organizer pipeline.
3. Artist matching against the curated list.

Partial files are never promoted. If any step fails, the staging file is deleted.

### ZIP Slip Protection

ZIP archive extraction validates every member's destination path to ensure it does not escape the staging sandbox. Any archive member whose resolved path falls outside the staging directory is rejected and the extraction is aborted.

### Filename Sanitization

All filenames are sanitized before being written to disk. Characters illegal on macOS (`/`, `:`, NUL) and Android (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) are removed or replaced. Filenames are also truncated to a maximum of 180 characters.

### Copyright and DRM

The acquisition pipeline enforces a hard policy:

- Commercial tracks are classified as `PURCHASE_REQUIRED`. No download attempt is made.
- Stream ripping from any streaming service (Spotify, YouTube Music, Apple Music, etc.) is not implemented.
- DRM circumvention is not implemented.
- These constraints are hard-coded design decisions, not configuration options.

### Copy-Only File Operations

Neither the organizer nor the phone sync module contains delete, remove, or prune operations against source files, destination files, or phone files. All operations are additive copies only.

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please do NOT open a public GitHub issue.

Instead:
1. Open a **private security advisory** on GitHub (Repository → Security → Advisories → New draft advisory).
2. Include a clear description of the vulnerability, steps to reproduce, and potential impact.
3. Allow reasonable time for a fix before any public disclosure.

## Out of Scope

The following are intentional design decisions, not vulnerabilities:

- The agent does not download commercial/DRM-protected music. This is by design.
- The agent does not support streaming service integration. This is by design.
- The agent does not implement fuzzy artist matching. Conservative exact matching is a security/correctness choice.
