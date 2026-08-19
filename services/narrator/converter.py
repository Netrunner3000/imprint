import os
import re
import sys
import json
import time
import random
import shutil
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
import pypdf
from ebooklib import epub
from bs4 import BeautifulSoup
from openai import OpenAI, AuthenticationError
import tiktoken


# ------------------------------------------------------
# CONFIG
# ------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BASE_DIR / "books"
OUTPUT_ROOT = Path("/Users/as/Documents/Files/Narrator")

TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "alloy"
TTS_INSTRUCTIONS = None

RETRIES = 2
MAX_WORKERS = 4
MANIFEST_SAVE_EVERY = 5
MAX_INPUT_TOKENS_PER_CHUNK = 1500

MANIFEST_FILENAME = "manifest.json"
TEMP_DIRNAME = "temp_audio"
FFMPEG_CONCAT_FILENAME = "ffmpeg_concat.txt"

USD_PER_1M_INPUT_TOKENS = 0.60
USD_PER_1M_OUTPUT_AUDIO_TOKENS = 12.00
EUR_PER_USD_FALLBACK = 0.855

# Lazy OpenAI client: importing this module must have NO side effects so it can
# be bundled into the host app (and PyInstaller) without needing a key at import time.
_ENV_PATH = BASE_DIR / ".env"
client = None


def get_client():
    """Create the OpenAI client on first use. Reads OPENAI_API_KEY from the host
    app's environment, falling back to a .env in the cwd, then to one beside this module."""
    global client
    if client is None:
        if not os.getenv("OPENAI_API_KEY"):
            load_dotenv(override=False)  # e.g. the project root .env
        if not os.getenv("OPENAI_API_KEY") and _ENV_PATH.exists():
            load_dotenv(dotenv_path=_ENV_PATH, override=False)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found. Set it in the app's environment or in a "
                f".env file (cwd or {_ENV_PATH})."
            )
        client = OpenAI(api_key=api_key)
    return client


# ------------------------------------------------------
# UTILITIES
# ------------------------------------------------------

