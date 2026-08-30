"""
Conservative, deterministic artist and category matcher.
"""

from dataclasses import dataclass
import re
import unicodedata
from typing import Optional, List, Tuple
from music_agent.config import LibraryConfig, ArtistRule
from music_agent.metadata import AudioMetadata

FEATURING_SPLIT_REGEX = re.compile(
    r'\s+(?:feat\.?|ft\.?|featuring|with|&|,|/|vs\.?)\s+',
    re.IGNORECASE
)
PUNCTUATION_STRIP_REGEX = re.compile(r'[^\w\s]')


@dataclass
class MatchResult:
    matched: bool
    canonical_artist: Optional[str] = None
    category_key: Optional[str] = None
    target_subfolder: Optional[str] = None
    confidence: Optional[str] = None  # "exact", "alias", "high_confidence"
    reason: Optional[str] = None


def normalize_string(s: str) -> str:
    """Normalize string: unicode NFC, lowercase, remove punctuation, collapse whitespace."""
    if not s:
        return ""
    nfd = unicodedata.normalize('NFKD', s)
    ascii_str = ''.join(c for c in nfd if not unicodedata.combining(c))
    cleaned = PUNCTUATION_STRIP_REGEX.sub(' ', ascii_str.lower())
    return re.sub(r'\s+', ' ', cleaned).strip()


def extract_artist_candidates(artist_raw: Optional[str], album_artist_raw: Optional[str]) -> List[str]:
    """
    Extract ordered list of artist candidate strings to check.
    Prioritizes full string, primary before 'feat/ft/&', then album artist.
    """
    candidates = []
    seen = set()

    for raw in [artist_raw, album_artist_raw]:
        if not raw:
            continue
        raw_str = raw.strip()
        if raw_str and raw_str.lower() not in seen:
            candidates.append(raw_str)
            seen.add(raw_str.lower())

        # Check primary artist if 'feat.' / 'ft.' / '&' exists
        split_parts = FEATURING_SPLIT_REGEX.split(raw_str)
        if len(split_parts) > 1:
            primary = split_parts[0].strip()
            if primary and primary.lower() not in seen:
                candidates.append(primary)
                seen.add(primary.lower())
            # Also check other collaborating artists
            for sub_art in split_parts[1:]:
                sub_clean = sub_art.strip()
                if sub_clean and sub_clean.lower() not in seen:
                    candidates.append(sub_clean)
                    seen.add(sub_clean.lower())

    return candidates


class ArtistMatcher:
    def __init__(self, config: LibraryConfig):
        self.config = config
        self._exact_map: dict[str, ArtistRule] = {}
        self._alias_map: dict[str, ArtistRule] = {}
        self._normalized_map: dict[str, ArtistRule] = {}
        self._build_indexes()

    def _build_indexes(self):
        for rule in self.config.artists.values():
            # Exact lowercase name
            self._exact_map[rule.canonical_name.lower()] = rule
            self._normalized_map[normalize_string(rule.canonical_name)] = rule

            # Aliases
            for alias in rule.aliases:
                self._alias_map[alias.lower()] = rule
                self._normalized_map[normalize_string(alias)] = rule

    def match(self, meta: AudioMetadata) -> MatchResult:
        """
        Conservative matching pipeline:
        1. Exact normalized match against artist name / aliases
        2. Primary artist check (stripping 'feat.', 'ft.', etc.)
        3. High-confidence normalized match
        4. Otherwise -> Review / Unmatched
        """
        candidates = extract_artist_candidates(meta.artist, meta.album_artist)

        if not candidates:
            return MatchResult(
                matched=False,
                reason="No artist metadata or filename artist found"
            )

        # 1. Exact match pass
        for cand in candidates:
            cand_lower = cand.lower().strip()
            if cand_lower in self._exact_map:
                rule = self._exact_map[cand_lower]
                return self._create_match(rule, confidence="exact")

        # 2. Configured alias pass
        for cand in candidates:
            cand_lower = cand.lower().strip()
            if cand_lower in self._alias_map:
                rule = self._alias_map[cand_lower]
                return self._create_match(rule, confidence="alias")

        # 3. High-confidence normalized pass (e.g. ignoring dots/dashes/extra whitespace)
        for cand in candidates:
            norm_cand = normalize_string(cand)
            if not norm_cand or len(norm_cand) < 2:
                continue
            if norm_cand in self._normalized_map:
                rule = self._normalized_map[norm_cand]
                return self._create_match(rule, confidence="high_confidence")

        # 4. Conservative fallback: Do NOT guess on partial substring or low confidence.
        return MatchResult(
            matched=False,
            reason=f"Artist '{candidates[0]}' not in approved library rules"
        )

    def _create_match(self, rule: ArtistRule, confidence: str) -> MatchResult:
        # Determine target subfolder using folder template
        # Template can be e.g. "International/{artist}" or "Indian/Telugu"
        subfolder = rule.folder_template.replace("{artist}", rule.canonical_name)
        return MatchResult(
            matched=True,
            canonical_artist=rule.canonical_name,
            category_key=rule.category_key,
            target_subfolder=subfolder,
            confidence=confidence,
            reason=f"Matched {rule.canonical_name} ({confidence})"
        )

    def fuzzy_suggest(
        self,
        artist_name: str,
        threshold: float = 92.0,
    ) -> Optional[Tuple[str, float]]:
        """
        Advisory-only fuzzy match against the curated artist list using rapidfuzz.

        Returns (canonical_name, confidence_score) if a match is found above
        threshold, or None if no confident suggestion is available.

        IMPORTANT: This method is ADVISORY ONLY. It NEVER routes files
        automatically. The caller decides whether to surface the suggestion
        in a report. Do NOT use this for automatic file placement.

        Args:
            artist_name: Raw artist name to match.
            threshold: Minimum similarity score 0–100 (default 92.0).

        Returns:
            Tuple of (canonical_artist_name, score) or None.
        """
        try:
            from rapidfuzz import process as fuzz_process, fuzz  # noqa: PLC0415
        except ImportError:
            return None  # rapidfuzz not installed — advisory feature unavailable

        if not artist_name or not artist_name.strip():
            return None

        # Build list of all canonical names and aliases to match against
        all_names = list(self._exact_map.keys()) + list(self._alias_map.keys())
        if not all_names:
            return None

        query = normalize_string(artist_name)
        choices_normalized = [normalize_string(n) for n in all_names]

        best = fuzz_process.extractOne(
            query,
            choices_normalized,
            scorer=fuzz.WRatio,
            score_cutoff=threshold,
        )

        if best is None:
            return None

        matched_normalized = best[0]
        score = best[1]

        # Map back from normalized alias/name to canonical artist
        for raw_name, rule in {**self._exact_map, **self._alias_map}.items():
            if normalize_string(raw_name) == matched_normalized:
                return (rule.canonical_name, score)

        return None
