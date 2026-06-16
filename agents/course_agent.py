from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from services.course.models import (
    CourseRequest, CourseOutline, CourseAssets, LessonAssets, DifficultyLevel,
)
from services.course import content_generator, slide_generator, video_assembler, packager
from providers.avatar.base import AvatarProvider, AvatarConfig
from providers.voice.base import VoiceProvider, VoiceConfig


def _provider_from_name(provider_name: str, kind: str):
    """Lazy-load a provider by name string."""
    name = provider_name.lower()

    if kind == "avatar":
        if name == "mock":
            from providers.avatar.mock import MockAvatarProvider
            return MockAvatarProvider()
        if name == "heygen":
            from providers.avatar.heygen import HeyGenProvider
            return HeyGenProvider()
        if name == "synthesia":
            from providers.avatar.synthesia import SynthesiaProvider
            return SynthesiaProvider()
        raise ValueError(f"Unknown avatar provider: {provider_name!r}. Choose: mock, heygen, synthesia")

    if kind == "voice":
        if name == "mock":
            from providers.voice.mock import MockVoiceProvider
            return MockVoiceProvider()
        if name == "elevenlabs":
            from providers.voice.elevenlabs import ElevenLabsProvider
            return ElevenLabsProvider()
        raise ValueError(f"Unknown voice provider: {provider_name!r}. Choose: mock, elevenlabs")

    raise ValueError(f"Unknown provider kind: {kind}")


class CourseAgent:
    """
    Orchestrates the full course generation pipeline:
      1. Generate outline (Claude)
      2. For each lesson: generate content → render slides → synthesize voice → generate avatar video → assemble
      3. Package into a browsable HTML course
    """

    def __init__(
        self,
        avatar_provider: str | AvatarProvider = "mock",
        voice_provider: str | VoiceProvider = "mock",
        avatar_config: Optional[AvatarConfig] = None,
        voice_config: Optional[VoiceConfig] = None,
        verbose: bool = True,
    ):
        self.avatar = (
            avatar_provider if isinstance(avatar_provider, AvatarProvider)
            else _provider_from_name(avatar_provider, "avatar")
        )
        self.voice = (
            voice_provider if isinstance(voice_provider, VoiceProvider)
            else _provider_from_name(voice_provider, "voice")
        )
        self.avatar_config = avatar_config or AvatarConfig()
        self.voice_config = voice_config or VoiceConfig()
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"[CourseAgent] {msg}")

    def build_messages(self, prompt: str) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a professional course creation agent. You can design and build "
                    "full online courses with video lessons, slides, scripts, and quizzes. "
                    "Ask the user for topic, difficulty, target audience, and scope if not provided."
                ),
            },
            {"role": "user", "content": prompt},
        ]

    def run(self, request: CourseRequest) -> CourseAssets:
        """Execute the full pipeline. Returns CourseAssets with all paths."""
        base_dir = os.path.join(request.output_dir, _safe_name(request.topic))
        os.makedirs(base_dir, exist_ok=True)

        # 1. Generate outline
        self._log(f"Generating outline for: {request.topic!r}")
        outline = content_generator.generate_outline(request)
        outline_path = os.path.join(base_dir, "outline.json")
        with open(outline_path, "w") as f:
            f.write(outline.model_dump_json(indent=2))
        self._log(f"Outline saved → {outline_path}")

        # Title slide
        title_slide_path = os.path.join(base_dir, "title_slide.png")
        slide_generator.render_title_slide(outline, title_slide_path)

        lesson_assets_list: list[LessonAssets] = []

        for mi, module in enumerate(outline.modules):
            for li, lesson in enumerate(module.lessons):
                self._log(f"Processing M{mi+1}L{li+1}: {lesson.title}")
                la = self._process_lesson(
                    outline=outline,
                    module_title=module.title,
                    lesson=lesson,
                    module_index=mi,
                    lesson_index=li,
                    base_dir=base_dir,
                )
                lesson_assets_list.append(la)

        assets = CourseAssets(
            course_title=outline.title,
            outline_path=outline_path,
            lessons=lesson_assets_list,
            index_html_path=os.path.join(base_dir, "index.html"),
            output_dir=base_dir,
        )

        # 2. Package
        self._log("Packaging course...")
        index_path = packager.package_course(outline, assets)
        self._log(f"Done → {index_path}")

        return assets

    def _process_lesson(
        self,
        outline: CourseOutline,
        module_title: str,
        lesson,
        module_index: int,
        lesson_index: int,
        base_dir: str,
    ) -> LessonAssets:
        lesson_dir = os.path.join(
            base_dir,
            f"m{module_index+1:02d}",
            f"l{lesson_index+1:02d}_{_safe_name(lesson.title)}",
        )
        os.makedirs(lesson_dir, exist_ok=True)

        # Generate lesson content
        script, slides, quiz = content_generator.generate_lesson(
            course_title=outline.title,
            module_title=module_title,
            lesson_title=lesson.title,
            objectives=lesson.learning_objectives,
            duration_minutes=lesson.duration_minutes,
            difficulty=outline.difficulty.value,
        )

        # Save script
        script_path = os.path.join(lesson_dir, "script.txt")
        with open(script_path, "w") as f:
            f.write(script)

        # Save quiz
        quiz_path = os.path.join(lesson_dir, "quiz.json")
        with open(quiz_path, "w") as f:
            json.dump([q.model_dump() for q in quiz], f, indent=2)

        # Render slide images
        slide_images = slide_generator.generate_lesson_slides(
            slides=slides,
            course_title=outline.title,
            lesson_dir=os.path.join(lesson_dir, "slides"),
        )

        # Generate PPTX
        pptx_path = os.path.join(lesson_dir, "slides.pptx")
        slide_generator.generate_pptx(slides, outline.title, lesson.title, pptx_path)

        la = LessonAssets(
            lesson_title=lesson.title,
            module_index=module_index,
            lesson_index=lesson_index,
            script_path=script_path,
            slide_images=slide_images,
            pptx_path=pptx_path,
        )

        # Synthesize voice
        audio_path = os.path.join(lesson_dir, "audio.mp3")
        try:
            self._log(f"  Synthesizing voice ({self.voice.name})...")
            self.voice.synthesize(script, audio_path, self.voice_config)
            la.audio_path = audio_path
        except Exception as e:
            self._log(f"  Voice synthesis failed: {e} — continuing without audio")

        # Generate avatar video
        avatar_video_path = os.path.join(lesson_dir, "avatar.mp4")
        try:
            self._log(f"  Generating avatar ({self.avatar.name})...")
            self.avatar.generate_video(script, avatar_video_path, self.avatar_config)
            la.avatar_video_path = avatar_video_path
        except Exception as e:
            self._log(f"  Avatar generation failed: {e} — continuing without avatar")

        # Assemble final video
        try:
            self._log("  Assembling final video...")
            final_path = video_assembler.assemble_lesson_video(la)
            la.final_video_path = final_path
        except Exception as e:
            self._log(f"  Video assembly failed: {e}")

        return la


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s.lower()).strip("_")
