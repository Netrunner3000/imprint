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

from agents.course import CourseAgent
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
    parser.add_argument("--yes", action="store_true",
                        help="Skip the cost confirmation (for scripted runs)")
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

    # ── Cost estimate + confirmation ─────────────────────────────────────
    # This CLI drives the most call-heavy paid workflow in the repo, and it
    # used to spend with no estimate, no confirmation and no usage row — a
    # course run was invisible to the GUI's daily cap. The estimate is an
    # upper bound: 1 outline call (≤4096 out) plus modules × lessons lesson
    # calls (≤8192 out), input ~1.5k tokens per call.
    from services.database import init_db
    from services.usage_tracker import UsageTracker
    from services.course.content_generator import (
        COURSE_MODEL, reset_usage_tally, usage_tally)

    init_db()
    tracker = UsageTracker()
    calls = 1 + args.modules * args.lessons
    est_in = calls * 1500
    est_out = 4096 + args.modules * args.lessons * 8192
    est_eur = tracker.calculate_cost_eur("anthropic", COURSE_MODEL, est_in, est_out)
    today = tracker.get_today_total()

    print(f"Estimated Anthropic cost (upper bound): ~€{est_eur:.2f} "
          f"({calls} calls, ≤{est_out:,} output tokens)")
    print(f"Spent today across the studio: €{today:.2f}")
    if args.voice == "elevenlabs":
        print("ElevenLabs narration is billed per character against your "
              "account's quota — not included in the estimate above.")
    if args.avatar in ("heygen", "synthesia"):
        print(f"{args.avatar} renders are billed per video minute by the "
              "provider — not included in the estimate above.")
    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            sys.exit("Cancelled — nothing was spent.")

    reset_usage_tally()
    try:
        assets = agent.run(request)
    finally:
        # Log whatever was actually spent — also on failure partway through,
        # so the GUI's "Cost Today" and daily cap see this run either way.
        tally = usage_tally()
        if tally["calls"]:
            entry = tracker.log_request(
                agent="course", backend="anthropic", model=COURSE_MODEL,
                prompt_text=f"course: {args.topic}", response_text="",
                usage={"input_tokens": tally["input_tokens"],
                       "output_tokens": tally["output_tokens"]})
            print(f"\nLogged €{entry['cost_eur']:.4f} "
                  f"({tally['calls']} calls, {tally['input_tokens']:,} in / "
                  f"{tally['output_tokens']:,} out) to the studio usage log.")

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
