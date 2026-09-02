# -*- coding: utf-8 -*-
"""
Automatinis programos atnaujinimų tikrinimo ir diegimo modulis.
Palaiko GitHub Releases API, vietinį Windows curl/SSL palaikymą, semantinį versijų palyginimą,
siuntimo progreso langą bei saugų failų pakeitimą ir persikrovimą Windows sistemoje.
"""

import sys
import os
import re
import ssl
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

CURRENT_VERSION = "1.1.0"
DEFAULT_GITHUB_REPO = "lkuprys/CC"



def parse_version_tuple(v_str):
    """Paverčia versijos eilutę (pvz., v1.2.3, 1.2, v2.0.0-beta) į palyginamą skaičių sąrašą."""
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
    """Grąžina True, jei remote_ver yra griežtai didesnė už local_ver."""
    return parse_version_tuple(remote_ver) > parse_version_tuple(local_ver)


def fetch_github_release_safe(repo_slug=DEFAULT_GITHUB_REPO):
    """
    Patikimai nuskaito naujausią GitHub Release informaciją.
    Prioritetas teikiamas Windows sisteminiam curl.exe (apeina visas Python OpenSSL/šifrų klaidas),
    su fallback į Python urllib ir PowerShell.
    """
    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    
    # 1. BŪDAS: Windows įdiegtas curl.exe (100% atsparus OpenSSL cipher trūkumams)
    curl_path = shutil.which("curl.exe") or r"C:\Windows\System32\curl.exe"
    if os.path.exists(curl_path):
        try:
            res = subprocess.run(
                [curl_path, "-s", "-L", "-H", "User-Agent: Podbase-Container-Studio", "-H", "Accept: application/vnd.github.v3+json", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if res.returncode == 0 and res.stdout:
                raw_text = res.stdout.decode("utf-8", errors="replace")
                data = json.loads(raw_text)
                if isinstance(data, dict) and "tag_name" in data:
                    return data
        except Exception:
            pass

    # 2. BŪDAS: Python urllib su neapribotu SSL kontekstu
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        try:
            ctx = ssl._create_unverified_context()
        except Exception:
            ctx = None

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Podbase-Container-Studio-Updater",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                raw_text = response.read().decode("utf-8", errors="replace")
                return json.loads(raw_text)
    except Exception:
        pass

    # 3. BŪDAS: PowerShell su Windows SChannel
    try:
        ps_cmd = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13; "
            f"$res = Invoke-RestMethod -Uri '{url}' -Headers @{{'User-Agent'='Podbase'}}; "
            f"$res | ConvertTo-Json -Depth 5"
        ]
        res_ps = subprocess.run(
            ps_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if res_ps.returncode == 0 and res_ps.stdout:
            raw_text = res_ps.stdout.decode("utf-8", errors="replace")
            return json.loads(raw_text)
    except Exception:
        pass

    return None


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
        try:
            data = fetch_github_release_safe(self.repo_slug)
        except Exception as e:
            self.check_failed.emit(f"Tikrinimo klaida: {str(e)}")
            return

        if not data or not isinstance(data, dict) or "tag_name" not in data:
            self.check_failed.emit("Nepavyko pasiekti GitHub atnaujinimų serverio. Patikrinkite interneto ryšį.")
            return

        tag_name = data.get("tag_name", "")
        remote_ver = tag_name.lstrip("v")
        release_name = data.get("name", "") or tag_name
        changelog = data.get("body", "") or "Pakeitimų sąrašas nenurodytas."
        published_at = data.get("published_at", "")

        # Ieškome tinkamo archyvo (.zip arba .exe) tarp assets
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
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass

        # 1. Bandome per Windows curl.exe su progreso stebėjimu
        curl_path = shutil.which("curl.exe") or r"C:\Windows\System32\curl.exe"
        if os.path.exists(curl_path):
            try:
                # Gauname failo dydi
                size_res = subprocess.run(
                    [curl_path, "-sI", "-L", "-H", "User-Agent: Podbase", self.download_url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                total_size = 0
                header_text = size_res.stdout.decode("utf-8", errors="replace")
                for line in header_text.splitlines():
                    if line.lower().startswith("content-length:"):
                        try:
                            total_size = int(line.split(":")[1].strip())
                        except Exception:
                            pass

                proc = subprocess.Popen(
                    [curl_path, "-s", "-L", "-H", "User-Agent: Podbase", "-o", dest_path, self.download_url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )

                start_time = time.time()
                while proc.poll() is None:
                    if self._is_cancelled:
                        proc.kill()
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        self.failed.emit("Atsisiuntimas atšauktas.")
                        return

                    if os.path.exists(dest_path):
                        current_size = os.path.getsize(dest_path)
                        elapsed = max(0.1, time.time() - start_time)
                        speed_mb = (current_size / (1024 * 1024)) / elapsed
                        if total_size > 0:
                            pct = min(100, int((current_size / total_size) * 100))
                            status = f"{current_size / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"
                        else:
                            pct = 50
                            status = f"{current_size / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"

                        self.progress.emit(pct, status)
                    time.sleep(0.2)

                if proc.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
                    self.finished.emit(dest_path)
                    return
            except Exception:
                pass

        # 2. Fallback per Python urllib
        try:
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                ctx = ssl._create_unverified_context()

            req = urllib.request.Request(self.download_url, headers={
                "User-Agent": "Podbase-Container-Studio-Updater"
            })

            with urllib.request.urlopen(req, context=ctx, timeout=25) as response:
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
            return

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
# ----------------- SAUGUS ATNAUJINIMO PRITAIKYMAS IR PERSIKROVIMAS -----------------
def apply_update_and_restart(downloaded_file_path):
    if not downloaded_file_path or not os.path.exists(downloaded_file_path):
        return

    import zipfile
    if not zipfile.is_zipfile(downloaded_file_path):
        print(f"[Updater] Atsisiųstas failas nėra tinkamas ZIP archyvas: {downloaded_file_path}")
        return

    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        exe_path = sys.executable
        exe_args = ""
        app_dir = os.path.dirname(exe_path)
        parent_dir = os.path.dirname(app_dir)
        exe_name = os.path.basename(exe_path)
        exe_stem = os.path.splitext(exe_name)[0]
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(app_dir)
        exe_path = sys.executable
        exe_args = os.path.join(app_dir, "app_gui.py")
        exe_name = "python.exe"
        exe_stem = "python"

    current_pid = os.getpid()
    temp_dir = tempfile.gettempdir()
    ps1_path = os.path.join(temp_dir, "podbase_updater.ps1")
    log_path = os.path.join(temp_dir, "podbase_updater.log")
    staging_dir = os.path.join(temp_dir, "podbase_update_staging")

    script_template = r"""
$ErrorActionPreference = "Continue"

$LogFile = "__LOG_PATH__"
function Log($msg) {
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$time] $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Log "========================================="
Log "STARTING PODBASE CONTAINER STUDIO UPDATER"
Log "Target PID: __TARGET_PID__"
Log "Exe Stem: __EXE_STEM__"
Log "Exe Path: __EXE_PATH__"
Log "Exe Args: __EXE_ARGS__"
Log "App Dir: __APP_DIR__"
Log "Parent Dir: __PARENT_DIR__"
Log "Zip Path: __ZIP_PATH__"
Log "Staging Dir: __STAGING_DIR__"
Log "Log File: $LogFile"
Log "========================================="

$TargetPid = __TARGET_PID__
$ExeStem = "__EXE_STEM__"
$ExePath = "__EXE_PATH__"
$ExeArgs = "__EXE_ARGS__"
$AppDir = "__APP_DIR__"
$ParentDir = "__PARENT_DIR__"
$ZipPath = "__ZIP_PATH__"
$StagingDir = "__STAGING_DIR__"

# 1. Terminate running process by PID and process stem
if ($TargetPid -and $TargetPid -gt 0) {
    Log "Stopping target process PID $TargetPid..."
    Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $TargetPid -Timeout 6 -ErrorAction SilentlyContinue
}

if ($ExeStem -and $ExeStem -ne "python" -and $ExeStem -ne "python3") {
    Log "Ensuring all remaining instances of $ExeStem are closed..."
    Get-Process -Name $ExeStem -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# 2. Wait until target executable is free and unlocked
$targetExe = Join-Path $AppDir "$ExeStem.exe"
if (Test-Path -LiteralPath $targetExe) {
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $stream = [System.IO.File]::Open($targetExe, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            if ($stream) {
                $stream.Close()
                $stream.Dispose()
                Log "Target executable is writable."
                break
            }
        } catch {
            Log "Target executable is still locked, waiting 1s... ($i/10)"
            Start-Sleep -Seconds 1
        }
    }
}

# 3. Clean and prepare staging directory
Log "Preparing staging directory: $StagingDir"
if (Test-Path -LiteralPath $StagingDir) {
    Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

# 4. Extract update archive
Log "Extracting ZIP archive: $ZipPath"
try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $StagingDir -Force
    Log "Extraction completed successfully."
} catch {
    Log "Extraction failed: $($_.Exception.Message)"
    exit 1
}

# 5. Detect payload folder structure
$stagedApp = $null
if (Test-Path -LiteralPath (Join-Path $StagingDir "Podbase_Konteineriai")) {
    $stagedApp = Join-Path $StagingDir "Podbase_Konteineriai"
} elseif (Test-Path -LiteralPath (Join-Path $StagingDir "$ExeStem.exe")) {
    $stagedApp = $StagingDir
} else {
    $subDirs = Get-ChildItem -Path $StagingDir -Directory
    if ($subDirs.Count -eq 1 -and (Test-Path (Join-Path $subDirs[0].FullName "Podbase_Konteineriai"))) {
        $stagedApp = Join-Path $subDirs[0].FullName "Podbase_Konteineriai"
    } elseif ($subDirs.Count -eq 1) {
        $stagedApp = $subDirs[0].FullName
    }
}

if (-not $stagedApp -or -not (Test-Path -LiteralPath $stagedApp)) {
    Log "ERROR: Could not find valid application payload in staging directory!"
    exit 1
}

Log "Deploying payload from $stagedApp to $AppDir using Robocopy..."

# Backup user configs (config.json, history.json) before overwriting
$cfgBackup = Join-Path $env:TEMP "podbase_config_backup.json"
$histBackup = Join-Path $env:TEMP "podbase_history_backup.json"
if (Test-Path (Join-Path $AppDir "config.json")) {
    Copy-Item (Join-Path $AppDir "config.json") $cfgBackup -Force -ErrorAction SilentlyContinue
    Log "Backed up config.json"
}
if (Test-Path (Join-Path $AppDir "history.json")) {
    Copy-Item (Join-Path $AppDir "history.json") $histBackup -Force -ErrorAction SilentlyContinue
    Log "Backed up history.json"
}

# Deploy application files with Robocopy
# /E = recursive, /IS = include same files, /IT = include tweaked files, /R:5 = retry 5 times, /W:1 = wait 1 sec
$roboArgs = @($stagedApp, $AppDir, "/E", "/IS", "/IT", "/R:5", "/W:1", "/NP")
$resRobo = Start-Process -FilePath "robocopy.exe" -ArgumentList $roboArgs -Wait -NoNewWindow -PassThru
Log "Robocopy exit code: $($resRobo.ExitCode)"

if ($resRobo.ExitCode -ge 8) {
    Log "ERROR: Robocopy failed with exit code $($resRobo.ExitCode)"
    exit 1
}

# Restore user config & history
if (Test-Path $cfgBackup) {
    Copy-Item $cfgBackup (Join-Path $AppDir "config.json") -Force -ErrorAction SilentlyContinue
    Remove-Item $cfgBackup -Force -ErrorAction SilentlyContinue
    Log "Restored user config.json"
}
if (Test-Path $histBackup) {
    Copy-Item $histBackup (Join-Path $AppDir "history.json") -Force -ErrorAction SilentlyContinue
    Remove-Item $histBackup -Force -ErrorAction SilentlyContinue
    Log "Restored user history.json"
}

# Deploy companion items (Chrome_Extension, Paleisti_Programa.bat, NAUDOJIMO_INSTRUKCIJA.md)
$stagedExt = Join-Path $StagingDir "Chrome_Extension"
if (Test-Path -LiteralPath $stagedExt) {
    $destExt = Join-Path $ParentDir "Chrome_Extension"
    Log "Deploying Chrome Extension to $destExt..."
    Start-Process -FilePath "robocopy.exe" -ArgumentList @($stagedExt, $destExt, "/E", "/IS", "/IT", "/R:3", "/W:1", "/NP") -Wait -NoNewWindow -PassThru | Out-Null
}

$stagedBat = Join-Path $StagingDir "Paleisti_Programa.bat"
if (Test-Path -LiteralPath $stagedBat) {
    Log "Deploying Paleisti_Programa.bat to $ParentDir..."
    Copy-Item -Path $stagedBat -Destination $ParentDir -Force -ErrorAction SilentlyContinue
}

$stagedDoc = Join-Path $StagingDir "NAUDOJIMO_INSTRUKCIJA.md"
if (Test-Path -LiteralPath $stagedDoc) {
    Copy-Item -Path $stagedDoc -Destination $ParentDir -Force -ErrorAction SilentlyContinue
}

# Clean staging and zip
Log "Cleaning up staging files..."
Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue

# 6. Restart application cleanly as a visible desktop process
Log "Restarting application: $ExePath $ExeArgs in $AppDir..."
Start-Sleep -Milliseconds 600

try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ExePath
    if ($ExeArgs) {
        $psi.Arguments = "`"$ExeArgs`""
    }
    $psi.WorkingDirectory = $AppDir
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    $proc = [System.Diagnostics.Process]::Start($psi)
    Log "Application started successfully! Process ID: $($proc.Id)"
} catch {
    Log "ProcessStart failed: $($_.Exception.Message). Falling back to cmd start..."
    if ($ExeArgs) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "`"`"", "`"$ExePath`"", "`"$ExeArgs`"" -WorkingDirectory $AppDir
    } else {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "`"`"", "`"$ExePath`"" -WorkingDirectory $AppDir
    }
}

Log "=== UPDATE COMPLETED SUCCESSFULLY ==="
"""

    script_content = script_template.replace("__LOG_PATH__", log_path)
    script_content = script_content.replace("__EXE_PATH__", exe_path)
    script_content = script_content.replace("__EXE_ARGS__", exe_args)
    script_content = script_content.replace("__APP_DIR__", app_dir)
    script_content = script_content.replace("__PARENT_DIR__", parent_dir)
    script_content = script_content.replace("__ZIP_PATH__", downloaded_file_path)
    script_content = script_content.replace("__STAGING_DIR__", staging_dir)
    script_content = script_content.replace("__EXE_STEM__", exe_stem)
    script_content = script_content.replace("__TARGET_PID__", str(current_pid))

    with open(ps1_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
        cwd=temp_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        close_fds=True
    )

    try:
        QApplication.quit()
    except Exception:
        pass

    # Forcefully terminate process and release all file locks immediately
    os._exit(0)


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
