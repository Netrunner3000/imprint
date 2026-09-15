"""Intent router implementation owned by the internal Router package."""

ROUTES = (
    ("onlyfans", ("onlyfans", "subscriber", "ppv", "fan retention")),
    ("video", ("video", "youtube", "shorts", "reel", "storyboard", "sora")),
    ("social", ("social post", "caption", "schedule post", "pinterest", "reddit")),
    ("audiobook", ("audiobook", "narrate", "narration", "text to speech", "tts")),
    ("music", ("spotify", "music release", "album", "single", "artist profile")),
    ("webdesign", ("website", "web page", "html", "css", "landing page")),
    ("fiverr", ("fiverr", "client delivery", "gig listing", "logo order")),
    ("creator", ("content campaign", "content calendar", "promo asset", "creator")),
    ("manuscript", (
        "query letter", "synopsis", "blurb", "book proposal", "publish",
        "kdp", "goodreads", "arc outreach", "book marketing",
    )),
    ("author", (
        "write a chapter", "write a scene", "character arc", "world building",
        "novel", "manuscript", "book outline",
    )),
)


class RouterAgent:
    def classify(self, text: str) -> str:
        lowered = text.casefold()
        for agent_key, keywords in ROUTES:
            if any(keyword in lowered for keyword in keywords):
                return agent_key
        return "chat"