def print_progress(current: int, total: int, prefix: str = ""):
    bar_len = 30
    ratio = current / total if total else 1
    filled = int(ratio * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    percent = ratio * 100
    print(f"\r{prefix}[{bar}] {percent:5.1f}% ({current}/{total})", end="", flush=True)
    if current >= total:
        print()


def clean_name(raw: str) -> str:
    raw = os.path.basename(raw)
    raw = raw.rsplit(".", 1)[0]
    raw = re.sub(r"\[[^\]]*\]", "", raw).strip()
    raw = re.sub(r"[^A-Za-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw)
    return raw.strip("_") or "Book"


def light_normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]

    cleaned = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def json_dump(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def json_load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_ffmpeg_available() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    raise RuntimeError(
        "ffmpeg was not found on your PATH.\n"
        "Install ffmpeg and make sure the `ffmpeg` command works in your terminal."
    )


def ensure_ffprobe_available() -> str:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        return ffprobe_path
    raise RuntimeError(
        "ffprobe was not found on your PATH.\n"
        "It normally ships with ffmpeg."
    )


def ensure_ebook_convert_available() -> str:
    cmd = shutil.which("ebook-convert")
    if cmd:
        return cmd

    mac_path = Path("/Applications/calibre.app/Contents/MacOS/ebook-convert")
    if mac_path.exists():
        return str(mac_path)

    raise RuntimeError(
        "ebook-convert was not found.\n"
        "Install Calibre and make sure ebook-convert is callable from your terminal.\n"
        "On macOS it is often here:\n"
        "/Applications/calibre.app/Contents/MacOS/ebook-convert"
    )


def wipe_book_state(book_out_dir: Path):
    temp_dir = book_out_dir / TEMP_DIRNAME
    manifest_path = book_out_dir / MANIFEST_FILENAME

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    if manifest_path.exists():
        manifest_path.unlink()


def matches_force_target(fp: Path, book_name: str, force_target: str | None) -> bool:
    if not force_target:
        return False

    candidates = {
        fp.name.lower(),
        fp.stem.lower(),
        book_name.lower(),
    }
    return force_target.lower() in candidates


# ------------------------------------------------------
# TEXT EXTRACTION
# ------------------------------------------------------

def extract_pdf(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    text = ""
    for page in reader.pages:
        text += (page.extract_text() or "") + "\n"
    return text


def extract_epub(path: Path) -> str:
    book = epub.read_epub(str(path))
    sections = []

    for item in book.get_items():
        if isinstance(item, epub.EpubHtml) and not isinstance(item, epub.EpubNav):
            soup = BeautifulSoup(item.get_body_content(), "html.parser")

            for tag in soup(["script", "style", "header", "footer", "noscript"]):
                tag.extract()

            txt = soup.get_text(separator="\n", strip=True)
            if txt:
                sections.append(txt)

    return "\n\n".join(sections)


def convert_mobi_to_epub(mobi_path: Path, work_dir: Path) -> Path:
    ebook_convert = ensure_ebook_convert_available()
    converted = work_dir / f"{mobi_path.stem}.converted.epub"

    cmd = [
        ebook_convert,
        str(mobi_path),
        str(converted),
    ]

    print(f"  Converting MOBI -> EPUB with Calibre: {mobi_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0 or not converted.exists():
        raise RuntimeError(
            "ebook-convert failed.\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )

    return converted


def load_text(path: Path, work_dir: Path | None = None) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".epub":
        return extract_epub(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".mobi":
        if work_dir is None:
            raise ValueError("work_dir is required for .mobi conversion")
        epub_path = convert_mobi_to_epub(path, work_dir)
        return extract_epub(epub_path)

    raise ValueError(f"Unsupported file type: {path}")


# ------------------------------------------------------
# TOKEN / COST HELPERS
# ------------------------------------------------------

def get_token_encoder():
    try:
        return tiktoken.encoding_for_model("gpt-4o-mini")
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str) -> int:
    enc = get_token_encoder()
    return len(enc.encode(text))


def estimate_audio_tokens_from_seconds(seconds: float) -> int:
    return int(round(seconds * 20))


def estimate_costs_usd(text_tokens: int, audio_tokens: int) -> dict:
    input_cost = (text_tokens / 1_000_000) * USD_PER_1M_INPUT_TOKENS
    output_cost = (audio_tokens / 1_000_000) * USD_PER_1M_OUTPUT_AUDIO_TOKENS
    total = input_cost + output_cost
    return {
        "input_usd": input_cost,
        "output_usd": output_cost,
        "total_usd": total,
    }


def usd_to_eur(usd_amount: float, eur_per_usd: float = EUR_PER_USD_FALLBACK) -> float:
    return usd_amount * eur_per_usd


def estimate_audio_seconds_from_text(text: str, words_per_minute: float = 150.0) -> float:
    words = len(text.split())
    minutes = words / words_per_minute if words_per_minute else 0
    return minutes * 60.0


def get_audio_duration_seconds(audio_path: Path) -> float:
    ensure_ffprobe_available()

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")

    return float(result.stdout.strip())


def print_cost_estimate(label: str, text_tokens: int, audio_seconds: float):
    audio_tokens = estimate_audio_tokens_from_seconds(audio_seconds)
    costs = estimate_costs_usd(text_tokens, audio_tokens)

    total_eur = usd_to_eur(costs["total_usd"])
    input_eur = usd_to_eur(costs["input_usd"])
    output_eur = usd_to_eur(costs["output_usd"])

    print(f"  {label}")
    print(f"    Text tokens: ~{text_tokens:,}")
    print(f"    Audio duration: ~{audio_seconds/60:.1f} min")
    print(f"    Cost estimate:")
    print(f"      Input:  ${costs['input_usd']:.4f} / €{input_eur:.4f}")
    print(f"      Output: ${costs['output_usd']:.4f} / €{output_eur:.4f}")
    print(f"      Total:  ${costs['total_usd']:.4f} / €{total_eur:.4f}")


# ------------------------------------------------------
# TOKEN-SAFE CHUNKING
# ------------------------------------------------------

def chunk_text(text: str, max_tokens: int = MAX_INPUT_TOKENS_PER_CHUNK) -> list[str]:
    enc = get_token_encoder()
    words = text.split()

    chunks = []
    current_words = []
    current_text = ""

    for word in words:
        candidate_text = f"{current_text} {word}".strip()
        token_count = len(enc.encode(candidate_text))

        if token_count <= max_tokens:
            current_words.append(word)
            current_text = candidate_text
        else:
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = [word]
                current_text = word
            else:
                chunks.append(word)
                current_words = []
                current_text = ""

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


# ------------------------------------------------------
# MANIFEST
# ------------------------------------------------------

def build_manifest(book_name: str, source_file: Path, chunks: list[str]) -> dict:
    return {
        "book_name": book_name,
        "source_file": str(source_file),
        "tts_model": TTS_MODEL,
        "tts_voice": TTS_VOICE,
        "tts_instructions": TTS_INSTRUCTIONS,
        "max_input_tokens_per_chunk": MAX_INPUT_TOKENS_PER_CHUNK,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "index": i,
                "filename": f"chunk_{i}.mp3",
                "status": "pending",
                "text_word_count": len(chunk.split()),
            }
            for i, chunk in enumerate(chunks)
        ],
    }


def load_or_create_manifest(
    manifest_path: Path,
    book_name: str,
    source_file: Path,
    chunks: list[str]
) -> dict:
    expected = build_manifest(book_name, source_file, chunks)

    if not manifest_path.exists():
        json_dump(manifest_path, expected)
        return expected

    existing = json_load(manifest_path)

    compatible = (
        existing.get("book_name") == expected["book_name"]
        and existing.get("source_file") == expected["source_file"]
        and existing.get("tts_model") == expected["tts_model"]
        and existing.get("tts_voice") == expected["tts_voice"]
        and existing.get("tts_instructions") == expected["tts_instructions"]
        and existing.get("max_input_tokens_per_chunk") == expected["max_input_tokens_per_chunk"]
        and existing.get("total_chunks") == expected["total_chunks"]
    )

    if not compatible:
        print("  ⚠️ Existing manifest does not match current run.")
        print("  Rebuilding manifest from scratch.")
        json_dump(manifest_path, expected)
        return expected

    return existing


def sync_manifest_with_files(manifest: dict, temp_dir: Path) -> dict:
    for entry in manifest["chunks"]:
        chunk_file = temp_dir / entry["filename"]
        if chunk_file.exists() and chunk_file.stat().st_size > 0:
            entry["status"] = "done"
        else:
            entry["status"] = "pending"
    return manifest


# ------------------------------------------------------
# TTS WITH RETRIES
# ------------------------------------------------------

def generate_tts_chunk(text: str, temp_path: Path, retries: int = RETRIES) -> bool:
    for attempt in range(1, retries + 1):
        try:
            kwargs = {
                "model": TTS_MODEL,
                "voice": TTS_VOICE,
                "input": text,
            }
            if TTS_INSTRUCTIONS:
                kwargs["instructions"] = TTS_INSTRUCTIONS

            with get_client().audio.speech.with_streaming_response.create(**kwargs) as response:
                response.stream_to_file(str(temp_path))
            return True

        except AuthenticationError as e:
            print(f"\n❌ Authentication failed: {e}")
            print("   Check your OPENAI_API_KEY in .env")
            return False

        except Exception as e:
            err_str = str(e)
            if "insufficient_quota" in err_str or "exceeded your current quota" in err_str or "Billing hard limit" in err_str:
                print(f"\n❌ insufficient_quota: Your OpenAI account has run out of credit.")
                print("   Top up your account at platform.openai.com/settings/billing")
                print("   Then run again — progress will resume automatically.")
                return False

            print(f"\n⚠️ Error generating chunk (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                wait = 2 + random.random() * 2
                print(f"   Waiting {wait:.1f}s before retry...")
                time.sleep(wait)

    print("\n❌ All retries failed for this chunk.")
    return False


# ------------------------------------------------------
# FFMPEG MERGE
# ------------------------------------------------------

def ffmpeg_escape_concat_path(path: Path) -> str:
    return str(path.resolve()).replace("'", r"'\''")


def merge_mp3s_with_ffmpeg(temp_dir: Path, output_path: Path, total_chunks: int):
    ensure_ffmpeg_available()

    concat_file = temp_dir / FFMPEG_CONCAT_FILENAME
    lines = []

    for i in range(total_chunks):
        chunk_path = temp_dir / f"chunk_{i}.mp3"
        if not chunk_path.exists() or chunk_path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty chunk during merge: {chunk_path.name}")
        lines.append(f"file '{ffmpeg_escape_concat_path(chunk_path)}'")

    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    temp_output = output_path.with_suffix(".tmp.mp3")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(temp_output),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg merge failed.\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )

    temp_output.replace(output_path)


# ------------------------------------------------------
# TEXT -> AUDIO
# ------------------------------------------------------

def text_to_audio(
    text: str,
    source_file: Path,
    book_name: str,
    output_path: Path,
    temp_dir: Path,
    manifest_path: Path
) -> bool:
    print("  Preparing text chunks...")
    chunks = chunk_text(text, MAX_INPUT_TOKENS_PER_CHUNK)
    total_chunks = len(chunks)
    print(f"  Total chunks needed: {total_chunks}")

    if total_chunks == 0:
        print("  ❌ No usable text found.")
        return False

    temp_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_or_create_manifest(manifest_path, book_name, source_file, chunks)
    manifest = sync_manifest_with_files(manifest, temp_dir)
    json_dump(manifest_path, manifest)

    completed_before = sum(1 for c in manifest["chunks"] if c["status"] == "done")
    print(f"  Found {completed_before}/{total_chunks} completed chunks.")

    pending_jobs = []
    for i, chunk in enumerate(chunks):
        entry = manifest["chunks"][i]
        temp_path = temp_dir / entry["filename"]

        if entry["status"] == "done" and temp_path.exists() and temp_path.stat().st_size > 0:
            continue

        pending_jobs.append((i, chunk, temp_path))

    if not pending_jobs:
        print("  All chunks already generated. Proceeding to merge...")
    else:
        print(f"  Generating {len(pending_jobs)} missing chunks with {MAX_WORKERS} workers...")

    completed_now = completed_before
    save_counter = 0

    def worker(job):
        i, chunk, temp_path = job
        ok = generate_tts_chunk(chunk, temp_path, retries=RETRIES)
        return i, ok

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(worker, job) for job in pending_jobs]

        for future in as_completed(futures):
            i, ok = future.result()

            if not ok:
                manifest["chunks"][i]["status"] = "pending"
                json_dump(manifest_path, manifest)
                print("\n❌ Stopping now. Resume will continue automatically next run.")
                return False

            manifest["chunks"][i]["status"] = "done"
            completed_now += 1
            save_counter += 1

            print_progress(completed_now, total_chunks, prefix="  Progress ")

            if save_counter >= MANIFEST_SAVE_EVERY or completed_now == total_chunks:
                json_dump(manifest_path, manifest)
                save_counter = 0

    remaining = [c["index"] for c in manifest["chunks"] if c["status"] != "done"]
    if remaining:
        print(f"  ❌ Cannot merge. Incomplete chunks remain: {remaining[:10]}")
        return False

    print("  Merging chunks into final audiobook with ffmpeg...")
    merge_mp3s_with_ffmpeg(temp_dir, output_path, total_chunks)
    print(f"  Audiobook finished: {output_path}")

    return True


def cleanup_after_success(temp_dir: Path, manifest_path: Path):
    print("  Removing temp chunks and manifest...")
    for f in temp_dir.glob("chunk_*.mp3"):
        f.unlink(missing_ok=True)

    concat_file = temp_dir / FFMPEG_CONCAT_FILENAME
    concat_file.unlink(missing_ok=True)

    manifest_path.unlink(missing_ok=True)

    try:
        temp_dir.rmdir()
    except OSError:
        pass


# ------------------------------------------------------
# CLI
# ------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Convert ebooks to audiobooks with OpenAI TTS.")

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to one ebook file or a folder containing ebooks. If omitted, uses the default books folder."
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output root folder. If omitted, uses the default OUTPUT_ROOT."
    )

    parser.add_argument(
        "--voice",
        type=str,
        default=TTS_VOICE,
        help=f"TTS voice to use. Default: {TTS_VOICE}"
    )

    parser.add_argument(
        "--chunk-tokens",
        type=int,
        default=MAX_INPUT_TOKENS_PER_CHUNK,
        help=f"Maximum estimated input tokens per TTS chunk. Default: {MAX_INPUT_TOKENS_PER_CHUNK}"
    )

    parser.add_argument(
        "--force-rebuild",
        type=str,
        default=None,
        help="Wipe old manifest/temp data for one book. Use original filename stem or cleaned book name."
    )

    return parser.parse_args()

# ------------------------------------------------------
# MAIN
# ------------------------------------------------------

def convert(input=None, output=None, voice=None, chunk_tokens=None, force_rebuild=None):
    """Convert one ebook file, or a folder of ebooks, into MP3 audiobook(s).

    Importable in-process entry point used by the app's ToolRunner and GUI.
    Returns True on full success, False if it failed / paused / found nothing.
    """
    global TTS_VOICE, MAX_INPUT_TOKENS_PER_CHUNK  # allow callers to override global defaults

    input_path = Path(input).expanduser() if input else BOOKS_DIR  # use given input or default books folder
    output_root = Path(output).expanduser() if output else OUTPUT_ROOT  # use given output or default output root

    if voice:
        TTS_VOICE = voice  # override voice
    if chunk_tokens:
        MAX_INPUT_TOKENS_PER_CHUNK = chunk_tokens  # override chunk token size

    print(f"\n📚 Input path: {input_path}")  # show chosen input path
    print(f"🎧 Output root: {output_root}")  # show chosen output folder
    print(f"🗣️ Voice: {TTS_VOICE}")  # show chosen voice
    print(f"🧩 Chunk token limit: {MAX_INPUT_TOKENS_PER_CHUNK}")  # show chunk token limit

    output_root.mkdir(parents=True, exist_ok=True)  # create output root if needed

    if not input_path.exists():
        print(f"❌ Input path not found: {input_path}")  # fail clearly if input does not exist
        return False

    if input_path.is_file():
        ebook_files = [input_path] if input_path.suffix.lower() in {".pdf", ".epub", ".txt", ".mobi"} else []  # single file mode
    else:
        ebook_files = sorted(
            f for f in input_path.iterdir()
            if f.suffix.lower() in {".pdf", ".epub", ".txt", ".mobi"}
        )  # folder mode

    if not ebook_files:
        print("❌ No books found.")
        return False

    print(f"Found {len(ebook_files)} book(s):")
    for f in ebook_files:
        print("  -", f.name)

    for fp in ebook_files:
        print("\n==============================")
        print("📖 Processing:", fp.name)
        print("==============================")

        book_name = clean_name(fp.name)
        book_out_dir = output_root / book_name
        book_out_dir.mkdir(parents=True, exist_ok=True)

        output_path = book_out_dir / f"{book_name}.mp3"
        temp_dir = book_out_dir / TEMP_DIRNAME
        manifest_path = book_out_dir / MANIFEST_FILENAME

        if matches_force_target(fp, book_name, force_rebuild):
            print(f"  🧹 Force rebuild requested for: {fp.name}")
            wipe_book_state(book_out_dir)
            if output_path.exists():
                output_path.unlink()

        if output_path.exists():
            print(f"  ✅ Final audiobook already exists, skipping: {output_path}")
            continue

        print("  Extracting text...")
        try:
            raw = load_text(fp, work_dir=book_out_dir)
        except Exception as e:
            print(f"  ❌ Failed to read file: {e}")
            continue

        print("  Raw text length:", len(raw))
        normalized = light_normalize(raw)
        print("  Normalized text length:", len(normalized))

        text_tokens = count_text_tokens(normalized)
        est_seconds = estimate_audio_seconds_from_text(normalized, words_per_minute=150.0)
        print_cost_estimate("Estimated cost before conversion:", text_tokens, est_seconds)

        try:
            success = text_to_audio(
                text=normalized,
                source_file=fp,
                book_name=book_name,
                output_path=output_path,
                temp_dir=temp_dir,
                manifest_path=manifest_path,
            )
        except Exception as e:
            print(f"\n❌ Fatal error while processing {fp.name}: {e}")
            print("▶️ Fix the issue and run the script again to resume.")
            return False

        if not success:
            print("\n⏸️ Conversion paused.")
            print("▶️ Run the script again later to automatically resume.")
            return False

        try:
            final_seconds = get_audio_duration_seconds(output_path)
            print_cost_estimate("Final estimated cost after conversion:", text_tokens, final_seconds)
        except Exception as e:
            print(f"  ⚠️ Could not calculate final duration/cost: {e}")

        cleanup_after_success(temp_dir, manifest_path)

    print("\n🎉 ALL BOOKS COMPLETED SUCCESSFULLY!")
    return True


def main():
    """CLI entry point. Also runnable as:  python -m services.narrator.converter

    Exits non-zero on any failure so the GUI (which keys off the process exit
    code) can tell a real failure apart from a successful run.
    """
    args = parse_args()
    try:
        ok = convert(
            input=args.input,
            output=args.output,
            voice=args.voice,
            chunk_tokens=args.chunk_tokens,
            force_rebuild=args.force_rebuild,
        )
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
