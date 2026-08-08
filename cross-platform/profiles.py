#!/usr/bin/env python3
"""Transcode profiles, configuration loading, and path discovery filtering."""
import json
import os
from pathlib import Path

AUDIO_COPY_FALLBACK_EXTENSIONS = frozenset(
    {".avi", ".flv", ".m4v", ".mov", ".mpg", ".mpeg", ".rm", ".rmvb", ".wmv"}
)

PROFILES = {
    "h264_mp4": {"ext": ".mp4", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_avi": {"ext": ".avi", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mov": {"ext": ".mov", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_m4v": {"ext": ".m4v", "suffix": "_REDU", "out_ext": ".m4v", "mode": "video", "quality": 26},
    "h264_mpg": {"ext": ".mpg", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mpeg": {"ext": ".mpeg", "suffix": "_REDU", "out_ext": ".mpeg", "mode": "video", "quality": 26},
    "h264_flv": {"ext": ".flv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_wmv": {"ext": ".wmv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 24},
    "h264_rm": {"ext": ".rm", "suffix": "_REDU", "out_ext": ".mpg", "mode": "video", "quality": 26},
    "h264_rmvb": {"ext": ".rmvb", "suffix": "_REDU", "out_ext": ".mpg", "mode": "video", "quality": 26},
    "hevc_mp4": {"ext": ".mp4", "suffix": "_HEVC_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "hevc_mkv": {"ext": ".mkv", "suffix": "_HEVC_REDU", "out_ext": ".mkv", "mode": "video", "quality": 26},
    "hevc_mkv_legacy": {"ext": ".mkv", "suffix": "_HEVC", "out_ext": ".mkv", "mode": "video", "quality": 26},
    "mkv_shrink": {"ext": ".mkv", "suffix": "_small", "out_ext": ".mp4", "mode": "video", "quality": 28,
                   "video_filter": "scale=-2:1080,fps=30", "audio_codec": "aac", "audio_bitrate": "96k",
                   "preserve_source": True, "video_codec_family": "hevc", "preset": "veryfast"},
    "flac_mp3": {"ext": ".flac", "suffix": "", "out_ext": ".mp3", "mode": "audio"},
    "wav_mp3": {"ext": ".wav", "suffix": "", "out_ext": ".mp3", "mode": "audio"},
}


def default_config_path():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "ffmpeg-utility-scripts" / "config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ffmpeg-utility-scripts" / "config.json"


def load_user_config(config_path: Path, required: bool = False):
    if not config_path.exists():
        if required:
            raise ValueError(f"config file does not exist: {config_path}")
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to parse config file {config_path}: {exc}")
    if not isinstance(data, dict):
        raise ValueError("config file must contain a JSON object")
    return data


def normalize_skip_dirs(skip_dir_values, root: Path):
    normalized = []
    seen = set()
    for raw in skip_dir_values:
        try:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = (root / candidate).resolve()
            else:
                candidate = candidate.resolve()
        except Exception:
            continue
        key = str(candidate)
        if key not in seen:
            normalized.append(candidate)
            seen.add(key)
    return normalized


def is_path_under(parent: Path, child: Path):
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def should_skip_file(file_path: Path, skip_dirs):
    return any(is_path_under(skip_dir, file_path) for skip_dir in skip_dirs)


def is_temporary_transcode_path(path: Path):
    return ".tmp." in path.name.lower()


def is_checkpoint_internal_path(path: Path):
    """Return true for files retained inside checkpoint or quarantine trees."""
    return any(".transcode-checkpoint-" in part for part in path.parts)


def discover_paths(root: Path, recurse: bool):
    """Discover files while pruning checkpoint and quarantine directory trees."""
    if not recurse:
        yield from root.glob("*")
        return
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if ".transcode-checkpoint-" not in name]
        parent = Path(directory)
        for name in filenames:
            yield parent / name


def validate_quality_value(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if not (0 <= value <= 51):
        raise ValueError(f"{label} must be between 0 and 51")


def effective_quality(profile_name: str, profile: dict, config: dict, cli_quality):
    if profile["mode"] != "video":
        return None
    if cli_quality is not None:
        return cli_quality
    qcfg = config.get("quality", {})
    if isinstance(qcfg, dict):
        if profile_name in qcfg:
            validate_quality_value(qcfg[profile_name], f"config quality.{profile_name}")
            return qcfg[profile_name]
        if "default_video" in qcfg:
            validate_quality_value(qcfg["default_video"], "config quality.default_video")
            return qcfg["default_video"]
    elif qcfg != {}:
        validate_quality_value(qcfg, "config quality")
        return qcfg
    return profile["quality"]