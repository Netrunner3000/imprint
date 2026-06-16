"""
CLI runner for the Course Agent.

Usage examples:
    # Full mock run (no API keys needed except ANTHROPIC_API_KEY):
    python run_course.py --topic "Machine Learning Fundamentals" --modules 2 --lessons 2

    # With ElevenLabs voice:
    python run_course.py --topic "Python for Beginners" --voice elevenlabs

    # With HeyGen avatar:
    python run_course.py --topic "Data Science" --avatar heygen --voice elevenlabs

    # Advanced course:
    python run_course.py --topic "Kubernetes" --difficulty advanced --audience "DevOps engineers"
"""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("Error: ANTHROPIC_API_KEY is not set. Add it to your .env file.")

sys.path.insert(0, os.path.dirname(__file__))

from agents.course_agent import CourseAgent
from services.course.models import CourseRequest, DifficultyLevel


def main():
    parser = argparse.ArgumentParser(description="Generate a professional AI course")
    parser.add_argument("--topic", required=True, help="Course topic")
    parser.add_argument("--difficulty", default="beginner",
                        choices=["beginner", "intermediate", "advanced"])
    parser.add_argument("--audience", default="general learners", help="Target audience")
    parser.add_argument("--modules", type=int, default=2, help="Number of modules (1-12)")
    parser.add_argument("--lessons", type=int, default=2, help="Lessons per module (1-10)")
    parser.add_argument("--duration", type=int, default=15, help="Minutes per lesson (5-60)")
    parser.add_argument("--avatar", default="mock",
                        choices=["mock", "heygen", "synthesia"],
                        help="Avatar video provider")
    parser.add_argument("--voice", default="mock",
                        choices=["mock", "elevenlabs"],
                        help="Voice synthesis provider")
    parser.add_argument("--output", default="output/courses", help="Output directory")
    args = parser.parse_args()

    request = CourseRequest(
        topic=args.topic,
        difficulty=DifficultyLevel(args.difficulty),
        target_audience=args.audience,
        num_modules=args.modules,
        lessons_per_module=args.lessons,
        lesson_duration_minutes=args.duration,
        output_dir=args.output,
    )

    agent = CourseAgent(
        avatar_provider=args.avatar,
        voice_provider=args.voice,
        verbose=True,
    )

    print(f"\nGenerating course: {args.topic!r}")
    print(f"  Difficulty : {args.difficulty}")
    print(f"  Modules    : {args.modules} × {args.lessons} lessons")
    print(f"  Avatar     : {args.avatar}")
    print(f"  Voice      : {args.voice}")
    print()

    assets = agent.run(request)

    print(f"\n{'='*60}")
    print(f"Course generated successfully!")
    print(f"  Output dir : {assets.output_dir}")
    print(f"  Open in browser: file://{os.path.abspath(assets.index_html_path)}")
    print(f"  Lessons generated: {len(assets.lessons)}")
    for la in assets.lessons:
        status = "✓ video" if la.final_video_path else "✗ no video"
        print(f"    [{status}] {la.lesson_title}")


if __name__ == "__main__":
    main()
