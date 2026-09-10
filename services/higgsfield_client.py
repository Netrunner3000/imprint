"""Higgsfield AI video generation client.

Higgsfield is a real, documented API — text-to-video, image-to-video and Soul
mode, with jobs submitted asynchronously and polled or delivered by webhook.
This wraps the parts Imprint needs, using the same shape as the other provider
clients (lazy client, central timeouts, no side effects at import).

## What this client will and will not send

Higgsfield's Terms of Use prohibit **sexually explicit material** and
**unauthorised images of other people**, moderate at the model level (prompts,
reference images *and* outputs are scanned), and treat circumventing moderation
as its own violation. Breaching it terminates the account.

That is not a footnote for this app in particular, which is used alongside
subscription-platform work — so the guard is in the code rather than in a
comment nobody reads. `check_prompt()` refuses the obvious cases before a
request is spent, and the panel routes everything through it.

The point is not to police the user's business. It is that generating this
material through Higgsfield does not work: the model filters catch it, the
request is wasted, and the account is at risk. Explicit content has to come
from somewhere else. Higgsfield's role here is promotional — safe-for-work
teasers for the off-platform funnels where subscription traffic actually
originates.
"""

from __future__ import annotations

import os
import math
import mimetypes
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from services.api_limits import REQUEST_TIMEOUT_SECONDS

BASE_URL = "https://api.higgsfield.ai"
DEFAULT_TEXT_ENDPOINT = "/bytedance/seedance/v1/lite/text-to-video"
DEFAULT_IMAGE_ENDPOINT = "/bytedance/seedance/v1/lite/image-to-video"
TERMINAL_STATUSES = frozenset({"completed", "failed", "nsfw", "canceled"})
RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})
SUPPORTED_UPLOAD_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif",
})

# Refused before a request is spent. Deliberately narrow — it catches the
# unambiguous cases rather than trying to be a general content classifier,
# because a broad keyword filter on a creative tool mostly produces false
# positives and teaches people to work around it.
_REFUSED_PATTERNS = [
    (r"\b(explicit|hardcore|pornographic|porn|nude|nudity|naked|sex scene|sexual)\b",
     "Higgsfield prohibits sexually explicit material and moderates prompts, "
     "reference images and outputs. Generate promotional, safe-for-work video "
     "here and source explicit content elsewhere."),
    (r"\b(deepfake|face swap|faceswap|undress|deep nude|deepnude)\b",
     "Higgsfield prohibits identity manipulation and unauthorised images of "
     "other people."),
    (r"\b(bypass|circumvent|jailbreak|evade)\b.{0,24}\b(filter|moderation|safety|nsfw)\b",
     "Circumventing moderation is itself a Terms of Use violation."),
]


class ContentPolicyError(ValueError):
    """The request would breach Higgsfield's Terms of Use."""


class HiggsfieldAPIError(RuntimeError):
    """An API error with safe diagnostic context for the UI and support."""


@dataclass
class VideoJob:
    job_id: str
    status: str = "queued"
    video_url: str = ""
    error: str = ""
    status_url: str = ""
    cancel_url: str = ""
    endpoint: str = ""
    correlation_id: str = ""

    @property
    def done(self) -> bool:
        return self.status in TERMINAL_STATUSES


@dataclass(frozen=True)
class PreparedVideoRequest:
    endpoint: str
    payload: dict


@dataclass(frozen=True)
class VideoEstimate:
    credits: float
    usd: float


# Words that flip the meaning of what follows. "no explicit content" is a
# perfectly good instruction to a video model, and a filter that refuses it is
# a filter people learn to route around rather than one that protects anything.
_NEGATIONS = ("no", "not", "non", "none", "nothing", "neither", "without",
              "avoid", "never", "excluding", "exclude", "omit", "zero")
_NEGATION_PHRASES = ("free of", "devoid of", "clear of")


