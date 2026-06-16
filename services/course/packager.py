from __future__ import annotations
import json
import os
from .models import CourseAssets, CourseOutline, LessonAssets


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_index_html(outline: CourseOutline, assets: CourseAssets) -> str:
    lessons_by_module: list[tuple[str, list[LessonAssets]]] = []
    module_titles = [m.title for m in outline.modules]

    grouped: dict[int, list[LessonAssets]] = {}
    for la in assets.lessons:
        grouped.setdefault(la.module_index, []).append(la)

    for mi, title in enumerate(module_titles):
        lessons_by_module.append((title, grouped.get(mi, [])))

    lessons_html = ""
    for mi, (mod_title, mod_lessons) in enumerate(lessons_by_module):
        lessons_html += f"""
        <div class="module">
            <h2>Module {mi + 1}: {_html_escape(mod_title)}</h2>"""
        for la in mod_lessons:
            video_rel = os.path.relpath(la.final_video_path or "", os.path.dirname(assets.index_html_path)) if la.final_video_path else None
            pptx_rel = os.path.relpath(la.pptx_path, os.path.dirname(assets.index_html_path))
            script_rel = os.path.relpath(la.script_path, os.path.dirname(assets.index_html_path))

            video_block = ""
            if video_rel:
                video_block = f"""
                <video controls width="100%" style="border-radius:8px;margin:12px 0">
                    <source src="{video_rel}" type="video/mp4">
                </video>"""

            lessons_html += f"""
            <div class="lesson">
                <h3>{_html_escape(la.lesson_title)}</h3>
                {video_block}
                <div class="links">
                    <a href="{pptx_rel}" download>⬇ Slides (.pptx)</a>
                    <a href="{script_rel}">📄 Script</a>
                </div>
            </div>"""
        lessons_html += "\n        </div>"

    outcomes_html = "".join(f"<li>{_html_escape(o)}</li>" for o in outline.learning_outcomes)
    prereq_html = "".join(f"<li>{_html_escape(p)}</li>" for p in outline.prerequisites)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(outline.title)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f172a; color: #e2e8f0; line-height: 1.6; }}
  header {{ background: linear-gradient(135deg, #1e293b, #0f172a);
            border-bottom: 3px solid #6366f1; padding: 48px 5%; }}
  header h1 {{ font-size: 2.4rem; color: #f8fafc; margin-bottom: 8px; }}
  header p.subtitle {{ color: #94a3b8; font-size: 1.1rem; margin-bottom: 16px; }}
  .meta {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .badge {{ background: #1e293b; border: 1px solid #334155; border-radius: 20px;
            padding: 4px 14px; font-size: 0.85rem; color: #7c3aed; font-weight: 600; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 48px 5%; }}
  section {{ margin-bottom: 48px; }}
  section h2 {{ color: #6366f1; font-size: 1.05rem; text-transform: uppercase;
               letter-spacing: 0.1em; margin-bottom: 16px; }}
  ul {{ padding-left: 20px; color: #94a3b8; }}
  ul li {{ margin-bottom: 6px; }}
  .module {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px;
             padding: 28px; margin-bottom: 24px; }}
  .module h2 {{ color: #a5b4fc; font-size: 1.2rem; margin-bottom: 16px;
               text-transform: none; letter-spacing: 0; }}
  .lesson {{ border-top: 1px solid #334155; padding-top: 16px; margin-top: 16px; }}
  .lesson h3 {{ color: #f1f5f9; font-size: 1rem; margin-bottom: 8px; }}
  .links {{ display: flex; gap: 12px; margin-top: 8px; }}
  .links a {{ color: #818cf8; text-decoration: none; font-size: 0.875rem; }}
  .links a:hover {{ color: #a5b4fc; text-decoration: underline; }}
  video {{ background: #0f172a; }}
</style>
</head>
<body>
<header>
  <h1>{_html_escape(outline.title)}</h1>
  <p class="subtitle">{_html_escape(outline.subtitle)}</p>
  <div class="meta">
    <span class="badge">{outline.difficulty.value.capitalize()}</span>
    <span class="badge">{outline.total_hours:.1f} hours</span>
    <span class="badge">{len(outline.modules)} modules</span>
    <span class="badge">{outline.target_audience}</span>
  </div>
</header>
<main>
  <section>
    <h2>About this course</h2>
    <p style="color:#94a3b8">{_html_escape(outline.description)}</p>
  </section>
  <section>
    <h2>What you'll learn</h2>
    <ul>{outcomes_html}</ul>
  </section>
  <section>
    <h2>Prerequisites</h2>
    <ul>{prereq_html}</ul>
  </section>
  <section>
    <h2>Course content</h2>
    {lessons_html}
  </section>
</main>
</body>
</html>"""


def package_course(outline: CourseOutline, assets: CourseAssets) -> str:
    html = build_index_html(outline, assets)
    with open(assets.index_html_path, "w", encoding="utf-8") as f:
        f.write(html)

    manifest = {
        "course_title": outline.title,
        "difficulty": outline.difficulty.value,
        "total_hours": outline.total_hours,
        "modules": len(outline.modules),
        "lessons": len(assets.lessons),
        "output_dir": assets.output_dir,
        "index": assets.index_html_path,
    }
    manifest_path = os.path.join(assets.output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return assets.index_html_path
