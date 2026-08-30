"""
Authorized Acquisition Connectors Package.
"""

from music_agent.connectors.base import BaseConnector, TrackCandidate, AcquisitionSourceStatus
from music_agent.connectors.manual import ManualLocalConnector
from music_agent.connectors.official_stores import OfficialStoreConnector
from music_agent.connectors.public_archive import PublicArchiveConnector

__all__ = [
    "BaseConnector",
    "TrackCandidate",
    "AcquisitionSourceStatus",
    "ManualLocalConnector",
    "OfficialStoreConnector",
    "PublicArchiveConnector",
]
