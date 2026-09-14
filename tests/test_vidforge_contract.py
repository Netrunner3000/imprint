"""The API Imprint depends on across a repository boundary.

`vidforge` is a separate git repo nested at `imprint/vidforge/`, and Imprint
imports it rather than vendoring a copy (see `services/video_studio.py` for why
that trade was made). The cost of that choice is a contract nothing enforces:
renaming a pipeline stage, changing `produce()`'s signature or dropping a config
key is a perfectly reasonable change *inside vidforge*, and it silently breaks
Imprint's Video tab — in a different repository, with no failing test on either
side, discovered when a render does nothing.

These tests are that enforcement, and they live here on purpose: Imprint is the
consumer, so Imprint is what should fail. Each one names what breaks, so
whoever changes vidforge can decide whether to adjust the call site or keep the
name.

They skip rather than fail when vidforge is absent — a clone of `imprint` alone
legitimately has no Video mode, which the panel already explains.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import video_studio  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not video_studio.available(),
    reason="vidforge is not present; Video mode is unavailable by design")


# The stage keys Imprint's progress bar weights and labels. Renaming one does
# not break the render — it breaks the progress reporting, silently, which is
# worse because the run still appears to work.
EXPECTED_STAGES = ("script", "voice", "captions", "visuals",
                   "motion", "audio", "assemble", "thumbnail")

# Config keys `video_studio.clip_overrides()` writes to turn the long-form
# pipeline into a social clip. If the pipeline stops reading one of these, the
# override is accepted and ignored: a vertical clip renders landscape, or a
# 30-second clip comes out eight minutes long.
CLIP_OVERRIDE_KEYS = ("video.width", "video.height", "visuals.image_size",
                      "script.target_seconds", "script.scene_seconds")


class TestPipelineEntryPoint:
    def test_produce_exists_and_keeps_its_signature(self):
        """`VideoWorker` calls produce(cfg, topic=, resume_slug=, reporter=)."""
        from vidforge import pipeline

        signature = inspect.signature(pipeline.produce)
        parameters = signature.parameters
        assert "cfg" in parameters, "produce() lost its positional config argument"
        for name in ("topic", "resume_slug", "reporter"):
            assert name in parameters, (
                f"produce() no longer accepts {name!r}; "
                "ui/workers.VideoWorker passes it by keyword")

    def test_the_build_it_returns_still_carries_slug_and_path(self):
        """`_video_on_done` reads `build.slug` and `build.video_path`."""
        from vidforge.pipeline import Build

        fields = set(getattr(Build, "__dataclass_fields__", {})) or set(dir(Build))
        for name in ("slug", "root"):
            assert name in fields, f"Build.{name} is gone; the done handler reads it"
        assert hasattr(Build, "video_path") or "video_path" in fields, (
            "Build.video_path is gone; the done handler and the Library read it")


class TestProgressContract:
    def test_every_stage_imprint_knows_about_still_exists(self):
        from vidforge import progress

        actual = tuple(key for key, _label, _weight in progress.STAGES)
        missing = [s for s in EXPECTED_STAGES if s not in actual]
        assert not missing, (
            f"pipeline stages renamed or removed: {missing}. Imprint's progress "
            f"bar weights these; update EXPECTED_STAGES and the Video panel.")

    def test_stage_weights_still_sum_to_one(self):
        """`overall_fraction` is a percentage in Imprint's progress bar."""
        from vidforge import progress

        total = sum(weight for _key, _label, weight in progress.STAGES)
        assert total == pytest.approx(1.0, abs=0.01), (
            f"stage weights sum to {total}, so the progress bar will not reach 100%")

    def test_reporter_exposes_the_hooks_the_qt_worker_overrides(self):
        from vidforge import progress

        for hook in ("on_stage", "on_progress", "on_log"):
            assert hasattr(progress.Reporter, hook), (
                f"Reporter.{hook} is gone; ui/workers.VideoWorker subclasses it")
        for control in ("cancel", "raise_if_cancelled"):
            assert hasattr(progress.Reporter, control), (
                f"Reporter.{control} is gone; Stop depends on it")

    def test_cancellation_raises_something_imprint_can_catch(self):
        from vidforge import progress

        assert issubclass(progress.Cancelled, Exception)
        # The worker matches on the class name rather than importing it, so a
        # rename is silent — a cancelled render would report as an error.
        assert progress.Cancelled.__name__ == "Cancelled", (
            "ui/workers.VideoWorker identifies cancellation by class name")


