from unittest import mock

import pytest


@pytest.fixture
def with_tmp_env_file(tmp_path):
    env_file = tmp_path / ".autobot-env"
    env_file.write_text("{}")
    with mock.patch.dict("os.environ", {"autobot_ENV_FILE": str(env_file)}, clear=True):
        yield env_file
    env_file.unlink()
