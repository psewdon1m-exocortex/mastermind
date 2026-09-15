import importlib.util
from pathlib import Path

import pytest
from test_image_candidate import archive_fixture

spec = importlib.util.spec_from_file_location("fixture_transfer", Path(__file__).resolve().parents[1] / "scripts/integration/transfer_qualification_stand.py")
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


def test_digest_alias_loss_uses_verified_exported_config_without_pulling(tmp_path):
    path, index, identity = archive_fixture(tmp_path)
    calls = []
    def docker(arguments, **kwargs):
        calls.append((arguments, kwargs))
        assert arguments == ["image", "inspect", "--format", "{{.Id}}", identity]
        return identity + "\n"
    configuration = [{"Name": "/mastermind-integration-postgres-1", "Image": index},
                     {"Name": "/mastermind-integration-gateway-1", "Image": index}]
    assert transfer.loaded_image_identities(configuration, path, docker) == {index: identity}
    assert len(calls) == 1 and calls[0][1] == {"remote": True}


def test_fixture_transfer_rejects_another_loaded_identity(tmp_path):
    path, index, _ = archive_fixture(tmp_path)
    with pytest.raises(ValueError, match="differs"):
        transfer.loaded_image_identities([{"Name": "/mastermind-integration-postgres-1", "Image": index}],
                                         path, lambda *_args, **_kwargs: "sha256:" + "f" * 64)
