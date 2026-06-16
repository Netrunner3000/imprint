from pathlib import Path  # used for file paths
from datetime import datetime  # used for timestamped filenames


class ReportExporter:
    def __init__(self, folder: str = "data/reports"):
        self.folder = Path(folder)  # save the report folder path
        self.folder.mkdir(parents=True, exist_ok=True)  # create folder if missing

    def export_text_report(self, title: str, content: str) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # create timestamp
        safe_title = title.strip().replace(" ", "_").replace("/", "_")  # make filename safer
        filename = f"{timestamp}_{safe_title}.txt"  # final report filename
        filepath = self.folder / filename  # full path to report

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)  # write the report content into the file

        return filepath  # return saved file path
