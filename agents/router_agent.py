class RouterAgent:
    def classify(self, text: str) -> str:
        lowered = text.lower()  # lowercase the text for easier keyword checks

        if any(x in lowered for x in ["email", "@", "username", "domain", "whois", "breach", "osint"]):
            return "osint"  # send OSINT-style inputs to the osint agent

        if any(x in lowered for x in ["code", "python", "script", "bug", "debug", "function", "class"]):
            return "coding"  # send coding-style inputs to the coding agent

        if any(x in lowered for x in ["rewrite", "email draft", "blog", "cover letter", "cv"]):
            return "writing"  # send writing tasks to the writing agent

        if any(x in lowered for x in [
            "query letter", "synopsis", "blurb", "book proposal", "author bio",
            "back cover", "publish", "literary agent", "self-publish", "kdp",
            "amazon description", "goodreads", "arc outreach", "arc email",
            "podcast pitch", "press release", "book club", "launch team",
            "newsletter", "instagram post", "tiktok caption", "booktok",
            "book marketing", "author platform", "comp title", "manuscript",
        ]):
            return "author"  # send publishing and marketing tasks to the author agent

        return "chat"  # everything else defaults to normal chat