class TestConfigContract:
    def test_the_keys_clip_overrides_writes_are_all_read(self):
        """An override the pipeline ignores fails quietly and expensively.

        A vertical clip that renders landscape still costs a full render.
        """
        config = video_studio.load_config()
        missing = [key for key in CLIP_OVERRIDE_KEYS if config.get(key) is None]
        assert not missing, (
            f"config.yaml no longer defines {missing}; clip_overrides() sets "
            "these and the pipeline would ignore them")

    def test_config_still_offers_load_and_set(self):
        from vidforge import config as vf_config

        assert hasattr(vf_config.Config, "load")
        assert hasattr(vf_config.Config, "get")
        assert hasattr(vf_config.Config, "set"), (
            "video_studio.load_config() applies overrides through Config.set")

    def test_the_paths_imprint_reads_still_exist(self):
        from vidforge import config as vf_config

        for name in ("ensure_user_root", "output_root", "SECRETS_DIR"):
            assert hasattr(vf_config, name), (
                f"vidforge.config.{name} is gone; Imprint reads it "
                "(SECRETS_DIR is how the YouTube publisher reports readiness)")


class TestImportingVidforgeDoesNotShadowImprint:
    """The nested repo is a whole application, not just a package.

    `imprint/vidforge/` holds vidforge's own `main.py` and `app.py` next to the
    `vidforge` package. Putting that directory at the *front* of `sys.path` —
    which is what `video_studio._load()` originally did — makes `import main`
    resolve to vidforge's, for anything imported after the Video mode loads.

    The running app hid it: `main` is in `sys.modules` long before anything
    touches Video, so the shadowed import never happens. The test suite is
    where it showed up, as 132 collection errors the first time a test imported
    `services.video_studio` at module scope.
    """

    def test_imprints_main_still_wins_after_vidforge_is_loaded(self):
        import main

        assert video_studio.available()
        assert Path(main.__file__).resolve().parent == PROJECT_ROOT, (
            f"`main` resolved to {main.__file__}; loading vidforge has "
            "shadowed Imprint's own top-level modules")

    def test_the_vidforge_root_is_not_ahead_of_the_project_root(self):
        """Asserted on sys.path directly, because the symptom depends on
        import order and would otherwise only appear in some runs."""
        entries = [Path(p).resolve() for p in sys.path if p]
        if video_studio.VIDFORGE_ROOT.resolve() not in entries:
            pytest.skip("vidforge root not on sys.path in this run")
        assert entries.index(PROJECT_ROOT) < entries.index(
            video_studio.VIDFORGE_ROOT.resolve()), (
            "imprint/vidforge precedes the project root on sys.path, so its "
            "main.py and app.py shadow Imprint's")


class TestClipOverridesStillMakeSense:
    @pytest.mark.parametrize("aspect,expect_portrait", [
        ("Vertical 9:16", True),
        ("Square 1:1", False),
        ("Landscape 16:9", False),
    ])
    def test_a_vertical_clip_asks_for_a_portrait_image(self, aspect, expect_portrait):
        overrides = video_studio.clip_overrides(aspect, 30)
        width, height = overrides["video.width"], overrides["video.height"]
        assert (height > width) is expect_portrait
        if expect_portrait:
            size = overrides.get("visuals.image_size", "")
            image_w, _, image_h = size.partition("x")
            assert int(image_h) > int(image_w), (
                "a portrait clip is asking the image model for a landscape "
                "image, which gets cropped to a strip of its middle")

    def test_a_short_clip_is_cut_faster_than_long_form(self):
        """Long-form cuts every ~14s. At that cadence a 30s clip is two shots."""
        overrides = video_studio.clip_overrides("Vertical 9:16", 30)
        assert overrides["script.scene_seconds"] <= 6
