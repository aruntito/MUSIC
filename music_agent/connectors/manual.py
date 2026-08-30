"""
Manual / Local Acquisition Connector.
Allows importing verified local audio files or user-provided direct download sources
subject to strict domain whitelisting, scheme validation, SSRF checks, and redirect protections.
"""

import os
from pathlib import Path
import shutil
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Optional
from music_agent.connectors.base import (
    BaseConnector,
    TrackCandidate,
    AcquisitionSourceStatus,
    AcquisitionPolicy,
    validate_acquisition_url,
    verify_host_dns_safety,
)
from music_agent.sanitizer import sanitize_filename


class SecureRedirectHandler(urllib.request.HTTPRedirectHandler):
    """HTTP redirect handler that validates target redirected URLs against security and SSRF policies."""

    def __init__(self, policy: AcquisitionPolicy):
        super().__init__()
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        is_valid, reason = validate_acquisition_url(newurl, self.policy, check_dns=True)
        if not is_valid:
            raise urllib.error.HTTPError(
                newurl, code, f"Security Violation: Redirect rejected ({reason})", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ManualLocalConnector(BaseConnector):
    """Connector for manually verified user-supplied paths or URLs."""

    def __init__(self, policy: Optional[AcquisitionPolicy] = None):
        self.policy = policy or AcquisitionPolicy()

    @property
    def source_name(self) -> str:
        return "ManualLocal"

    def search(self, artist: str, title: str) -> List[TrackCandidate]:
        return []

    def verify_policy_compliance(self, candidate: TrackCandidate) -> bool:
        if candidate.status != AcquisitionSourceStatus.AVAILABLE:
            return False
        if not candidate.direct_download_url:
            return False

        is_valid, _ = validate_acquisition_url(candidate.direct_download_url, self.policy, check_dns=False)
        return is_valid

    def stage_track(self, candidate: TrackCandidate, staging_dir: Path) -> Optional[Path]:
        if not self.verify_policy_compliance(candidate):
            return None

        url = candidate.direct_download_url
        if not url:
            return None

        staging_dir = Path(staging_dir).resolve()
        staging_dir.mkdir(parents=True, exist_ok=True)

        # 1. Local filesystem path
        if url.startswith("file://") or url.startswith("/") or url.startswith("~"):
            src_path = Path(url.replace("file://", "")).expanduser().resolve()
            if not src_path.exists() or not src_path.is_file():
                return None
            safe_name = sanitize_filename(src_path.name)
            dst_path = (staging_dir / safe_name).resolve()
            # Staging path escape check
            if not str(dst_path).startswith(str(staging_dir)):
                return None
            shutil.copy2(str(src_path), str(dst_path))
            return dst_path

        # 2. Remote HTTPS URL
        is_valid, reason = validate_acquisition_url(url, self.policy, check_dns=True)
        if not is_valid:
            print(f"[SECURITY REJECTED] {reason}")
            return None

        parsed = urllib.parse.urlparse(url)
        raw_name = Path(parsed.path).name or f"{candidate.artist} - {candidate.title}.mp3"
        safe_name = sanitize_filename(raw_name)
        dst_path = (staging_dir / safe_name).resolve()

        # Ensure staging containment
        if not str(dst_path).startswith(str(staging_dir)):
            print(f"[SECURITY REJECTED] Destination path escaped staging directory: {dst_path}")
            return None

        opener = urllib.request.build_opener(SecureRedirectHandler(self.policy))
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MusicLibraryAgent/1.0 (macOS; Local Curated Ingestion)"}
        )

        downloaded_bytes = 0
        try:
            with opener.open(req, timeout=self.policy.timeout_seconds) as response:
                content_len_header = response.headers.get("Content-Length")
                if content_len_header:
                    try:
                        content_len = int(content_len_header)
                        if content_len > self.policy.max_download_size_bytes:
                            print(f"[SECURITY REJECTED] Content length {content_len} exceeds max size {self.policy.max_download_size_bytes}")
                            return None
                    except ValueError:
                        pass

                with open(dst_path, "wb") as out_f:
                    while chunk := response.read(65536):
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > self.policy.max_download_size_bytes:
                            print(f"[SECURITY REJECTED] Download size exceeded limit ({downloaded_bytes} bytes)")
                            raise ValueError("Download size exceeded maximum allowed limit")
                        out_f.write(chunk)

            if downloaded_bytes == 0 or not dst_path.exists():
                if dst_path.exists():
                    dst_path.unlink()
                return None

            return dst_path

        except Exception as e:
            if dst_path.exists():
                try:
                    dst_path.unlink()
                except OSError:
                    pass
            print(f"[ERROR] Download failed for {url}: {e}")
            return None