def _is_negated(text: str, start: int) -> bool:
    """True when the match is preceded by a negation, e.g. 'no nudity'.

    Only within the current clause: "explicit shots, no captions" negates the
    captions, not the shots, so the window stops at the last punctuation.
    """
    window = text[max(0, start - 24):start]
    tail = re.split(r"[.;,]", window)[-1]
    words = re.findall(r"[a-z-]+", tail)
    if any(word in _NEGATIONS for word in words[-3:]):
        return True
    # Multi-word forms ("free of nudity") that word-splitting would miss.
    return any(phrase in tail for phrase in _NEGATION_PHRASES)


def check_prompt(prompt: str, reference_image: str | None = None) -> None:
    """Raise ContentPolicyError if this request should not be sent.

    Checked locally so the user gets a clear reason instead of an opaque
    moderation rejection after the request has been billed.
    """
    text = (prompt or "").lower()
    for pattern, reason in _REFUSED_PATTERNS:
        for match in re.finditer(pattern, text):
            if not _is_negated(text, match.start()):
                raise ContentPolicyError(reason)
    if reference_image and not os.path.exists(reference_image):
        raise ValueError(f"Reference image not found: {reference_image}")


class HiggsfieldClient:
    """Thin wrapper over Higgsfield's documented asynchronous REST API."""

    def __init__(self, key_id: str | None = None,
                 key_secret: str | None = None, *,
                 base_url: str | None = None,
                 text_endpoint: str | None = None,
                 image_endpoint: str | None = None):
        self._key_id = key_id
        self._key_secret = key_secret
        self.base_url = (base_url or os.getenv("HIGGSFIELD_BASE_URL")
                         or BASE_URL).rstrip("/")
        self.text_endpoint = (text_endpoint
                              or os.getenv("HIGGSFIELD_TEXT_VIDEO_ENDPOINT")
                              or DEFAULT_TEXT_ENDPOINT)
        self.image_endpoint = (image_endpoint
                               or os.getenv("HIGGSFIELD_IMAGE_VIDEO_ENDPOINT")
                               or DEFAULT_IMAGE_ENDPOINT)
        self._session: requests.Session | None = None

    # ── plumbing ────────────────────────────────────────────────────────
    @property
    def key_id(self) -> str:
        if self._key_id is None:
            self._key_id = (os.getenv("HF_API_KEY_ID")
                            or os.getenv("HIGGSFIELD_API_KEY_ID", ""))
        return self._key_id

    @property
    def key_secret(self) -> str:
        if self._key_secret is None:
            self._key_secret = (os.getenv("HF_API_KEY_SECRET")
                                or os.getenv("HIGGSFIELD_API_KEY_SECRET", ""))
        return self._key_secret

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    def _client(self) -> requests.Session:
        if self._session is None:
            session = requests.Session()
            session.headers.update({
                "Authorization": f"Key {self.key_id}:{self.key_secret}",
                "Content-Type": "application/json",
            })
            self._session = session
        return self._session

    def _require_key(self) -> None:
        if not self.configured:
            raise RuntimeError(
                "Higgsfield needs both HF_API_KEY_ID and HF_API_KEY_SECRET. "
                "Create server-side credentials in Higgsfield Cloud and add "
                "both values to Imprint's private .env file. The old single "
                "HIGGSFIELD_API_KEY bearer token is no longer supported."
            )

    def _api_url(self, path_or_url: str) -> str:
        """Resolve an API URL without leaking credentials to another host."""
        url = urljoin(self.base_url + "/", path_or_url)
        expected = urlparse(self.base_url)
        actual = urlparse(url)
        if actual.scheme != "https" and expected.hostname != "localhost":
            raise HiggsfieldAPIError("Higgsfield API URLs must use HTTPS.")
        if actual.netloc != expected.netloc:
            raise HiggsfieldAPIError(
                "Higgsfield returned a status URL on an unexpected host; "
                "credentials were not sent.")
        return url

    @staticmethod
    def _detail(response) -> str:
        try:
            detail = response.json().get("detail")
            if isinstance(detail, list):
                return "; ".join(str(item) for item in detail)
            return str(detail or "")
        except Exception:
            return ""

    def _raise_for_status(self, response, action: str) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            correlation = response.headers.get("X-Correlation-ID", "")
            detail = self._detail(response) or f"HTTP {response.status_code}"
            suffix = f" (correlation {correlation})" if correlation else ""
            raise HiggsfieldAPIError(f"Higgsfield {action} failed: {detail}{suffix}") from exc

    def _get_with_retry(self, url: str, *, attempts: int = 4):
        """Retry status reads only; generation POSTs are never replayed."""
        delay = 1.0
        last_error = None
        for attempt in range(attempts):
            try:
                response = self._client().get(
                    self._api_url(url), timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    self._raise_for_status(response, "status check")
                    return response
                last_error = HiggsfieldAPIError(
                    f"Higgsfield status check failed: HTTP {response.status_code}")
            except requests.RequestException as exc:
                last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay + random.uniform(0, 0.25))
                delay = min(delay * 2, 8.0)
        raise HiggsfieldAPIError(
            f"Higgsfield status check failed after {attempts} attempts: {last_error}")

    # ── media upload ────────────────────────────────────────────────────
    def upload_file(self, path: str | os.PathLike) -> str:
        """Upload local input media through Higgsfield's presigned flow."""
        self._require_key()
        source = Path(path)
        if not source.is_file():
            raise ValueError(f"Reference image not found: {source}")
        content_type = mimetypes.guess_type(source.name)[0] or ""
        if content_type == "image/jpg":
            content_type = "image/jpeg"
        if content_type not in SUPPORTED_UPLOAD_TYPES:
            raise ValueError(
                f"Unsupported Higgsfield reference-image type: {content_type or source.suffix}")

        response = self._client().post(
            self._api_url("/files/generate-upload-url"),
            json={"content_type": content_type},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        self._raise_for_status(response, "upload preparation")
        upload = response.json()
        public_url = upload.get("public_url", "")
        upload_url = upload.get("upload_url", "")
        upload_headers = upload.get("upload_headers") or {"Content-Type": content_type}
        upload_headers = {
            str(key): str(value) for key, value in upload_headers.items()
            if str(key).lower() != "authorization"
        }
        if not public_url or not upload_url:
            raise HiggsfieldAPIError("Higgsfield did not return a usable upload URL.")
        if urlparse(upload_url).scheme != "https":
            raise HiggsfieldAPIError("Higgsfield returned an insecure upload URL.")

        # Deliberately use a fresh request: API credentials must never be sent
        # to the presigned object-storage host.
        with source.open("rb") as handle:
            put = requests.put(
                upload_url, data=handle, headers=upload_headers,
                timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            put.raise_for_status()
        except requests.HTTPError as exc:
            raise HiggsfieldAPIError("Higgsfield reference-image upload failed.") from exc
        return public_url

    def prepare_video(self, prompt: str, *, duration: int = 5,
                      reference_image: str | None = None,
                      aspect_ratio: str | None = None,
                      resolution: str | None = None) -> PreparedVideoRequest:
        check_prompt(prompt, reference_image)
        self._require_key()
        if not 2 <= int(duration) <= 12:
            raise ValueError("Higgsfield video duration must be between 2 and 12 seconds.")
        endpoint = self.image_endpoint if reference_image else self.text_endpoint
        payload: dict = {"prompt": prompt, "duration": int(duration)}
        if reference_image:
            payload["image_url"] = self.upload_file(reference_image)
        if aspect_ratio is not None:
            if aspect_ratio not in {"16:9", "9:16", "4:3", "3:4", "1:1", "21:9"}:
                raise ValueError(f"Unsupported Higgsfield aspect ratio: {aspect_ratio}")
            payload["aspect_ratio"] = aspect_ratio
        if resolution is not None:
            if resolution not in {"480", "720", "1080"}:
                raise ValueError(f"Unsupported Higgsfield resolution: {resolution}")
            payload["resolution"] = resolution
        return PreparedVideoRequest(endpoint=endpoint, payload=payload)

    def estimate(self, request: PreparedVideoRequest) -> VideoEstimate:
        """Ask Higgsfield for the authenticated cost of this exact request."""
        self._require_key()
        response = self._client().post(
            self._api_url(f"/estimate/{request.endpoint.lstrip('/')}"),
            json=request.payload, timeout=REQUEST_TIMEOUT_SECONDS)
        self._raise_for_status(response, "estimate")
        data = response.json()
        try:
            credits = float(data["credits"])
            usd = float(data["usd"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HiggsfieldAPIError("Higgsfield returned an invalid estimate.") from exc
        if not math.isfinite(credits) or not math.isfinite(usd) or credits < 0 or usd < 0:
            raise HiggsfieldAPIError("Higgsfield returned an invalid estimate.")
        return VideoEstimate(credits=credits, usd=usd)

    # ── generation ──────────────────────────────────────────────────────
    def generate_video(self, prompt: str, *, model: str = "",
                       duration: int = 5, reference_image: str | None = None,
                       seed: int | None = None) -> VideoJob:
        """Submit a generation job. Returns immediately with a job id.

        Policy-checked first: a refused prompt costs nothing and explains why,
        rather than being billed and then rejected by the model's own filter.
        """
        request = self.prepare_video(
            prompt, duration=duration, reference_image=reference_image)
        # `model` and `seed` belonged to the retired guessed endpoint. The
        # official API selects a model by path; the default Seedance schema has
        # no seed field, so neither value is sent.
        return self.generate_prepared(request)

    def generate_prepared(self, request: PreparedVideoRequest) -> VideoJob:
        """Submit a prepared request exactly once."""
        self._require_key()
        response = self._client().post(
            self._api_url(request.endpoint), json=request.payload,
            timeout=REQUEST_TIMEOUT_SECONDS)
        self._raise_for_status(response, "generation")
        data = response.json()
        request_id = data.get("request_id", "")
        if not request_id:
            raise HiggsfieldAPIError("Higgsfield accepted no request identifier.")
        return self._job_from_data(data, endpoint=request.endpoint,
                                   correlation=response.headers.get("X-Correlation-ID", ""))

    @staticmethod
    def _job_from_data(data: dict, *, endpoint: str = "",
                       correlation: str = "") -> VideoJob:
        video = data.get("video") or {}
        return VideoJob(
            job_id=data.get("request_id", ""),
            status=data.get("status", "unknown"),
            video_url=video.get("url", "") if isinstance(video, dict) else "",
            error=data.get("error") or "",
            status_url=data.get("status_url", ""),
            cancel_url=data.get("cancel_url", ""),
            endpoint=endpoint,
            correlation_id=correlation,
        )

    def poll(self, job: VideoJob) -> VideoJob:
        """Refresh one job's status."""
        self._require_key()
        status_url = job.status_url or f"/requests/{job.job_id}/status"
        response = self._get_with_retry(status_url)
        data = response.json()
        refreshed = self._job_from_data(
            data, endpoint=job.endpoint,
            correlation=response.headers.get("X-Correlation-ID", ""))
        refreshed.status_url = data.get("status_url") or job.status_url
        refreshed.cancel_url = data.get("cancel_url") or job.cancel_url
        return refreshed

    def cancel(self, job: VideoJob) -> bool:
        """Cancel a queued request; False means processing already started."""
        self._require_key()
        cancel_url = job.cancel_url or f"/requests/{job.job_id}/cancel"
        response = self._client().post(
            self._api_url(cancel_url), timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 400:
            return False
        self._raise_for_status(response, "cancellation")
        return response.status_code == 202

    def wait(self, job: VideoJob, *, timeout: int = 600,
             interval: float = 2.0, on_progress=None, should_cancel=None) -> VideoJob:
        """Poll until the job finishes or `timeout` seconds elapse.

        Bounded on purpose: a render that never completes should surface as a
        timeout the user can see, not a thread parked forever.
        """
        deadline = time.time() + timeout
        delay = max(0.1, float(interval))
        while time.time() < deadline:
            if should_cancel and should_cancel():
                if job.status == "queued" and self.cancel(job):
                    job.status = "canceled"
                    return job
                # Once in progress Higgsfield cannot cancel. Keep polling so
                # the completed output can still be downloaded rather than lost.
            job = self.poll(job)
            if on_progress:
                on_progress(job)
            if job.done:
                return job
            time.sleep(delay + random.uniform(0, min(0.5, delay / 4)))
            delay = min(delay * 1.5, 10.0)
        job.status = "failed"
        job.error = f"Timed out after {timeout}s"
        return job
