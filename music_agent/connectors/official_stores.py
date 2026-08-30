"""
Official Store Discovery Connector.
Generates legitimate search destinations on digital purchase stores (iTunes Store, Bandcamp, Qobuz)
for commercial tracks and marks them as PURCHASE_REQUIRED.
Never downloads or rips unauthorized streams.
"""

import urllib.parse
from typing import List, Optional
from pathlib import Path
from music_agent.connectors.base import BaseConnector, TrackCandidate, AcquisitionSourceStatus


class OfficialStoreConnector(BaseConnector):
    """
    Identifies legitimate digital store purchase destinations.
    Strictly reports PURCHASE_REQUIRED and never executes downloads.
    """

    @property
    def source_name(self) -> str:
        return "OfficialStore"

    def search(self, artist: str, title: str) -> List[TrackCandidate]:
        query = f"{artist} {title}"
        encoded_query = urllib.parse.quote_plus(query)

        # Plain, clean valid URL strings
        itunes_url = f"https://music.apple.com/search?term={encoded_query}"
        bandcamp_url = f"https://bandcamp.com/search?q={encoded_query}"

        return [
            TrackCandidate(
                source_name="iTunes Store Search",
                artist=artist,
                title=title,
                status=AcquisitionSourceStatus.PURCHASE_REQUIRED,
                format="AAC / ALAC",
                bitrate_or_quality="256 kbps AAC / Lossless",
                store_url=itunes_url,
                reason="Commercial release: Official digital store search destination generated",
                is_policy_approved=False,
            ),
            TrackCandidate(
                source_name="Bandcamp Search",
                artist=artist,
                title=title,
                status=AcquisitionSourceStatus.PURCHASE_REQUIRED,
                format="FLAC / MP3 / WAV",
                bitrate_or_quality="Lossless Hi-Res / 320 kbps",
                store_url=bandcamp_url,
                reason="Official artist/label purchase store search destination generated",
                is_policy_approved=False,
            )
        ]

    def verify_policy_compliance(self, candidate: TrackCandidate) -> bool:
        return False

    def stage_track(self, candidate: TrackCandidate, staging_dir: Path) -> Optional[Path]:
        return None
