"""
agents/subtitle_agent.py
Generates SRT and ASS subtitle files from narration scripts + audio durations.
"""

from pathlib import Path

from config.settings import (
    SUBTITLE_FONT_SIZE,
    SUBTITLE_COLOR,
    SUBTITLE_BORDER_COLOR,
    SUBTITLE_BORDER_WIDTH,
    WORDS_PER_SUBTITLE_BLOCK,
)
from utils.logger import get_logger

logger = get_logger("subtitle_agent")


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds → SRT timestamp HH:MM:SS,mmm."""
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert float seconds → ASS timestamp H:MM:SS.cc."""
    cs = int((seconds % 1) * 100)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class SubtitleAgent:
    """Generates subtitle files aligned to voice audio durations."""

    def generate(
        self,
        scripts: list[dict],
        audio_durations: list[float],
        workspace: Path,
    ) -> dict[str, Path]:
        """
        Build SRT and ASS subtitle files.

        Args:
            scripts: Scene script dicts with narration text
            audio_durations: Actual duration of each scene's audio (seconds)
            workspace: Working directory for output

        Returns:
            {"srt": Path, "ass": Path}
        """
        sub_dir = workspace / "subtitles"
        sub_dir.mkdir(parents=True, exist_ok=True)

        srt_blocks = []
        ass_events = []
        counter = 1
        cursor = 0.0

        for script, duration in zip(scripts, audio_durations):
            words = script["narration"].split()
            block_size = WORDS_PER_SUBTITLE_BLOCK
            n_blocks = max(1, len(words) // block_size)
            time_per_block = duration / n_blocks

            for b in range(n_blocks):
                start = cursor + b * time_per_block
                end = start + time_per_block
                block_words = words[b * block_size: (b + 1) * block_size]
                text = " ".join(block_words)

                # SRT entry
                srt_blocks.append(
                    f"{counter}\n"
                    f"{_seconds_to_srt_time(start)} --> {_seconds_to_srt_time(end)}\n"
                    f"{text}\n"
                )

                # ASS event line
                ass_events.append(
                    f"Dialogue: 0,{_seconds_to_ass_time(start)},"
                    f"{_seconds_to_ass_time(end)},Default,,0,0,0,,{text}"
                )

                counter += 1

            cursor += duration

        srt_path = sub_dir / "subtitles.srt"
        ass_path = sub_dir / "subtitles.ass"

        srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")
        ass_path.write_text(
            self._ass_header() + "\n".join(ass_events), encoding="utf-8"
        )

        logger.info(f"Generated {counter-1} subtitle blocks | SRT + ASS written")
        return {"srt": srt_path, "ass": ass_path}

    def _ass_header(self) -> str:
        """Return ASS file header with styling."""
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
            "Bold, Italic, Alignment, BorderStyle, Outline, Shadow, MarginV\n"
            f"Style: Default,Arial,{SUBTITLE_FONT_SIZE},"
            f"&H00FFFFFF,&H00000000,1,0,2,1,{SUBTITLE_BORDER_WIDTH},0,50\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
