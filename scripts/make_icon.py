"""Build the Imprint macOS icon from the approved source artwork."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "icon_source_v2.png"
OUTPUT = ASSETS / "icon-v2.icns"

def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source artwork: {SOURCE}")

    with Image.open(SOURCE) as source_image:
        artwork = source_image.convert("RGBA")
        if artwork.width != artwork.height:
            raise ValueError("Icon source artwork must be square")

        # Pillow writes the modern Retina ICNS representations directly. This
        # is more reliable than iconutil on sandboxed macOS builds and keeps the
        # conversion deterministic across developer machines.
        artwork.resize((1024, 1024), Image.Resampling.LANCZOS).save(
            OUTPUT,
            format="ICNS",
        )

    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
