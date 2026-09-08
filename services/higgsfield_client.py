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
import re
import time
from dataclasses import dataclass

import requests

from services.api_limits import REQUEST_TIMEOUT_SECONDS

BASE_URL = os.getenv("HIGGSFIELD_BASE_URL", "https://api.higgsfield.ai/v1")

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


@dataclass
class VideoJob:
    job_id: str
    status: str = "queued"
    video_url: str = ""
    error: str = ""

    @property
    def done(self) -> bool:
        return self.status in ("completed", "failed")


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
    """Thin wrapper over the Higgsfield generation API."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._session: requests.Session | None = None

    # ── plumbing ────────────────────────────────────────────────────────
    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = os.getenv("HIGGSFIELD_API_KEY", "")
        return self._api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> requests.Session:
        if self._session is None:
            session = requests.Session()
            session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
            self._session = session
        return self._session

    def _require_key(self) -> None:
        if not self.configured:
            raise RuntimeError(
                "HIGGSFIELD_API_KEY is not set. Add it to the .env in "
                "~/Library/Application Support/Imprint/."
            )

    # ── generation ──────────────────────────────────────────────────────
    def generate_video(self, prompt: str, *, model: str = "text-to-video",
                       duration: int = 5, reference_image: str | None = None,
                       seed: int | None = None) -> VideoJob:
        """Submit a generation job. Returns immediately with a job id.

        Policy-checked first: a refused prompt costs nothing and explains why,
        rather than being billed and then rejected by the model's own filter.
        """
        check_prompt(prompt, reference_image)
        self._require_key()

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
        }
        if reference_image:
            payload["reference_image"] = reference_image
        if seed is not None:
            payload["seed"] = seed

        response = self._client().post(
            f"{BASE_URL}/generate", json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return VideoJob(job_id=data.get("id") or data.get("request_id", ""),
                        status=data.get("status", "queued"))

    def poll(self, job: VideoJob) -> VideoJob:
        """Refresh one job's status."""
        self._require_key()
        response = self._client().get(
            f"{BASE_URL}/generate/{job.job_id}", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return VideoJob(
            job_id=job.job_id,
            status=data.get("status", "unknown"),
            video_url=data.get("video_url", "") or data.get("url", ""),
            error=data.get("error", "") or "",
        )

    def wait(self, job: VideoJob, *, timeout: int = 600,
             interval: int = 5, on_progress=None) -> VideoJob:
        """Poll until the job finishes or `timeout` seconds elapse.

        Bounded on purpose: a render that never completes should surface as a
        timeout the user can see, not a thread parked forever.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.poll(job)
            if on_progress:
                on_progress(job)
            if job.done:
                return job
            time.sleep(interval)
        job.status = "failed"
        job.error = f"Timed out after {timeout}s"
        return job
