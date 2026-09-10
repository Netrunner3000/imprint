"""Contract tests for the official Higgsfield request lifecycle."""

import pytest
import requests

from services.higgsfield_client import (
    DEFAULT_IMAGE_ENDPOINT,
    DEFAULT_TEXT_ENDPOINT,
    HiggsfieldAPIError,
    HiggsfieldClient,
    PreparedVideoRequest,
    VideoJob,
)


class Response:
    def __init__(self, data=None, status=200, headers=None):
        self._data = data or {}
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class Session:
    def __init__(self, *, posts=None, gets=None):
        self.posts = list(posts or [])
        self.gets = list(gets or [])
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        result = self.posts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        result = self.gets.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client_with(session):
    client = HiggsfieldClient(key_id="kid", key_secret="secret")
    client._session = session
    return client


def test_authentication_uses_key_id_and_secret():
    client = HiggsfieldClient(key_id="kid", key_secret="secret")
    assert client._client().headers["Authorization"] == "Key kid:secret"


def test_text_generation_uses_model_endpoint_and_returned_urls():
    session = Session(posts=[Response({
        "request_id": "req-1",
        "status": "queued",
        "status_url": "https://api.higgsfield.ai/custom/status/req-1",
        "cancel_url": "https://api.higgsfield.ai/custom/cancel/req-1",
    }, headers={"X-Correlation-ID": "corr-1"})])
    client = client_with(session)

    job = client.generate_video("a safe teaser", duration=6, seed=99,
                                model="retired-model-name")

    method, url, kwargs = session.calls[0]
    assert (method, url) == (
        "POST", f"https://api.higgsfield.ai{DEFAULT_TEXT_ENDPOINT}")
    assert kwargs["json"] == {"prompt": "a safe teaser", "duration": 6}
    assert job.job_id == "req-1"
    assert job.status_url.endswith("/custom/status/req-1")
    assert job.cancel_url.endswith("/custom/cancel/req-1")
    assert job.correlation_id == "corr-1"


def test_reference_image_is_uploaded_without_api_credentials(monkeypatch, tmp_path):
    source = tmp_path / "reference.png"
    source.write_bytes(b"not-a-real-png-but-fine-for-transport")
    session = Session(posts=[Response({
        "upload_url": "https://storage.example.test/presigned",
        "public_url": "https://cdn.example.test/reference.png",
        "upload_headers": {
            "Content-Type": "image/png", "x-upload": "ok",
            "Authorization": "must-not-leak",
        },
    })])
    client = client_with(session)
    put_calls = []

    def fake_put(url, **kwargs):
        put_calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "put", fake_put)
    prepared = client.prepare_video(
        "cinematic portrait", reference_image=str(source))

    assert prepared.endpoint == DEFAULT_IMAGE_ENDPOINT
    assert prepared.payload["image_url"] == "https://cdn.example.test/reference.png"
    assert session.calls[0][1].endswith("/files/generate-upload-url")
    assert put_calls[0][0] == "https://storage.example.test/presigned"
    assert put_calls[0][1]["headers"] == {
        "Content-Type": "image/png", "x-upload": "ok"}
    assert "Authorization" not in put_calls[0][1]["headers"]


def test_estimate_prices_the_exact_prepared_payload():
    session = Session(posts=[Response({"credits": 3.5, "usd": 1.75})])
    client = client_with(session)
    request = PreparedVideoRequest(
        endpoint=DEFAULT_TEXT_ENDPOINT,
        payload={"prompt": "safe teaser", "duration": 5},
    )

    estimate = client.estimate(request)

    assert estimate.credits == pytest.approx(3.5)
    assert estimate.usd == pytest.approx(1.75)
    assert session.calls[0][1] == (
        "https://api.higgsfield.ai/estimate"
        f"{DEFAULT_TEXT_ENDPOINT}")
    assert session.calls[0][2]["json"] is request.payload


def test_poll_retries_safe_reads_and_uses_returned_status_url(monkeypatch):
    session = Session(gets=[
        Response(status=503),
        Response({
            "request_id": "req-2", "status": "completed",
            "video": {"url": "https://cdn.example.test/video.mp4"},
        }, headers={"X-Correlation-ID": "corr-2"}),
    ])
    client = client_with(session)
    monkeypatch.setattr("services.higgsfield_client.time.sleep", lambda _: None)
    monkeypatch.setattr("services.higgsfield_client.random.uniform", lambda *_: 0)
    job = VideoJob(
        "req-2", status_url="https://api.higgsfield.ai/custom/req-2/status")

    result = client.poll(job)

    assert result.status == "completed"
    assert result.video_url.endswith("video.mp4")
    assert result.correlation_id == "corr-2"
    assert [call[0] for call in session.calls] == ["GET", "GET"]
    assert all(call[1].endswith("/custom/req-2/status") for call in session.calls)


def test_generation_post_is_not_retried_after_ambiguous_network_error():
    session = Session(posts=[requests.Timeout("ambiguous timeout")])
    client = client_with(session)
    request = PreparedVideoRequest(DEFAULT_TEXT_ENDPOINT, {
        "prompt": "safe teaser", "duration": 5,
    })

    with pytest.raises(requests.Timeout):
        client.generate_prepared(request)
    assert len(session.calls) == 1


def test_cancel_uses_returned_url_and_accepts_queued_request():
    session = Session(posts=[Response(status=202)])
    client = client_with(session)
    job = VideoJob(
        "req-3", cancel_url="https://api.higgsfield.ai/custom/req-3/cancel")

    assert client.cancel(job)
    assert session.calls[0][1].endswith("/custom/req-3/cancel")


def test_provider_urls_cannot_redirect_authenticated_reads_to_another_host():
    client = client_with(Session(gets=[]))
    with pytest.raises(HiggsfieldAPIError, match="unexpected host"):
        client.poll(VideoJob(
            "req-4", status_url="https://attacker.example/status/req-4"))
