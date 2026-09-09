"""Actually posting, for the platforms where that is possible today.

`services/social_platforms.py` says which those are and why. This module is the
mechanics for them, and it is written to fail loudly and early rather than
half-post: every publisher answers `configured` before it is offered, and a
publisher that cannot run says what is missing in the same sentence.

**Nothing here posts without an explicit click.** There is no scheduler thread
and no "publish all". The schedule is a plan the user works through; a tool
that posts on its own behalf while unattended is how an account gets banned for
something the user never saw.

Credentials come from the environment (the app's `.env` under Application
Support), never from the database, and are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from services.social_platforms import get as get_platform


class PublishError(RuntimeError):
    """Posting failed. The message is shown to the user verbatim."""


@dataclass
class PublishResult:
    permalink: str = ""
    detail: str = ""


class Publisher:
    """One platform's posting mechanics."""

    key = ""
    #: Environment variables this publisher needs, in the order to set them.
    required_env: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return all(os.getenv(name) for name in self.required_env)

    def missing(self) -> list[str]:
        return [name for name in self.required_env if not os.getenv(name)]

    def why_not(self) -> str:
        platform = get_platform(self.key)
        name = platform.name if platform else self.key
        if self.configured:
            return ""
        return (f"{name} is not configured. Set "
                f"{', '.join(self.missing())} in the .env under Application "
                f"Support, then restart Imprint.")

    def publish(self, body: str, media_path: str = "", **kwargs) -> PublishResult:
        raise NotImplementedError


class RedditPublisher(Publisher):
    """A self post (optionally a link post) to one subreddit.

    Uses the script-app OAuth flow — a personal app on your own account, which
    needs no review. The subreddit is the caller's decision and not guessed:
    posting to the wrong one is the single most reliable way to get a promotion
    post removed and an account flagged.
    """

    key = "reddit"
    required_env = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                    "REDDIT_USERNAME", "REDDIT_PASSWORD")
    USER_AGENT = "imprint-social/1.0 (personal script)"

    def _token(self) -> str:
        import requests

        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(os.getenv("REDDIT_CLIENT_ID", ""),
                  os.getenv("REDDIT_CLIENT_SECRET", "")),
            data={"grant_type": "password",
                  "username": os.getenv("REDDIT_USERNAME", ""),
                  "password": os.getenv("REDDIT_PASSWORD", "")},
            headers={"User-Agent": self.USER_AGENT},
            timeout=30,
        )
        if response.status_code != 200:
            raise PublishError(
                f"Reddit refused the login ({response.status_code}). Check the "
                "client id/secret and that the app is of type 'script'.")
        token = response.json().get("access_token")
        if not token:
            raise PublishError("Reddit returned no access token.")
        return token

    def publish(self, body: str, media_path: str = "", *, subreddit: str = "",
                title: str = "", **_kwargs) -> PublishResult:
        import requests

        if not subreddit:
            raise PublishError("Reddit needs a subreddit to post to.")
        if not title:
            raise PublishError("Reddit needs a title.")

        response = requests.post(
            "https://oauth.reddit.com/api/submit",
            headers={"Authorization": f"bearer {self._token()}",
                     "User-Agent": self.USER_AGENT},
            data={"sr": subreddit.lstrip("r/").strip("/"),
                  "kind": "self", "title": title[:300], "text": body,
                  "api_type": "json"},
            timeout=60,
        )
        if response.status_code != 200:
            raise PublishError(f"Reddit rejected the post ({response.status_code}).")

        payload = response.json().get("json", {})
        errors = payload.get("errors") or []
        if errors:
            # Reddit reports rule violations here rather than as an HTTP error.
            raise PublishError("; ".join(" ".join(str(p) for p in e) for e in errors))
        return PublishResult(permalink=payload.get("data", {}).get("url", ""))


