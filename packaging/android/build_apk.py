"""Build the TCsOffice Android APK with Qt's pyside6-android-deploy.

Linux only (the release workflow runs it on ubuntu-latest). It needs:
  - the PySide6 and shiboken6 *Android* wheels (aarch64), from
    https://download.qt.io/official_releases/QtForPython/ (same version as
    the host PySide6),
  - the Android NDK r28c and SDK, as pyside-setup's
    tools/cross_compile_android/main.py --download-only fetches them,
  - JDK 17+.

    python packaging/android/build_apk.py --version 1.0.17 \
        --wheel-pyside PySide6-...android_aarch64.whl \
        --wheel-shiboken shiboken6-...android_aarch64.whl

pyside6-android-deploy only lists python3, shiboken6 and PySide6 as the
app's requirements, so this script hooks its buildozer.spec writer to add the
libraries the .docx/.xlsx/.pptx code needs (python-for-android has recipes
for the compiled ones, lxml and Pillow) and the app's version and icon.
The finished APK lands in dist/TCsOffice-<version>.apk.
"""
import argparse
import shutil
import sys
from pathlib import Path

import PySide6

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "build" / "android" / "TCsOffice"

# What office/ imports beyond Qt, plus their own pure-Python dependencies.
EXTRA_REQUIREMENTS = [
    "lxml", "Pillow", "openpyxl", "et_xmlfile", "python-docx", "python-pptx",
    "XlsxWriter", "typing_extensions",
]
EXTRA_PERMISSIONS = ["INTERNET", "REQUEST_INSTALL_PACKAGES"]


def stage():
    """Copy just the app (main.py + office/) into a clean folder: the tool packs the whole folder."""
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    shutil.copytree(ROOT / "office", STAGE / "office",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (STAGE / "main.py").write_text(
        "import sys\n\nfrom office.app import main\n\nsys.exit(main())\n")
    shutil.copy(ROOT / "office" / "assets" / "icon-512.png", STAGE / "icon.png")


def hook_buildozer(version: str, numeric_version: int):
    scripts = Path(PySide6.__file__).parent / "scripts"
    sys.path.insert(0, str(scripts))
    from deploy_lib.android import buildozer as bz

    original = bz.BuildozerConfig.__init__

    def patched(self, spec_file, pysidedeploy_config):
        original(self, spec_file, pysidedeploy_config)
        reqs = self.get_value("app", "requirements")
        self.set_value("app", "requirements", ",".join([reqs, *EXTRA_REQUIREMENTS]))
        perms = [p.strip() for p in (self.get_value("app", "android.permissions") or "").split(",")
                 if p.strip()]
        perms += [p for p in EXTRA_PERMISSIONS if p not in perms]
        self.set_value("app", "android.permissions", ", ".join(perms))
        self.set_value("app", "version", version)
        self.set_value("app", "android.numeric_version", str(numeric_version), raise_warning=False)
        self.set_value("app", "package.domain", "io.github.tcsm23")
        self.set_value("app", "package.name", "tcsoffice")
        self.set_value("app", "title", "TCsOffice")
        self.set_value("app", "orientation", "landscape, portrait", raise_warning=False)
        self.set_value("app", "icon.filename", str(STAGE / "icon.png"))
        self.set_value("app", "source.include_exts", "py,png,svg,ttf,txt,md,ico")
        self.update_config()

    bz.BuildozerConfig.__init__ = patched
    return scripts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--wheel-pyside", required=True, type=Path)
    ap.add_argument("--wheel-shiboken", required=True, type=Path)
    ap.add_argument("--ndk-path", type=Path)
    ap.add_argument("--sdk-path", type=Path)
    args = ap.parse_args()
    for wheel in (args.wheel_pyside, args.wheel_shiboken):
        if not wheel.is_file():
            sys.exit(f"Wheel not found: {wheel} (did the shell glob match nothing?)")

    nums = [int(n) for n in args.version.split(".")] + [0, 0, 0]
    numeric = nums[0] * 1_000_000 + nums[1] * 10_000 + nums[2]  # 1.0.17 -> 1000017

    stage()
    hook_buildozer(args.version, numeric)
    import os
    os.chdir(STAGE)  # the tool insists on running next to main.py
    import android_deploy
    android_deploy.main(
        name="TCsOffice",
        pyside_wheel=args.wheel_pyside.resolve(),
        shiboken_wheel=args.wheel_shiboken.resolve(),
        ndk_path=args.ndk_path.resolve() if args.ndk_path else None,
        sdk_path=args.sdk_path.resolve() if args.sdk_path else None,
        force=True,
        keep_deployment_files=False,
        extra_modules_grouped="Network,Svg",
        loglevel=20,
    )
    # The tool prints buildozer failures instead of raising, so look for the result.
    apks = sorted(STAGE.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if not apks:
        sys.exit("No APK was produced; see the buildozer log above.")
    out = ROOT / "dist" / f"TCsOffice-{args.version}.apk"
    out.parent.mkdir(exist_ok=True)
    shutil.copy(apks[-1], out)
    print(f"APK: {out}")


if __name__ == "__main__":
    main()
