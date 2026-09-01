# -*- coding: utf-8 -*-
"""
Automatinis programos atnaujinimu tikrinimo ir diegimo modulis.
Palaiko GitHub Releases API, semantini versiju palyginima,
siuntimo progreso langa bei saugu failu pakeitima ir persikrovima Windows sistemoje.
"""

import sys
import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QProgressBar, QSizePolicy, QApplication
)

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CaptionLabel,
    PrimaryPushButton, PushButton, ProgressBar, InfoBar,
    InfoBarPosition, isDarkTheme, FluentIcon as FIF
)

CURRENT_VERSION = "1.0.0"
DEFAULT_GITHUB_REPO = "lkuprys/CC"


def parse_version_tuple(v_str):
    """Pavercia versijos eilute (pvz., v1.2.3, 1.2, v2.0.0-beta) i palyginama skaiciu sarasa."""
    if not v_str:
        return (0, 0, 0)
    clean = re.sub(r'^[^\d]*', '', v_str.strip())
    clean = clean.split('-')[0].split('+')[0]
    parts = []
    for p in clean.split('.'):
        digits = re.findall(r'\d+', p)
        if digits:
            parts.append(int(digits[0]))
        else:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(remote_ver, local_ver):
    """Grazina True, jei remote_ver yra grieztai didesne uz local_ver."""
    return parse_version_tuple(remote_ver) > parse_version_tuple(local_ver)


# ----------------- GITHUB RELEASES TIKRINIMO GIJA -----------------
class VersionCheckWorker(QThread):
    update_available = Signal(dict)   # release_info dict
    no_update = Signal(str)           # message
    check_failed = Signal(str)        # error message

    def __init__(self, repo_slug=DEFAULT_GITHUB_REPO, current_ver=CURRENT_VERSION):
        super().__init__()
        self.repo_slug = repo_slug.strip() or DEFAULT_GITHUB_REPO
        self.current_ver = current_ver

    def run(self):
        url = f"https://api.github.com/repos/{self.repo_slug}/releases/latest"
        headers = {
            "User-Agent": "Podbase-Container-Studio-Updater",
            "Accept": "application/vnd.github.v3+json"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    self.check_failed.emit(f"HTTP klaida: {response.status}")
                    return
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            remote_ver = tag_name.lstrip("v")
            release_name = data.get("name", "") or tag_name
            changelog = data.get("body", "") or "Pakeitimų sąrašas nenurodytas."
            published_at = data.get("published_at", "")

            # Ieskome tinkamo archyvo (.zip arba .exe) tarp assets
            download_url = None
            asset_name = None
            asset_size = 0

            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".zip") or name.endswith(".exe") or name.endswith(".rar"):
                    download_url = asset.get("browser_download_url")
                    asset_name = asset.get("name")
                    asset_size = asset.get("size", 0)
                    break

            if not download_url and data.get("zipball_url"):
                download_url = data.get("zipball_url")
                asset_name = f"{self.repo_slug.replace('/', '_')}_update.zip"

            if is_newer_version(remote_ver, self.current_ver):
                self.update_available.emit({
                    "version": remote_ver,
                    "tag_name": tag_name,
                    "name": release_name,
                    "changelog": changelog,
                    "published_at": published_at,
                    "download_url": download_url,
                    "asset_name": asset_name,
                    "asset_size": asset_size,
                    "html_url": data.get("html_url", "")
                })
            else:
                self.no_update.emit(f"Jūs naudojate naujausią programos versiją (v{self.current_ver}).")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.no_update.emit("GitHub repozitorijoje dar nėra paskelbtų atnaujinimų (Releases).")
            else:
                self.check_failed.emit(f"GitHub API klaida: HTTP {e.code}")
        except urllib.error.URLError as e:
            self.check_failed.emit(f"Nepavyko prisijungti prie interneto: {e.reason}")
        except Exception as e:
            self.check_failed.emit(f"Tikrinimo klaida: {str(e)}")


# ----------------- FAILŲ ATSISIUNTIMO GIJA -----------------
class DownloadWorker(QThread):
    progress = Signal(int, str)       # (procentai, greicio/busenos tekstas)
    finished = Signal(str)            # issaugoto failo kelias
    failed = Signal(str)              # klaidos tekstas

    def __init__(self, download_url, target_filename="podbase_update.zip"):
        super().__init__()
        self.download_url = download_url
        self.target_filename = target_filename
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self.download_url:
            self.failed.emit("Nėra atnaujinimo failo atsisiuntimo nuorodos.")
            return

        temp_dir = tempfile.gettempdir()
        dest_path = os.path.join(temp_dir, self.target_filename)

        try:
            req = urllib.request.Request(self.download_url, headers={
                "User-Agent": "Podbase-Container-Studio-Updater"
            })

            with urllib.request.urlopen(req, timeout=20) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024
                start_time = time.time()

                with open(dest_path, "wb") as out_file:
                    while True:
                        if self._is_cancelled:
                            out_file.close()
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                            self.failed.emit("Atsisiuntimas atšauktas.")
                            return

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        out_file.write(chunk)
                        downloaded += len(chunk)

                        elapsed = max(0.1, time.time() - start_time)
                        speed_mb = (downloaded / (1024 * 1024)) / elapsed

                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            status = f"{downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"
                        else:
                            pct = 0
                            status = f"{downloaded / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"

                        self.progress.emit(pct, status)

            self.finished.emit(dest_path)

        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            self.failed.emit(f"Klaida siunčiant atnaujinimą: {str(e)}")


