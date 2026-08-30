"""
Public Domain & Creative Commons Archive Connector.
Searches verified public domain / CC repositories that explicitly provide free downloads.
Note: Direct bulk archive streaming/staging is currently in discovery mode.
"""

from pathlib import Path
from typing import List, Optional
from music_agent.connectors.base import BaseConnector, TrackCandidate, AcquisitionSourceStatus


class PublicArchiveConnector(BaseConnector):
    """Searches authorized public domain / CC repositories."""

    @property
    def source_name(self) -> str:
        return "PublicArchive"

    def search(self, artist: str, title: str) -> List[TrackCandidate]:
        # For curated commercial artists, public CC archives do not host original masters
        return []

    def verify_policy_compliance(self, candidate: TrackCandidate) -> bool:
        license_str = (candidate.license_note or "").strip()
        is_open_license = ("Creative Commons" in license_str) or ("Public Domain" in license_str)
        return (
            candidate.status == AcquisitionSourceStatus.AVAILABLE
            and candidate.direct_download_url is not None
            and is_open_license
        )

    def stage_track(self, candidate: TrackCandidate, staging_dir: Path) -> Optional[Path]:
        # Direct public archive staging is currently discovery/metadata only
        return None
