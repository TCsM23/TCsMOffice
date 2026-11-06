from office import updater
from office.updater import is_newer, parse_version, release_from_json

API = {
    "tag_name": "v1.0.12",
    "body": "Fixes and fonts",
    "html_url": "https://github.com/x/y/releases/tag/v1.0.12",
    "assets": [
        {"name": "TCsOffice-1.0.12.apk", "browser_download_url": "u/apk", "size": 3},
        {"name": "TCsOffice-Setup-1.0.12.exe", "browser_download_url": "u/exe", "size": 2},
        {"name": "TCsOffice-1.0.12-x86_64.AppImage", "browser_download_url": "u/ai", "size": 1},
    ],
}


def test_parse_version():
    assert parse_version("v1.2.10") == (1, 2, 10)
    assert parse_version("") == ()


def test_is_newer_compares_numbers_not_text():
    assert is_newer("1.0.10", "1.0.9")
    assert not is_newer("1.0.9", "1.0.10")
    assert not is_newer("v1.0.3", "1.0.3")
    assert is_newer("1.1", "1.0.99")
    assert is_newer("1.0.1", "1.0")


def test_release_picks_this_platforms_asset():
    win = release_from_json(API, "windows")
    assert win.version == "1.0.12" and win.asset_url == "u/exe" and win.notes == "Fixes and fonts"
    assert release_from_json(API, "android").asset_name.endswith(".apk")
    assert release_from_json(API, "appimage").asset_url == "u/ai"
    assert release_from_json(API, "source").asset_url is None


def test_source_checkout_is_not_frozen(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert updater.current_platform() in ("source", "windows", "macos")
    assert not updater.is_frozen()
