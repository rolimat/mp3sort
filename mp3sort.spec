# PyInstaller spec; run via tools/build_app.sh (needs MP3SORT_VERSION, MP3SORT_MINOS and build/licenses)
import os

v = os.environ["MP3SORT_VERSION"]
why = "mp3sort reads and moves the mp3 files in the folders you choose."

a = Analysis(
    ["mp3sort_gui.py"],
    datas=[("sorter/web", "sorter/web"), ("build/licenses", "licenses")],
    hiddenimports=["webview.platforms.cocoa"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="mp3sort", console=False, target_arch="arm64")
coll = COLLECT(exe, a.binaries, a.datas, name="mp3sort")
app = BUNDLE(
    coll,
    name="mp3sort.app",
    icon="assets/mp3sort.icns",
    bundle_identifier="io.github.rolimat.mp3sort",
    version=v,
    info_plist={
        "CFBundleShortVersionString": v,
        "CFBundleVersion": v,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": os.environ["MP3SORT_MINOS"],  # minos of the bundled Python
        "NSDownloadsFolderUsageDescription": why,
        "NSDocumentsFolderUsageDescription": why,
        "NSDesktopFolderUsageDescription": why,
        "NSRemovableVolumesUsageDescription": why,
        "NSHumanReadableCopyright": "GPL-3.0-or-later",
    },
)