class YouTubePublisher(Publisher):
    """Uploads a rendered clip through vidforge's existing uploader.

    Not reimplemented here: vidforge already has a working Data API v3 upload
    with its own OAuth token cache, and a second implementation would be a
    second thing to keep working. Uploads stay private unless explicitly
    published, which is vidforge's default and the right one.
    """

    key = "youtube"
    required_env = ()

    @property
    def configured(self) -> bool:
        from services import video_studio
        if not video_studio.available():
            return False
        # vidforge's youtube module imports cleanly without the Google client
        # libraries — it pulls them inside the call — so importing it proves
        # nothing. Check for what the upload actually needs, and for the OAuth
        # client secret, or "ready to post" is a promise that breaks on click.
        try:
            import googleapiclient.discovery  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401
            from vidforge import config as vf_config  # type: ignore
        except Exception:
            return False
        secrets = Path(vf_config.SECRETS_DIR)
        return secrets.is_dir() and any(secrets.glob("client_secret*.json"))

    def missing(self) -> list[str]:
        return [] if self.configured else ["vidforge YouTube upload prerequisites"]

    def why_not(self) -> str:
        if self.configured:
            return ""
        from services import video_studio
        if not video_studio.available():
            return ("YouTube upload runs through vidforge, which is not "
                    "present. See the Video tab.")
        try:
            import googleapiclient.discovery  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401
        except Exception:
            return ("YouTube upload needs google-api-python-client and "
                    "google-auth-oauthlib installed.")
        from vidforge import config as vf_config  # type: ignore
        return ("Put an OAuth client secret (client_secret*.json) in "
                f"{vf_config.SECRETS_DIR}. The first upload opens a browser "
                "once and caches the token.")

    def publish(self, body: str, media_path: str = "", *, title: str = "",
                privacy: str = "private", **_kwargs) -> PublishResult:
        if not media_path or not Path(media_path).exists():
            raise PublishError("YouTube needs a rendered clip to upload.")
        try:
            from vidforge import youtube  # type: ignore
        except Exception as exc:
            raise PublishError(f"vidforge's uploader is unavailable: {exc}")
        try:
            video_id = youtube.upload(
                Path(media_path), title=title or "Untitled",
                description=body, privacy=privacy)
        except Exception as exc:
            raise PublishError(f"{type(exc).__name__}: {exc}")
        return PublishResult(permalink=f"https://youtu.be/{video_id}")


class PinterestPublisher(Publisher):
    """Creates a pin on one board. Needs a business account, which is free."""

    key = "pinterest"
    required_env = ("PINTEREST_ACCESS_TOKEN",)

    def publish(self, body: str, media_path: str = "", *, board_id: str = "",
                title: str = "", link: str = "", **_kwargs) -> PublishResult:
        import base64
        import requests

        if not board_id:
            raise PublishError("Pinterest needs a board id to pin to.")
        if not media_path or not Path(media_path).exists():
            raise PublishError("Pinterest needs an image or video file.")

        encoded = base64.b64encode(Path(media_path).read_bytes()).decode("ascii")
        response = requests.post(
            "https://api.pinterest.com/v5/pins",
            headers={"Authorization":
                     f"Bearer {os.getenv('PINTEREST_ACCESS_TOKEN', '')}"},
            json={"board_id": board_id, "title": title[:100],
                  "description": body[:500], "link": link or None,
                  "media_source": {"source_type": "image_base64",
                                   "content_type": "image/png",
                                   "data": encoded}},
            timeout=120,
        )
        if response.status_code not in (200, 201):
            raise PublishError(
                f"Pinterest rejected the pin ({response.status_code}): "
                f"{response.text[:200]}")
        return PublishResult(
            permalink=f"https://pinterest.com/pin/{response.json().get('id', '')}")


PUBLISHERS: dict[str, Publisher] = {
    "reddit": RedditPublisher(),
    "youtube": YouTubePublisher(),
    "pinterest": PinterestPublisher(),
}


def publisher_for(platform_key: str) -> Publisher | None:
    return PUBLISHERS.get(platform_key)


def can_publish(platform_key: str) -> bool:
    publisher = PUBLISHERS.get(platform_key)
    return bool(publisher and publisher.configured)


def status_lines() -> list[tuple[str, bool, str]]:
    """(platform name, ready, explanation) for every platform.

    Covers all of them, not just the ones with a publisher, so the panel can
    say plainly which are drafting-only and why rather than leaving the user
    to work out that four of the buttons do nothing.
    """
    from services.social_platforms import PLATFORMS

    lines = []
    for platform in PLATFORMS:
        publisher = PUBLISHERS.get(platform.key)
        if publisher is None:
            lines.append((platform.name, False, platform.posting_note))
        elif publisher.configured:
            lines.append((platform.name, True, "Configured and ready to post."))
        else:
            lines.append((platform.name, False, publisher.why_not()))
    return lines
