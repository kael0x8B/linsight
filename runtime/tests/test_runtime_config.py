from pathlib import Path

from ai_runtime.app.core.config import RuntimeSettings


def test_runtime_data_root_accepts_documented_environment_name(monkeypatch) -> None:
    monkeypatch.setenv("LINSIGHT_RUNTIME_API_KEY", "a-secure-runtime-key-for-tests")
    monkeypatch.setenv("LINSIGHT_RUNTIME_DATA_ROOT", "/srv/linsight/runtime-data")

    settings = RuntimeSettings()

    assert settings.runtime_data_root == Path("/srv/linsight/runtime-data")


def test_runtime_data_root_retains_legacy_double_prefix(monkeypatch) -> None:
    monkeypatch.setenv("LINSIGHT_RUNTIME_API_KEY", "a-secure-runtime-key-for-tests")
    monkeypatch.setenv("LINSIGHT_RUNTIME_RUNTIME_DATA_ROOT", "/legacy/runtime-data")

    settings = RuntimeSettings()

    assert settings.runtime_data_root == Path("/legacy/runtime-data")


def test_explicit_data_root_is_not_silently_ignored(tmp_path) -> None:
    settings = RuntimeSettings(api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path)
    assert settings.runtime_data_root == tmp_path
