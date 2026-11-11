import pytest

from src.tool.filesystem.exceptions import PermissionDeniedError
from src.tool.filesystem.utils import get_path_permission, require_read, require_write


@pytest.fixture
def file_perms(monkeypatch):
    def _apply(default, blocked=None, readonly=None, writable=None):
        config = {
            "default_permission": default,
            "permissions": {
                "blocked": blocked or [],
                "readonly": readonly or [],
                "writable": writable or [],
            },
        }
        monkeypatch.setattr("src.utils.config.get_file_config", lambda: config)

    return _apply


def test_readonly_denies_write_and_writable_whitelist_grants_write(
    tmp_path, file_perms
):
    allowed = tmp_path / "allowed.txt"
    other = tmp_path / "other.txt"
    file_perms("readonly", writable=[str(allowed)])

    assert get_path_permission(str(other)) == "readonly"
    assert get_path_permission(str(allowed)) == "readwrite"


def test_writeonly_denies_read_and_readonly_whitelist_grants_read(tmp_path, file_perms):
    allowed = tmp_path / "readable"
    other = tmp_path / "other"
    file_perms("writeonly", readonly=[str(allowed)])

    assert get_path_permission(str(other)) == "writeonly"
    assert get_path_permission(str(allowed)) == "readwrite"


def test_readwrite_allows_read_and_write(tmp_path, file_perms):
    file_perms("readwrite")

    assert get_path_permission(str(tmp_path / "a.txt")) == "readwrite"


def test_blocked_overrides_more_specific_whitelists(tmp_path, file_perms):
    target = tmp_path / "dir" / "file.txt"
    file_perms(
        "blocked",
        blocked=[str(tmp_path)],
        readonly=[str(target)],
        writable=[str(target)],
    )

    assert get_path_permission(str(target)) == "blocked"


def test_blocked_default_uses_both_whitelists(tmp_path, file_perms):
    read_only = tmp_path / "read"
    write_only = tmp_path / "write"
    file_perms("blocked", readonly=[str(read_only)], writable=[str(write_only)])

    assert get_path_permission(str(read_only)) == "readonly"
    assert get_path_permission(str(write_only)) == "writeonly"


def test_legacy_writable_default_is_readwrite(tmp_path, file_perms):
    file_perms("writable")

    assert get_path_permission(str(tmp_path / "a.txt")) == "readwrite"


def test_require_helpers_follow_effective_permission(tmp_path, file_perms):
    target = tmp_path / "a.txt"
    file_perms("writeonly")

    with pytest.raises(PermissionDeniedError):
        require_read(str(target))
    assert require_write(str(target)) == str(target)
