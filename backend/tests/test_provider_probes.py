from app.providers.probes import ProbeOutput, VISION_PROBE_IMAGE, required_probes_passed
from app.providers.models import ModelProfile


def test_probe_fixture_is_small_and_deterministic():
    assert VISION_PROBE_IMAGE.startswith("data:image/png;base64,")
    assert len(VISION_PROBE_IMAGE) < 1000
    assert ProbeOutput(ok=True, message="ok").ok is True


def test_enable_requires_text_structured_and_vision():
    model = ModelProfile(provider_id="p1", model_id="m1", display_name="M1")
    assert required_probes_passed(model) is False
    model.text_status = model.structured_status = model.vision_status = "passed"
    assert required_probes_passed(model) is True
