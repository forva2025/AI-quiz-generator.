from typing import List, Optional
from urllib.parse import urlparse, parse_qs

import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

YOUTUBE_OEMBED = "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"


def extract_video_id(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.endswith("youtu.be"):
            video_id = parsed.path.lstrip("/")
            return video_id or None
        if "youtube.com" in host:
            if parsed.path.startswith("/watch"):
                query_params = parse_qs(parsed.query)
                return query_params.get("v", [None])[0]
            if parsed.path.startswith("/embed/"):
                return parsed.path.split("/")[-1] or None
        return None
    except Exception:
        return None


def fetch_transcript(video_id: str, languages: Optional[List[str]] = None) -> str:
    languages = languages or ["en", "en-US", "en-GB"]
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                lines = transcript.fetch()
                return " ".join(segment.get("text", "").strip() for segment in lines).strip()
            except Exception:
                continue
        for lang in languages:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                lines = transcript.fetch()
                return " ".join(segment.get("text", "").strip() for segment in lines).strip()
            except Exception:
                continue
        for transcript in transcript_list:
            try:
                lines = transcript.fetch()
                return " ".join(segment.get("text", "").strip() for segment in lines).strip()
            except Exception:
                continue
        return ""
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return ""


def fetch_title(video_id: str) -> Optional[str]:
    try:
        resp = requests.get(YOUTUBE_OEMBED.format(video_id=video_id), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("title")
        return None
    except Exception:
        return None