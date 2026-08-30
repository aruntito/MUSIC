import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

from music_agent.acquisition import AcquisitionManager
from music_agent.config import LibraryConfig
from music_agent.connectors.base import (
    TrackCandidate,
    AcquisitionSourceStatus,
    AcquisitionPolicy,
    validate_acquisition_url,
    is_domain_trusted,
    is_ip_public_and_safe,
    verify_host_dns_safety,
)
from music_agent.connectors.manual import ManualLocalConnector, SecureRedirectHandler
from music_agent.connectors.official_stores import OfficialStoreConnector
from music_agent.connectors.public_archive import PublicArchiveConnector


@pytest.fixture
def custom_policy():
    return AcquisitionPolicy(
        allowed_schemes=["file", "https"],
        trusted_direct_domains=["bandcamp.com", "archive.org", "freemusicarchive.org"],
        timeout_seconds=5,
        max_download_size_bytes=1000000,
        block_private_ips=True,
    )


def test_http_source_is_rejected(custom_policy):
    is_valid, reason = validate_acquisition_url("http://bandcamp.com/download/track.mp3", custom_policy)
    assert is_valid is False
    assert "not permitted" in reason


def test_untrusted_https_domain_is_rejected(custom_policy):
    is_valid, reason = validate_acquisition_url("https://untrusted-pirate-site.example/song.mp3", custom_policy)
    assert is_valid is False
    assert "not in trusted direct domains whitelist" in reason


def test_domain_suffix_and_prefix_spoofing_rejected(custom_policy):
    # Attacker domain with trusted domain as prefix/suffix
    assert validate_acquisition_url("https://bandcamp.com.evil.com/song.mp3", custom_policy)[0] is False
    assert validate_acquisition_url("https://evilbandcamp.com/song.mp3", custom_policy)[0] is False
    assert validate_acquisition_url("https://notbandcamp.com/song.mp3", custom_policy)[0] is False


def test_userinfo_url_is_rejected(custom_policy):
    # Embedded credentials / userinfo tricks
    assert validate_acquisition_url("https://bandcamp.com@evil.com/song.mp3", custom_policy)[0] is False
    assert validate_acquisition_url("https://user:pass@bandcamp.com/song.mp3", custom_policy)[0] is False


def test_trusted_domain_and_subdomain_is_accepted(custom_policy):
    is_valid, _ = validate_acquisition_url("https://bandcamp.com/download/track.mp3", custom_policy)
    assert is_valid is True

    is_valid_sub, _ = validate_acquisition_url("https://artistname.bandcamp.com/track/song.flac", custom_policy)
    assert is_valid_sub is True


def test_ssrf_ip_filtering():
    # Loopback
    assert is_ip_public_and_safe("127.0.0.1") is False
    assert is_ip_public_and_safe("::1") is False

    # RFC1918 Private
    assert is_ip_public_and_safe("10.0.0.1") is False
    assert is_ip_public_and_safe("172.16.0.1") is False
    assert is_ip_public_and_safe("192.168.1.1") is False

    # Link-local & Multicast
    assert is_ip_public_and_safe("169.254.169.254") is False
    assert is_ip_public_and_safe("224.0.0.1") is False

    # Public IP
    assert is_ip_public_and_safe("93.184.216.34") is True


def test_dns_resolution_to_private_ip_is_blocked(custom_policy):
    # Mock DNS resolving to private IP
    with patch("socket.getaddrinfo") as mock_getaddr:
        mock_getaddr.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 443))
        ]
        is_safe, reason = verify_host_dns_safety("bandcamp.com")
        assert is_safe is False
        assert "SSRF blocked" in reason


def test_redirect_to_untrusted_domain_is_rejected(custom_policy):
    handler = SecureRedirectHandler(custom_policy)
    req = MagicMock()
    fp = MagicMock()

    with pytest.raises(urllib.error.HTTPError, match="Security Violation: Redirect rejected"):
        handler.redirect_request(req, fp, 302, "Found", {}, "https://evil-untrusted-redirect.example/song.mp3")


def test_redirect_to_http_is_rejected(custom_policy):
    handler = SecureRedirectHandler(custom_policy)
    req = MagicMock()
    fp = MagicMock()

    with pytest.raises(urllib.error.HTTPError, match="Security Violation: Redirect rejected"):
        handler.redirect_request(req, fp, 302, "Found", {}, "http://bandcamp.com/song.mp3")


def test_public_domain_license_requires_available_status():
    conn = PublicArchiveConnector()

    cand_unavail = TrackCandidate(
        source_name="PublicArchive",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.UNAVAILABLE,
        direct_download_url="https://archive.org/song.mp3",
        license_note="Public Domain Mark 1.0",
    )
    assert conn.verify_policy_compliance(cand_unavail) is False

    cand_avail = TrackCandidate(
        source_name="PublicArchive",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url="https://archive.org/song.mp3",
        license_note="Public Domain Mark 1.0",
    )
    assert conn.verify_policy_compliance(cand_avail) is True


