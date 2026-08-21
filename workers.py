"""
workers.py
----------
QThread subclasses that run updater.py's blocking calls off the main
thread and report back via Qt signals. This is the idiomatic PySide
equivalent of the callback-based threading used in the Tkinter version:
Qt automatically marshals signal emissions back onto the GUI thread,
so update_window.py never has to touch thread-safety itself.
"""

from PySide6.QtCore import QThread, Signal

import updater


class CheckUpdateWorker(QThread):
    """Runs updater.check_for_update() off the main thread."""

    found = Signal(object)   # emits ReleaseInfo, or None if up to date
    failed = Signal(str)

    def run(self):
        try:
            result = updater.check_for_update()
            self.found.emit(result)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class DownloadInstallWorker(QThread):
    """Runs updater.download_and_install() off the main thread."""

    progress = Signal(int, int)   # downloaded, total
    status = Signal(str)
    finished_ok = Signal(str)     # emits app_root path
    failed = Signal(str)

    def __init__(self, release: "updater.ReleaseInfo", parent=None):
        super().__init__(parent)
        self.release = release

    def run(self):
        try:
            app_root = updater.download_and_install(
                self.release,
                progress_cb=lambda done, total: self.progress.emit(done, total),
                status_cb=lambda text: self.status.emit(text),
            )
            self.finished_ok.emit(app_root)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
