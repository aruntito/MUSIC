import pytest
from pathlib import Path
from music_agent.connectors.manual import ManualLocalConnector
from music_agent.connectors.base import TrackCandidate, AcquisitionSourceStatus
from tests.make_dummy_audio import create_dummy_mp3


def test_manual_connector_interface(tmp_path):
    conn = ManualLocalConnector()
    assert conn.source_name == "ManualLocal"

    f = tmp_path / "song.mp3"
    create_dummy_mp3(f, artist="Billie Eilish", title="Ocean Eyes")

    cand = TrackCandidate(
        source_name="ManualLocal",
        artist="Billie Eilish",
        title="Ocean Eyes",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url=str(f)
    )

    assert conn.verify_policy_compliance(cand) is True

    staging = tmp_path / "staging"
    staged_path = conn.stage_track(cand, staging)
    assert staged_path is not None
    assert staged_path.exists()
    assert staged_path.name == "song.mp3"
