from __future__ import annotations

from tools.configure_aap_wave_reboot import (
    ControllerApi,
    csv_values,
    repository_url,
    requests_verify,
)


def test_aap_bootstrap_input_normalization(monkeypatch) -> None:
    assert csv_values("SSH, WebSphere Admin, ,") == ["SSH", "WebSphere Admin"]
    assert requests_verify("true") is True
    assert requests_verify("OFF") is False
    assert requests_verify("/etc/pki/ca.pem") == "/etc/pki/ca.pem"

    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "platform/was-automation")
    assert repository_url("") == (
        "https://github.example.test/platform/was-automation.git"
    )

    api = ControllerApi("https://aap.example.test", "not-a-real-token", api_prefix="")
    assert api.endpoint("projects") == "/api/v2/projects/"
