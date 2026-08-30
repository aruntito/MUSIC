"""
Base interface and security models for legitimate music acquisition connectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import ipaddress
from pathlib import Path
import socket
from typing import List, Optional, Tuple
import urllib.parse


class AcquisitionSourceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"                  # Direct downloadable file from policy-approved source
    PURCHASE_REQUIRED = "PURCHASE_REQUIRED"  # Official digital store search link generated
    STREAM_ONLY = "STREAM_ONLY"              # Streaming only (no DRM-free file)
    UNAVAILABLE = "UNAVAILABLE"              # No verified source found


@dataclass
class AcquisitionPolicy:
    allowed_schemes: List[str] = field(default_factory=lambda: ["file", "https"])
    trusted_direct_domains: List[str] = field(
        default_factory=lambda: ["bandcamp.com", "archive.org", "freemusicarchive.org", "jamendo.com"]
    )
    timeout_seconds: int = 15
    max_download_size_bytes: int = 262144000  # 250 MB
    block_private_ips: bool = True


def is_domain_trusted(hostname: Optional[str], trusted_domains: List[str]) -> bool:
    """
    Check if a hostname matches or is a legitimate subdomain of any trusted domain.
    Rejects suffix tricks like 'bandcamp.com.evil.com' or 'evilbandcamp.com'.
    """
    if not hostname:
        return False
    host = hostname.lower().strip().rstrip(".")
    for td in trusted_domains:
        td_clean = td.lower().strip().rstrip(".")
        if host == td_clean or host.endswith(f".{td_clean}"):
            return True
    return False


def is_ip_public_and_safe(ip_str: str) -> bool:
    """
    Verify that an IP address is a valid public, routable IP.
    Rejects loopback (127.0.0.1, ::1), private RFC1918 (10.x, 192.168.x, 172.16-31.x),
    link-local (169.254.x), multicast, and unspecified (0.0.0.0).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            return False
        return True
    except ValueError:
        return False


def verify_host_dns_safety(hostname: str, port: int = 443) -> Tuple[bool, str]:
    """
    Perform DNS resolution and ensure all resolved IP addresses are safe public IPs (SSRF protection).
    """
    if not hostname:
        return False, "Empty hostname"

    # Direct IP literal check if hostname is already an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if not is_ip_public_and_safe(hostname):
            return False, f"Host IP '{hostname}' is a non-public or loopback address (SSRF blocked)"
    except ValueError:
        pass

    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        if not addr_infos:
            return False, f"DNS resolution yielded no IP addresses for {hostname}"

        for family, socktype, proto, canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            if not is_ip_public_and_safe(ip_str):
                return False, f"Host '{hostname}' resolved to unsafe/private IP address '{ip_str}' (SSRF blocked)"

        return True, "DNS resolved to safe public IPs"
    except socket.gaierror as e:
        return False, f"DNS resolution failed for {hostname}: {e}"
    except Exception as e:
        return False, f"DNS validation error: {e}"


def validate_acquisition_url(url: str, policy: AcquisitionPolicy, check_dns: bool = False) -> Tuple[bool, str]:
    """
    Validate that an acquisition URL satisfies scheme, userinfo, domain, and SSRF policies.
    Returns (is_valid, reason).
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL"

    url_str = url.strip()
    if url_str.startswith("file://") or url_str.startswith("/") or url_str.startswith("~"):
        if "file" not in policy.allowed_schemes:
            return False, "Local file scheme is disabled by policy"
        local_path = Path(url_str.replace("file://", "")).expanduser().resolve()
        if not local_path.exists() or not local_path.is_file():
            return False, f"Local file does not exist: {local_path}"
        return True, "Valid local file source"

    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        return False, "URLs containing embedded userinfo credentials are not permitted"

    if parsed.scheme not in policy.allowed_schemes:
        return False, f"Scheme '{parsed.scheme}' is not permitted (Allowed: {policy.allowed_schemes})"

    if not is_domain_trusted(parsed.hostname, policy.trusted_direct_domains):
        return False, f"Domain '{parsed.hostname}' is not in trusted direct domains whitelist"

    if check_dns and policy.block_private_ips and parsed.hostname:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        is_safe, dns_reason = verify_host_dns_safety(parsed.hostname, port)
        if not is_safe:
            return False, dns_reason

    return True, "Valid policy-approved source"


@dataclass
class TrackCandidate:
    source_name: str
    artist: str
    title: str
    status: AcquisitionSourceStatus
    format: Optional[str] = None
    bitrate_or_quality: Optional[str] = None
    direct_download_url: Optional[str] = None
    store_url: Optional[str] = None
    license_note: Optional[str] = None
    reason: Optional[str] = None
    is_policy_approved: bool = False


class BaseConnector(ABC):
    """
    Abstract connector interface for authorized music sources.
    Strictly forbids DRM bypassing, stream ripping, or unauthorized scraping.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the acquisition source."""
        pass

    @abstractmethod
    def search(self, artist: str, title: str) -> List[TrackCandidate]:
        """Search the source for matching legitimate tracks."""
        pass

    @abstractmethod
    def verify_policy_compliance(self, candidate: TrackCandidate) -> bool:
        """Verify that the candidate complies with scheme, domain, and transport policy."""
        pass

    @abstractmethod
    def stage_track(self, candidate: TrackCandidate, staging_dir: Path) -> Optional[Path]:
        """Download/copy candidate file into temporary staging directory."""
        pass
