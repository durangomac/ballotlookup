import os
import sys
import platform
from pathlib import Path

import types
import importlib

# Ensure the project root (where app.py lives) is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app


def test_norm_expands_env_and_tilde(monkeypatch, tmp_path):
    fake_home = tmp_path / "Users" / "someone"
    (fake_home / "Desktop").mkdir(parents=True)

    # Provide both env vars so either platform can expand correctly
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    # Windows uses %VAR%, POSIX uses $VAR
    if os.name == "nt":
        raw = r"%USERPROFILE%\Desktop\ballots"
    else:
        raw = "$USERPROFILE/Desktop/ballots"

    normed = app.norm(raw)
    assert Path(normed) == (fake_home / "Desktop" / "ballots")

    # Tilde expansion works cross-platform
    tilde = app.norm("~/Desktop/ballots")
    assert Path(tilde) == (fake_home / "Desktop" / "ballots")


def test_validate_precinct_split_happy_paths():
    ok, val = app.validate_precinct_split("1704.123")
    assert ok and val == "1704.123"

    ok, val = app.validate_precinct_split("1704_123")
    assert ok and val == "1704.123"


def test_validate_precinct_split_rejects_bad():
    for bad in ["170.123", "17044.123", "1704.12", "1704-123", "abcd.efg", "", "  "]:
        ok, msg = app.validate_precinct_split(bad)
        assert not ok and "format" in msg


def test_build_candidates_forms_dot_and_underscore():
    assert app.build_candidates("6432.732") == ["6432.732", "6432_732"]


def test_find_pdf_prefers_nested_u18_like_directory(tmp_path):
    """
    find_pdf doesn't "prefer" nested by itself, but it will match ballot_type if it’s
    part of the nested folder path. We simulate both nested U18 and flat STND and ensure
    both can be found depending on ballot_type argument.
    """
    base = tmp_path / "ballots"
    lang = base / "English"
    (lang / "U18").mkdir(parents=True)

    # Files
    u18_file = lang / "U18" / "1704.123_U18.pdf"
    u18_file.write_bytes(b"%PDF-1.4")
    stnd_file = lang / "1704_123_STND.pdf"
    stnd_file.write_bytes(b"%PDF-1.4")

    # Search for U18 (should see the nested one)
    hits_u18 = app.find_pdf(str(base), "English", ["1704.123", "1704_123"], "U18", case_insensitive=True)
    assert any(p.endswith(str(u18_file)) for p in hits_u18)

    # Search for STND (should see the flat one)
    hits_stnd = app.find_pdf(str(base), "English", ["1704.123", "1704_123"], "STND", case_insensitive=True)
    assert any(p.endswith(str(stnd_file)) for p in hits_stnd)


def test_find_pdf_matches_case_insensitive_and_path_contains_ballot_type(tmp_path):
    base = tmp_path / "b"
    lang = base / "Español" / "PND18"
    lang.mkdir(parents=True)
    f = lang / "6432.732_pNd18.PDF"
    f.write_bytes(b"%PDF-1.4")

    hits = app.find_pdf(str(base), "Español", ["6432.732", "6432_732"], "PND18", case_insensitive=True)
    assert len(hits) == 1
    assert hits[0].endswith(str(f))


def test_compute_log_path_uses_app_dir_when_config_true(monkeypatch, tmp_path):
    # Patch app_base_dir to a sandbox
    monkeypatch.setattr(app, "app_base_dir", lambda: str(tmp_path / "appdir"))
    (tmp_path / "appdir").mkdir()

    cfg = {"log_in_app_dir": True}
    path = app.compute_log_path(cfg)
    assert Path(path).parent == (tmp_path / "appdir")
    assert Path(path).name == "ballotfinder.log"


def test_compute_log_path_uses_user_state_dir_when_config_false(monkeypatch, tmp_path):
    # Redirect the user_state_dir to our sandbox
    monkeypatch.setattr(app, "user_state_dir", lambda: str(tmp_path / "state"))
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    cfg = {"log_in_app_dir": False}
    path = app.compute_log_path(cfg)
    assert Path(path).parent == (tmp_path / "state")
    assert Path(path).name == "ballotfinder.log"


def test_setup_logging_creates_file(monkeypatch, tmp_path):
    # Keep everything sandboxed
    monkeypatch.setattr(app, "user_state_dir", lambda: str(tmp_path / "state"))
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    cfg = {"log_in_app_dir": False}
    app.setup_logging(cfg)

    # LOG_PATH is set globally by setup_logging
    assert hasattr(app, "LOG_PATH")
    assert Path(app.LOG_PATH).exists()


def test_open_or_print_pdf_windows_open(monkeypatch, tmp_path):
    # behave like Windows + open
    test_pdf = tmp_path / "doc.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")
    calls = {}

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(os, "startfile", lambda p, *args: calls.setdefault("startfile", []).append((p, args)), raising=False)

    app.open_or_print_pdf(str(test_pdf), open_instead=True)
    assert ("startfile" in calls) and calls["startfile"][0][0] == str(test_pdf)
    # When open_instead=True, no print verb is passed, so args empty or absent
    assert calls["startfile"][0][1] in [(), tuple()]


def test_open_or_print_pdf_windows_print(monkeypatch, tmp_path):
    test_pdf = tmp_path / "doc.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")
    calls = {}

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    # emulate os.startfile with verb
    def fake_startfile(p, verb="open"):
        calls.setdefault("startfile", []).append((p, verb))
    monkeypatch.setattr(os, "startfile", fake_startfile, raising=False)

    app.open_or_print_pdf(str(test_pdf), open_instead=False)
    assert calls["startfile"][0] == (str(test_pdf), "print")


def test_open_or_print_pdf_posix_open(monkeypatch, tmp_path):
    test_pdf = tmp_path / "doc.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")

    ran = {}
    def fake_run(cmd, check=False):
        ran["cmd"] = cmd

    # macOS
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app.subprocess, "run", fake_run)

    app.open_or_print_pdf(str(test_pdf), open_instead=True)
    assert ran["cmd"] == ["open", str(test_pdf)]

    # Linux
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    app.open_or_print_pdf(str(test_pdf), open_instead=True)
    assert ran["cmd"] == ["xdg-open", str(test_pdf)]


def test_open_or_print_pdf_posix_print(monkeypatch, tmp_path):
    test_pdf = tmp_path / "doc.pdf"
    test_pdf.write_bytes(b"%PDF-1.4")

    ran = {}
    def fake_run(cmd, check=False):
        ran["cmd"] = cmd

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    # macOS
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    app.open_or_print_pdf(str(test_pdf), open_instead=False)
    assert ran["cmd"] == ["lp", str(test_pdf)]

    # Linux
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    app.open_or_print_pdf(str(test_pdf), open_instead=False)
    assert ran["cmd"] == ["lp", str(test_pdf)]