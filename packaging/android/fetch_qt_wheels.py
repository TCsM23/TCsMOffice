"""Download Qt's prebuilt PySide6 + shiboken6 Android wheels (aarch64).

Prints the PySide6 version it picked on the last line, so the workflow can
install the same version on the host:

    python packaging/android/fetch_qt_wheels.py build/wheels [6.12.0]
"""
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://download.qt.io/official_releases/QtForPython/"


def listing(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def wheels(package):
    """{version: url} for every aarch64 Android wheel of package, top level and one folder down."""
    url = f"{BASE}{package.lower()}/"
    html = listing(url)
    found = {}
    pattern = re.compile(rf'href="([^"]*{package}-(\d+\.\d+\.\d+)[^"]*android_aarch64\.whl)"', re.I)
    for href, version in pattern.findall(html):
        found[version] = href if href.startswith("http") else url + href.lstrip("./")
    if not found:  # some releases sit in a sub-folder per version
        for sub in sorted(set(re.findall(r'href="([^"?/][^"]*/)"', html)))[-6:]:
            for href, version in pattern.findall(listing(url + sub)):
                found[version] = href if href.startswith("http") else url + sub + href
    return found


def key(v):
    return tuple(int(n) for n in v.split("."))


def main():
    out = Path(sys.argv[1])
    want = sys.argv[2] if len(sys.argv) > 2 else None
    out.mkdir(parents=True, exist_ok=True)
    pyside, shiboken = wheels("PySide6"), wheels("shiboken6")
    common = sorted(set(pyside) & set(shiboken), key=key)
    if not common:
        sys.exit(f"No Android aarch64 wheels found under {BASE}")
    version = want if want in common else common[-1]
    for url in (pyside[version], shiboken[version]):
        target = out / url.rsplit("/", 1)[-1]
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, target)
    print(version)


if __name__ == "__main__":
    main()
