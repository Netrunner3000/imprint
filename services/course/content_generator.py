from __future__ import annotations
import json
import os
import anthropic
from .models import (
    CourseRequest, CourseOutline, DifficultyLevel,
    Module, Lesson, Slide, QuizQuestion,
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_SYSTEM_PROMPT = """You are an expert instructional designer and course creator with 15 years of
experience building professional online courses for platforms like Coursera, edX, and Udemy.
You write clear, engaging, pedagogically sound content that is accurate and well-structured.
Always respond with valid JSON matching the exact schema requested. No markdown fences, no extra keys."""


def generate_outline(req: CourseRequest) -> CourseOutline:
    schema = {
        "title": "string",
        "subtitle": "string",
        "description": "string (2-3 sentences)",
        "difficulty": req.difficulty.value,
        "target_audience": "string",
        "prerequisites": ["string"],
        "learning_outcomes": ["string (6-8 items)"],
        "total_hours": "number",
        "modules": [
            {
                "title": "string",
                "description": "string",
                "lessons": [
                    {"title": "string", "learning_objectives": ["string"], "duration_minutes": "number"}
                ],
            }
        ],
    }

    prompt = f"""Create a professional course outline for the following:

Topic: {req.topic}
Difficulty: {req.difficulty.value}
Target audience: {req.target_audience}
Number of modules: {req.num_modules}
Lessons per module: {req.lessons_per_module}
Lesson duration: {req.lesson_duration_minutes} minutes each

Return a JSON object matching this schema exactly:
{json.dumps(schema, indent=2)}

Each module must have exactly {req.lessons_per_module} lessons.
Do not include 'slides', 'script', or 'quiz' fields — those come later.
"""

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    data = json.loads(raw)

    modules = []
    for mod_data in data["modules"]:
        lessons = [
            Lesson(
                title=l["title"],
                learning_objectives=l.get("learning_objectives", []),
                script="",
                slides=[],
                quiz=[],
                duration_minutes=l.get("duration_minutes", req.lesson_duration_minutes),
            )
            for l in mod_data["lessons"]
        ]
        modules.append(Module(title=mod_data["title"], description=mod_data["description"], lessons=lessons))

    return CourseOutline(
        title=data["title"],
        subtitle=data.get("subtitle", ""),
        description=data["description"],
        difficulty=DifficultyLevel(data["difficulty"]),
        target_audience=data["target_audience"],
        prerequisites=data.get("prerequisites", []),
        learning_outcomes=data.get("learning_outcomes", []),
        modules=modules,
        total_hours=data.get("total_hours", req.num_modules * req.lessons_per_module * req.lesson_duration_minutes / 60),
    )


def generate_lesson(
    course_title: str,
    module_title: str,
    lesson_title: str,
    objectives: list[str],
    duration_minutes: int,
    difficulty: str,
) -> tuple[str, list[Slide], list[QuizQuestion]]:
    """Returns (script, slides, quiz) for a single lesson."""

    slide_count = max(4, duration_minutes // 3)
    quiz_count = min(5, max(3, duration_minutes // 5))

    prompt = f"""Write a complete lesson for an online course.

Course: {course_title}
Module: {module_title}
Lesson: {lesson_title}
Difficulty: {difficulty}
Duration: {duration_minutes} minutes
Learning objectives:
{chr(10).join(f"- {o}" for o in objectives)}

Return a JSON object with exactly these keys:

{{
  "script": "The full narration script the AI presenter will speak. Conversational, engaging, ~{duration_minutes * 130} words. Include transitions between slides.",
  "slides": [
    {{
      "title": "Slide title",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"],
      "speaker_notes": "What the presenter says specifically during this slide (~2-3 sentences)"
    }}
  ],
  "quiz": [
    {{
      "question": "Question text",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "Why this answer is correct"
    }}
  ]
}}

Generate exactly {slide_count} slides and {quiz_count} quiz questions.
The script should flow naturally across all slides.
"""

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    data = json.loads(raw)

    slides = [
        Slide(
            title=s["title"],
            bullets=s.get("bullets", []),
            speaker_notes=s.get("speaker_notes", ""),
        )
        for s in data["slides"]
    ]

    quiz = [
        QuizQuestion(
            question=q["question"],
            options=q["options"],
            correct_index=q["correct_index"],
            explanation=q.get("explanation", ""),
        )
        for q in data["quiz"]
    ]

    return data["script"], slides, quiz
