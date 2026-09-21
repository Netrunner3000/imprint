from __future__ import annotations
import os
import subprocess
import tempfile
from .models import LessonAssets


def _ffmpeg(*args: str) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-1000:]}")
    return result


def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 60.0


def assemble_slides_only(
    slide_images: list[str],
    audio_path: str | None,
    output_path: str,
    lesson_title: str,
) -> str:
    """
    Create a video from slide PNGs + optional audio.
    Each slide is shown for equal time across the total audio duration.
    Without audio, each slide is shown for 8 seconds.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if audio_path and os.path.exists(audio_path):
        total_duration = _get_audio_duration(audio_path)
    else:
        total_duration = len(slide_images) * 8.0

    slide_duration = total_duration / max(len(slide_images), 1)

    with tempfile.TemporaryDirectory() as tmp:
        concat_file = os.path.join(tmp, "slides.txt")
        with open(concat_file, "w") as f:
            for img in slide_images:
                abs_img = os.path.abspath(img)
                f.write(f"file '{abs_img}'\n")
                f.write(f"duration {slide_duration:.3f}\n")
            # ffmpeg concat demuxer needs last entry repeated
            if slide_images:
                f.write(f"file '{os.path.abspath(slide_images[-1])}'\n")

        silent_video = os.path.join(tmp, "slides_video.mp4")
        _ffmpeg(
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            silent_video,
        )

        if audio_path and os.path.exists(audio_path):
            _ffmpeg(
                "-i", silent_video, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", output_path,
            )
        else:
            os.replace(silent_video, output_path)

    return output_path


def composite_avatar_video(
    slides_video_path: str,
    avatar_video_path: str,
    output_path: str,
    position: str = "bottom-right",
    avatar_scale: float = 0.28,
) -> str:
    """
    Composite the avatar video as a picture-in-picture overlay on the slides video.
    The avatar appears in the corner so slides remain fully visible.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Avatar PiP dimensions relative to 1920x1080
    aw = int(1920 * avatar_scale)
    ah = int(aw * 9 / 16)
    margin = 30

    positions = {
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "top-left": f"{margin}:{margin}",
    }
    overlay_pos = positions.get(position, positions["bottom-right"])

    filter_complex = (
        f"[1:v]scale={aw}:{ah}[avatar];"
        f"[0:v][avatar]overlay={overlay_pos}[out]"
    )

    _ffmpeg(
        "-i", slides_video_path,
        "-i", avatar_video_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        output_path,
    )

    return output_path


def assemble_lesson_video(assets: LessonAssets) -> str:
    """
    Full assembly pipeline for one lesson.
    Returns path to the final MP4.
    """
    lesson_dir = os.path.dirname(assets.script_path)
    slides_video = os.path.join(lesson_dir, "slides_video.mp4")
    final_path = os.path.join(lesson_dir, "lesson_final.mp4")

    assemble_slides_only(
        slide_images=assets.slide_images,
        audio_path=assets.audio_path,
        output_path=slides_video,
        lesson_title=assets.lesson_title,
    )

    if assets.avatar_video_path and os.path.exists(assets.avatar_video_path):
        composite_avatar_video(
            slides_video_path=slides_video,
            avatar_video_path=assets.avatar_video_path,
            output_path=final_path,
        )
    else:
        os.replace(slides_video, final_path)

    return final_path
