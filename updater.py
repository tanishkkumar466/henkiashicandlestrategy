"""
updater.py
----------
Self-update engine. Pure Python — no Qt imports here at all, so it's
reusable regardless of GUI toolkit and easy to unit test.

check_for_update()      -> synchronous, call off the main thread
download_and_install()  -> synchronous, call off the main thread;
                            takes a progress_cb(downloaded, total) and
                            status_cb(str) so the caller (a QThread, in
                            worker.py) can relay progress to the UI.

Everything Qt-specific (QThread wrapping, signals) lives in worker.py.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

from version import __version__ as CURRENT_VERSION


# ---------------------------------------------------------------------------
# CONFIGURE THESE for your repo
# ---------------------------------------------------------------------------
GITHUB_OWNER = "your-github-username"
GITHUB_REPO = "your-repo-name"
GITHUB_TOKEN = None  # set for private repos, e.g. os.environ.get("GH_TOKEN")

API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    notes: str
    zip_url: str
    zip_name: str
    zip_size: int


class UpdateError(Exception):
    pass


def _version_tuple(v: str):
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote_version: str, local_version: str = CURRENT_VERSION) -> bool:
    return _version_tuple(remote_version) > _version_tuple(local_version)


def _api_request(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise UpdateError(f"GitHub API error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise UpdateError(f"Network error contacting GitHub: {e.reason}")


def check_for_update() -> Optional[ReleaseInfo]:
    """Returns ReleaseInfo if newer version exists, else None. Blocking call."""
    data = _api_request(API_LATEST_RELEASE)

    tag = data.get("tag_name", "")
    version = tag.lstrip("vV")
    notes = data.get("body", "") or ""

    assets = data.get("assets", [])
    zip_asset = next((a for a in assets if a.get("name", "").endswith(".zip")), None)
    if not zip_asset:
        raise UpdateError("Latest release has no .zip asset attached.")

    info = ReleaseInfo(
        tag=tag,
        version=version,
        notes=notes,
        zip_url=zip_asset["browser_download_url"],
        zip_name=zip_asset["name"],
        zip_size=zip_asset.get("size", 0),
    )

    if is_newer(info.version):
        return info
    return None


def _download_zip(url: str, dest_path: str, progress_cb: Callable[[int, int], None]):
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")

    with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out_file:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 65536
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            progress_cb(downloaded, total)


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _extract_python_files(zip_path: str, extract_to: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)


def _find_source_root(extracted_dir: str) -> str:
    """Walk down through single-child dirs (GitHub's zip wrapping folder)."""
    current = extracted_dir
    while True:
        entries = [e for e in os.listdir(current) if not e.startswith(".")]
        if len(entries) == 1 and os.path.isdir(os.path.join(current, entries[0])):
            current = os.path.join(current, entries[0])
        else:
            return current


def _copy_over_app(source_root: str, app_root: str):
    for root, _dirs, files in os.walk(source_root):
        rel_dir = os.path.relpath(root, source_root)
        target_dir = app_root if rel_dir == "." else os.path.join(app_root, rel_dir)
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(target_dir, fname))


def relaunch_and_exit(app_root: str):
    """Spawn a new process running main.py, then hard-exit this one."""
    python_exe = sys.executable
    main_script = os.path.join(app_root, "main.py")

    if os.name == "nt":
        relauncher = os.path.join(tempfile.gettempdir(), "app_relaunch.bat")
        with open(relauncher, "w") as f:
            f.write("@echo off\r\n")
            f.write("timeout /t 1 /nobreak > nul\r\n")
            if getattr(sys, "frozen", False):
                f.write(f'start "" "{python_exe}"\r\n')
            else:
                f.write(f'start "" "{python_exe}" "{main_script}"\r\n')
            f.write("del \"%~f0\"\r\n")
        subprocess.Popen(["cmd", "/c", relauncher], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        if getattr(sys, "frozen", False):
            subprocess.Popen([python_exe])
        else:
            subprocess.Popen([python_exe, main_script])

    os._exit(0)


def download_and_install(
    release: ReleaseInfo,
    progress_cb: Callable[[int, int], None],
    status_cb: Callable[[str], None],
) -> str:
    """
    Blocking: download -> extract -> copy over app files.
    Returns the app_root path so the caller can decide when to relaunch
    (the QThread wrapper emits a 'finished' signal instead of relaunching
    immediately, so the UI gets a chance to show "done" first).
    """
    status_cb(f"Downloading {release.zip_name}...")
    tmp_dir = tempfile.mkdtemp(prefix="app_update_")
    zip_path = os.path.join(tmp_dir, release.zip_name)

    _download_zip(release.zip_url, zip_path, progress_cb)

    status_cb("Extracting update...")
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    _extract_python_files(zip_path, extract_dir)
    source_root = _find_source_root(extract_dir)

    status_cb("Installing update...")
    app_root = _app_root()
    _copy_over_app(source_root, app_root)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    status_cb("Update installed.")
    return app_root
