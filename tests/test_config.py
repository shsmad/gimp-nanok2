from pathlib import Path

import pytest

from gimp_xtouch import LogSpec, load_config

VALID = """
[log]
path = "x.log"
level = "info"
max_bytes = 500
backups = 1
"""


def test_load_valid(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID)
    cfg = load_config(config_file)
    assert cfg.log == LogSpec(path="x.log", level="INFO", max_bytes=500, backups=1)


def test_load_defaults_from_empty(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("")
    cfg = load_config(config_file)
    assert cfg.log.path == "gimp_xtouch.log"
    assert cfg.log.level == "DEBUG"


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_invalid_max_bytes(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[log]\nmax_bytes = 0\n")
    with pytest.raises(ValueError):
        load_config(config_file)
