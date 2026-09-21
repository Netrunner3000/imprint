from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuizQuestion(BaseModel):
    question: str
    options: list[str]  # exactly 4 options
    correct_index: int
    explanation: str


class Slide(BaseModel):
    title: str
    bullets: list[str]
    speaker_notes: str  # what the presenter says during this slide


class Lesson(BaseModel):
    title: str
    learning_objectives: list[str]
    script: str          # full narration the AI tutor will speak
    slides: list[Slide]
    quiz: list[QuizQuestion]
    duration_minutes: int


class Module(BaseModel):
    title: str
    description: str
    lessons: list[Lesson]


class CourseOutline(BaseModel):
    title: str
    subtitle: str
    description: str
    difficulty: DifficultyLevel
    target_audience: str
    prerequisites: list[str]
    learning_outcomes: list[str]
    modules: list[Module]
    total_hours: float


class CourseRequest(BaseModel):
    topic: str
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER
    target_audience: str = "general learners"
    num_modules: int = Field(default=4, ge=1, le=12)
    lessons_per_module: int = Field(default=3, ge=1, le=10)
    lesson_duration_minutes: int = Field(default=15, ge=5, le=60)
    output_dir: str = "output/courses"


class LessonAssets(BaseModel):
    lesson_title: str
    module_index: int
    lesson_index: int
    script_path: str
    slide_images: list[str]        # PNG paths, one per slide
    pptx_path: str
    audio_path: Optional[str] = None
    avatar_video_path: Optional[str] = None
    final_video_path: Optional[str] = None


class CourseAssets(BaseModel):
    course_title: str
    outline_path: str              # JSON of CourseOutline
    lessons: list[LessonAssets]
    index_html_path: str
    output_dir: str