def test_purchase_search_does_not_claim_verified_purchase():
    conn = OfficialStoreConnector()
    results = conn.search("Billie Eilish", "Ocean Eyes")
    for r in results:
        assert r.status == AcquisitionSourceStatus.PURCHASE_REQUIRED
        assert "search destination generated" in r.reason.lower()
        assert r.is_policy_approved is False
        assert conn.verify_policy_compliance(r) is False


def test_download_size_limit_is_enforced(custom_policy, tmp_path):
    conn = ManualLocalConnector(custom_policy)
    cand = TrackCandidate(
        source_name="Bandcamp",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url="https://bandcamp.com/huge_track.flac",
        is_policy_approved=True,
    )

    staging = tmp_path / "staging"
    staging.mkdir()

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "5000000"}  # 5MB > 1MB policy limit
    mock_resp.__enter__.return_value = mock_resp

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_resp
            mock_opener_cls.return_value = mock_opener

            staged = conn.stage_track(cand, staging)
            assert staged is None
            assert len(list(staging.glob("*"))) == 0


def test_chunked_response_exceeding_max_size_is_aborted(custom_policy, tmp_path):
    conn = ManualLocalConnector(custom_policy)
    cand = TrackCandidate(
        source_name="Bandcamp",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url="https://bandcamp.com/endless_stream.flac",
        is_policy_approved=True,
    )

    staging = tmp_path / "staging"
    staging.mkdir()

    # Response with no Content-Length header, returning 20 chunks of 65KB (1.3MB > 1.0MB limit)
    mock_resp = MagicMock()
    mock_resp.headers = {}
    mock_resp.read.side_effect = [b"A" * 65536] * 20 + [b""]
    mock_resp.__enter__.return_value = mock_resp

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_resp
            mock_opener_cls.return_value = mock_opener

            staged = conn.stage_track(cand, staging)
            assert staged is None
            # Aborted file must be cleaned up immediately
            assert len(list(staging.glob("*"))) == 0


def test_zero_byte_download_is_rejected_and_cleaned_up(custom_policy, tmp_path):
    conn = ManualLocalConnector(custom_policy)
    cand = TrackCandidate(
        source_name="Bandcamp",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url="https://bandcamp.com/empty.mp3",
        is_policy_approved=True,
    )

    staging = tmp_path / "staging"
    staging.mkdir()

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "0"}
    mock_resp.read.return_value = b""
    mock_resp.__enter__.return_value = mock_resp

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_resp
            mock_opener_cls.return_value = mock_opener

            staged = conn.stage_track(cand, staging)
            assert staged is None
            assert len(list(staging.glob("*"))) == 0


def test_download_filename_path_traversal_escapes_are_sanitized(custom_policy, tmp_path):
    conn = ManualLocalConnector(custom_policy)
    # URL containing directory traversal attempt
    cand = TrackCandidate(
        source_name="Bandcamp",
        artist="Artist",
        title="Title",
        status=AcquisitionSourceStatus.AVAILABLE,
        direct_download_url="https://bandcamp.com/../../evil.mp3",
        is_policy_approved=True,
    )

    staging = tmp_path / "staging"
    staging.mkdir()

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "100"}
    mock_resp.read.side_effect = [b"VALID_AUDIO_BYTES_12345", b""]
    mock_resp.__enter__.return_value = mock_resp

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_resp
            mock_opener_cls.return_value = mock_opener

            staged = conn.stage_track(cand, staging)
            assert staged is not None
            # Must be contained within staging_dir and not escape to parent
            assert str(staged).startswith(str(staging.resolve()))
            assert not (tmp_path / "evil.mp3").exists()


def test_disabled_connector_is_not_used(tmp_path):
    config = LibraryConfig.load()
    acq_cfg_file = tmp_path / "acq_custom.json"
    acq_cfg_file.write_text(json.dumps({
        "version": 1,
        "settings": {
            "allowed_schemes": ["file", "https"],
            "trusted_direct_domains": ["bandcamp.com"]
        },
        "connectors": {
            "manual_local": {"enabled": True},
            "official_stores": {"enabled": False},
            "public_archives": {"enabled": False}
        }
    }))

    manager = AcquisitionManager(config, acquisition_config_path=acq_cfg_file)
    assert len(manager.connectors) == 1
    assert manager.connectors[0].source_name == "ManualLocal"


def test_failed_acquisition_leaves_zero_partial_files_in_library(tmp_path):
    config = LibraryConfig.load()
    config.destination_dir = tmp_path / "Songs"
    config.destination_dir.mkdir(parents=True, exist_ok=True)

    wishlist_path = tmp_path / "wishlist.json"
    wishlist_path.write_text(json.dumps({
        "version": 1,
        "tracks": [
            {
                "artist": "Billie Eilish",
                "title": "Ocean Eyes",
                "category": "International",
                "priority": "core",
                "status": "wanted",
                "source_url": "https://bandcamp.com/broken_download.mp3"
            }
        ]
    }))

    manager = AcquisitionManager(config, wishlist_path=wishlist_path)

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.side_effect = IOError("Network timeout or connection reset")
            mock_opener_cls.return_value = mock_opener

            report = manager.run_acquisition(dry_run=False)
            assert report.acquired_count == 0

            # Destination library MUST have 0 partial or corrupted files
            assert len(list(config.destination_dir.rglob("*"))) == 0