# ----------------- MODERNUS ATNAUJINIMO PATVIRTINIMO DIALOGAS -----------------
class UpdateConfirmDialog(MessageBoxBase):
    def __init__(self, release_info, current_version=CURRENT_VERSION, parent=None):
        super().__init__(parent)
        self.release_info = release_info
        self.current_version = current_version
        self.init_ui()

    def init_ui(self):
        dark = isDarkTheme()
        self.widget.setMinimumWidth(480)
        self.widget.setMaximumWidth(560)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title_box = QHBoxLayout()
        title_box.setSpacing(8)

        lbl_icon = QLabel("🚀", self)
        lbl_icon.setStyleSheet("font-size: 26px;")
        title_box.addWidget(lbl_icon)

        title_lbl = SubtitleLabel("Rastas naujas programos atnaujinimas!", self)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #10b981;")
        title_box.addWidget(title_lbl, 1)
        layout.addLayout(title_box)

        ver_box = QHBoxLayout()
        ver_box.setSpacing(10)

        old_badge = QLabel(f"Dabartinė: v{self.current_version}", self)
        old_badge.setStyleSheet(f"""
            background: {'#334155' if dark else '#e2e8f0'};
            color: {'#94a3b8' if dark else '#64748b'};
            padding: 4px 10px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 12px;
        """)
        ver_box.addWidget(old_badge)

        arrow_lbl = QLabel("➔", self)
        arrow_lbl.setStyleSheet("color: #10b981; font-weight: 900; font-size: 14px;")
        ver_box.addWidget(arrow_lbl)

        new_badge = QLabel(f"Nauja: v{self.release_info.get('version', '')}", self)
        new_badge.setStyleSheet("""
            background: #10b981;
            color: #ffffff;
            padding: 4px 10px;
            border-radius: 6px;
            font-weight: 800;
            font-size: 12px;
        """)
        ver_box.addWidget(new_badge)
        ver_box.addStretch(1)

        layout.addLayout(ver_box)

        layout.addWidget(BodyLabel("Pakeitimų ir naujovių sąrašas (Changelog):", self))

        self.changelog_browser = QTextBrowser(self)
        self.changelog_browser.setFixedHeight(140)
        self.changelog_browser.setPlainText(self.release_info.get("changelog", ""))
        self.changelog_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {'#0f172a' if dark else '#f8fafc'};
                color: {'#f1f5f9' if dark else '#1e293b'};
                border: 1px solid {'#334155' if dark else '#cbd5e1'};
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }}
        """)
        layout.addWidget(self.changelog_browser)

        prompt_lbl = BodyLabel("Ar norite atnaujinti programą dabar?", self)
        prompt_lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(prompt_lbl)

        self.viewLayout.addLayout(layout)

        self.yesButton.setText("⬇️  Taip, atnaujinti dabar")
        self.yesButton.setStyleSheet("""
            PrimaryPushButton {
                background: #10b981;
                border: 1px solid #059669;
                font-weight: 800;
            }
            PrimaryPushButton:hover {
                background: #059669;
            }
        """)
        self.cancelButton.setText("⏰ Priminti vėliau")


# ----------------- ATSISIUNTIMO PROGRESO DIALOGAS -----------------
class DownloadProgressDialog(MessageBoxBase):
    def __init__(self, download_worker, parent=None):
        super().__init__(parent)
        self.worker = download_worker
        self.init_ui()

    def init_ui(self):
        self.widget.setMinimumWidth(440)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        self.lbl_title = SubtitleLabel("Siunčiamas programos atnaujinimas...", self)
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #10b981;")
        layout.addWidget(self.lbl_title)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_status = CaptionLabel("Pradedamas siuntimas...", self)
        self.lbl_status.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(self.lbl_status)

        self.viewLayout.addLayout(layout)

        self.yesButton.hide()
        self.cancelButton.setText("Atšaukti")

        self.worker.progress.connect(self.on_progress)

    def on_progress(self, pct, status_text):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(status_text)


# ----------------- SAUGUS ATNAUJINIMO PRITAIKYMAS IR PERSIKROVIMAS -----------------
def apply_update_and_restart(downloaded_file_path):
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        exe_path = sys.executable
        exe_name = os.path.basename(exe_path)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        exe_path = os.path.join(app_dir, "app_gui.py")
        exe_name = "python.exe"

    temp_dir = tempfile.gettempdir()
    bat_path = os.path.join(temp_dir, "podbase_updater_install.bat")

    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        launch_cmd = f'start "" "{exe_path}"'
    else:
        launch_cmd = f'start "" "{sys.executable}" "{exe_path}"'

    bat_lines = [
        "@echo off",
        "chcp 65001 >nul",
        "echo Laukiama, kol programa pilnai uzsidarys...",
        "timeout /t 2 /nobreak >nul",
        f'taskkill /F /IM "{exe_name}" >nul 2>&1',
        "timeout /t 1 /nobreak >nul",
        f'echo Diegiamas atnaujinimas i "{app_dir}"...',
        f'tar -xf "{downloaded_file_path}" -C "{app_dir}" 2>nul',
        "if %ERRORLEVEL% NEQ 0 (",
        f'    powershell -Command "Expand-Archive -Path ''{downloaded_file_path}'' -DestinationPath ''{app_dir}'' -Force"',
        ")",
        "timeout /t 1 /nobreak >nul",
        "echo Paleidziama atnaujinta programa...",
        f'cd /d "{app_dir}"',
        launch_cmd,
        f'del /f /q "{downloaded_file_path}" 2>nul',
        "(goto) 2>nul & del \"%~f0\"",
        "exit"
    ]

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bat_lines))

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        cwd=temp_dir,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        close_fds=True
    )

    QApplication.quit()
    sys.exit(0)


# ----------------- PAGRINDINIS ATNAUJINTOJO VALDIKLIS (AppUpdater) -----------------
class AppUpdater(QObject):
    update_checked = Signal(bool, str)

    def __init__(self, parent_window, current_version=CURRENT_VERSION):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.current_version = current_version
        self.check_worker = None
        self.download_worker = None
        self.is_manual_check = False
        self.postpone_until = 0

    def check_for_updates(self, repo_slug=DEFAULT_GITHUB_REPO, manual=False):
        self.is_manual_check = manual
        now = time.time()

        if not manual and self.postpone_until > now:
            return

        if self.check_worker and self.check_worker.isRunning():
            return

        self.check_worker = VersionCheckWorker(repo_slug=repo_slug, current_ver=self.current_version)
        self.check_worker.update_available.connect(self.on_update_available)
        self.check_worker.no_update.connect(self.on_no_update)
        self.check_worker.check_failed.connect(self.on_check_failed)
        self.check_worker.start()

    def on_update_available(self, release_info):
        self.update_checked.emit(True, f"Rasta nauja versija v{release_info.get('version')}")

        dlg = UpdateConfirmDialog(release_info, current_version=self.current_version, parent=self.parent_window)
        if dlg.exec():
            download_url = release_info.get("download_url")
            if download_url:
                self.start_download(download_url)
            else:
                InfoBar.warning(
                    title="Nėra failo",
                    content="Šiam atnaujinimui nėra prisegto diegimo failo.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.parent_window
                )
        else:
            self.postpone_until = time.time() + (4 * 3600)
            InfoBar.info(
                title="Atnaujinimas atidėtas",
                content="Apie naują versiją priminsime vėliau.",
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self.parent_window
            )

    def on_no_update(self, msg):
        self.update_checked.emit(True, msg)
        if self.is_manual_check:
            InfoBar.success(
                title="Naujausia versija",
                content=msg,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self.parent_window
            )

    def on_check_failed(self, err_msg):
        self.update_checked.emit(False, err_msg)
        if self.is_manual_check:
            InfoBar.error(
                title="Tikrinimo klaida",
                content=err_msg,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4500,
                parent=self.parent_window
            )

    def start_download(self, download_url):
        self.download_worker = DownloadWorker(download_url)
        prog_dlg = DownloadProgressDialog(self.download_worker, parent=self.parent_window)

        def on_download_finished(dest_path):
            prog_dlg.accept()
            InfoBar.success(
                title="Atsisiųsta!",
                content="Programa atsinaujina ir persikrauna...",
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self.parent_window
            )
            QTimer.singleShot(1000, lambda: apply_update_and_restart(dest_path))

        def on_download_failed(err_msg):
            prog_dlg.reject()
            InfoBar.error(
                title="Atsisiuntimo klaida",
                content=err_msg,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.parent_window
            )

        self.download_worker.finished.connect(on_download_finished)
        self.download_worker.failed.connect(on_download_failed)

        prog_dlg.cancelButton.clicked.connect(self.download_worker.cancel)
        self.download_worker.start()
        prog_dlg.exec()
