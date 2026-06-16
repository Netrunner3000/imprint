# NARRATOR — Ebook to Audiobook Converter

## What it does
Narrator converts ebook files (PDF, EPUB, TXT, MOBI) into MP3 audiobooks using OpenAI's Text-to-Speech (TTS) API. It handles text extraction, chunking, voice synthesis, and stitches the audio into a single MP3 file — all locally.

> **Requirement:** An OpenAI API key is required. This agent uses OpenAI TTS regardless of the provider selected elsewhere in the app.

---

## How to use

1. **Select input file** — click **Browse** and choose a PDF, EPUB, TXT, or MOBI file.
2. **Select output folder** — where the final MP3 will be saved.
3. **Choose a voice** — pick from the six available OpenAI TTS voices (see below).
4. *(Optional)* **Adjust chunk size** — controls how much text is sent per TTS API call (default: 1400 tokens). Smaller chunks = more API calls but smoother long-form audio.
5. Click **Start** to begin conversion.
6. Monitor progress in the **Output Log** — each chunk is logged as it completes.
7. Click **Stop** to cancel at any time.

---

## Supported input formats

| Format | Notes |
|---|---|
| TXT | Direct text extraction — fastest and most reliable |
| PDF | Text extracted from PDF; scanned PDFs may produce poor results |
| EPUB | Full ebook extraction with chapter structure |
| MOBI | Amazon Kindle format — text extracted automatically |

---

## Available voices

| Voice | Character |
|---|---|
| **alloy** | Neutral, versatile — good default |
| **echo** | Male, clear and measured |
| **fable** | British accent, expressive |
| **onyx** | Deep, authoritative |
| **nova** | Female, warm and natural |
| **shimmer** | Female, soft and gentle |

---

## Output
A single `.mp3` file saved to your chosen output folder, named after the source file. Large books are chunked and stitched automatically — you receive one continuous file.

---

## Tips
- **TXT files** give the cleanest results — if your ebook is available as plain text, use it.
- **PDF accuracy** depends on the PDF's formatting. Scanned/image PDFs need OCR first (not handled by Narrator).
- For **very long books**, the conversion may take several minutes — the log shows live progress.
- The **chunk size** setting affects cost: larger chunks = fewer API calls but each call costs slightly more. Default (1400) is optimised for most books.

---

## Cost
Narrator uses OpenAI TTS, billed per character. A typical novel (~80,000 words, ~500,000 characters) costs approximately **$7.50 USD** at $0.015/1K characters (tts-1 model). See the **Cost** panel for live session tracking.
