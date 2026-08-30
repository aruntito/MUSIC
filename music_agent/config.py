"""
Configuration loader and data models for Music Library Agent.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class ArtistRule:
    canonical_name: str
    category_key: str
    folder_template: str
    aliases: List[str] = field(default_factory=list)


@dataclass
class LibraryConfig:
    source_dir: Path
    destination_dir: Path
    review_dir: Path
    file_naming_format: str
    sanitize_filenames: bool
    max_filename_length: int
    supported_extensions: Set[str]
    artists: Dict[str, ArtistRule] = field(default_factory=dict)
    raw_config: dict = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Optional[str or Path] = None) -> "LibraryConfig":
        if config_path is None:
            # Default location: config/library_rules.json relative to project root
            base_dir = Path(__file__).resolve().parent.parent
            config_path = base_dir / "config" / "library_rules.json"

        config_path = Path(config_path).expanduser().resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        paths = data.get("paths", {})
        source_dir = Path(os.path.expanduser(paths.get("source_dir", "~/Music/Inbox"))).resolve()
        dest_dir = Path(os.path.expanduser(paths.get("destination_dir", "~/Downloads/Songs"))).resolve()
        review_dir = Path(os.path.expanduser(paths.get("review_dir", "~/Music/Review"))).resolve()

        naming = data.get("file_naming", {})
        naming_format = naming.get("format", "{artist} - {title}.{ext}")
        sanitize = naming.get("sanitize_macos_android", True)
        max_len = int(naming.get("max_filename_length", 180))

        supported_exts = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in data.get("supported_extensions", [".mp3", ".m4a", ".flac", ".wav", ".ogg"])
        }

        # Build artist rules index
        artists_map: Dict[str, ArtistRule] = {}
        categories = data.get("categories", {})

        for cat_key, cat_val in categories.items():
            folder_template = cat_val.get("folder_template", cat_key)
            cat_artists = cat_val.get("artists", [])
            for art in cat_artists:
                name = art.get("name", "").strip()
                if not name:
                    continue
                aliases = [a.strip().lower() for a in art.get("aliases", []) if a.strip()]
                # Include the canonical name in lower-case
                if name.lower() not in aliases:
                    aliases.append(name.lower())

                rule = ArtistRule(
                    canonical_name=name,
                    category_key=cat_key,
                    folder_template=folder_template,
                    aliases=aliases,
                )
                artists_map[name.lower()] = rule

        return cls(
            source_dir=source_dir,
            destination_dir=dest_dir,
            review_dir=review_dir,
            file_naming_format=naming_format,
            sanitize_filenames=sanitize,
            max_filename_length=max_len,
            supported_extensions=supported_exts,
            artists=artists_map,
            raw_config=data,
        )
