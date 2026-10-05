# -*- coding: utf-8 -*-
"""
Automatinis programos atnaujinimų tikrinimo ir diegimo modulis.

Eiga:
1. VersionCheckWorker per GitHub Releases API suranda naujausią leidimą ir jo
   Podbase_Studio_vX.Y.Z.zip failą.
2. DownloadWorker atsisiunčia ZIP ir patikrina jį (dydis, SHA-256, struktūra).
3. apply_update_and_restart() išarchyvuoja ZIP, paleidžia PowerShell skriptą ir
   užbaigia programą. Skriptas pakeičia failus (su atsargine kopija ir atstatymu
   klaidos atveju) ir VISADA iš naujo paleidžia programą.
4. Kito paleidimo metu show_last_update_result() parodo, ar atnaujinimas pavyko.

Žurnalas: %TEMP%\\podbase_updater.log
"""

import sys
import os
import re
import ssl
import json
import time
import shutil
import hashlib
import zipfile
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

CURRENT_VERSION = "1.1.3"
DEFAULT_GITHUB_REPO = "lkuprys/CC"

# Release ZIP pavadinimas, kurį sukuria package_release.py
RELEASE_ASSET_PATTERN = re.compile(r"^Podbase_Studio_v[\d.]+\.zip$", re.IGNORECASE)
# Programos aplankas ZIP viduje ir jo exe
PAYLOAD_DIR_NAME = "Podbase_Konteineriai"
PAYLOAD_EXE_NAME = "Podbase_Konteineriai.exe"

# Kaip dažnai tikrinti atnaujinimus, kol programa atidaryta
PERIODIC_CHECK_INTERVAL_MS = 30 * 60 * 1000
# Kiek laiko netrukdyti po „Priminti vėliau“
POSTPONE_SECONDS = 4 * 3600

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _temp_path(name):
    return os.path.join(tempfile.gettempdir(), name)


UPDATER_LOG_PATH = _temp_path("podbase_updater.log")
UPDATE_RESULT_PATH = _temp_path("podbase_update_result.json")


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


def _find_curl():
    curl_path = shutil.which("curl.exe") or r"C:\Windows\System32\curl.exe"
    return curl_path if os.path.exists(curl_path) else None


def fetch_github_release_safe(repo_slug=DEFAULT_GITHUB_REPO):
    """
    Nuskaito naujausią GitHub Release informaciją.
    Pirmiausia Windows curl.exe (naudoja sistemos sertifikatus), tada Python urllib,
    tada PowerShell. Visais atvejais SSL sertifikatas tikrinamas.
    """
    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"

    # 1. BŪDAS: Windows curl.exe
    curl_path = _find_curl()
    if curl_path:
        try:
            res = subprocess.run(
                [curl_path, "-s", "-f", "-L", "--max-time", "12",
                 "-H", "User-Agent: Podbase-Container-Studio",
                 "-H", "Accept: application/vnd.github+json", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                creationflags=_NO_WINDOW
            )
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout.decode("utf-8", errors="replace"))
                if isinstance(data, dict) and "tag_name" in data:
                    return data
        except Exception:
            pass

    # 2. BŪDAS: Python urllib (su sertifikato tikrinimu)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Podbase-Container-Studio-Updater",
            "Accept": "application/vnd.github+json"
        })
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
                if isinstance(data, dict) and "tag_name" in data:
                    return data
    except Exception:
        pass

    # 3. BŪDAS: PowerShell su Windows SChannel
    try:
        ps_cmd = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
            f"$res = Invoke-RestMethod -Uri '{url}' -Headers @{{'User-Agent'='Podbase'}}; "
            "$res | ConvertTo-Json -Depth 5"
        ]
        res_ps = subprocess.run(
            ps_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            creationflags=_NO_WINDOW
        )
        if res_ps.returncode == 0 and res_ps.stdout:
            data = json.loads(res_ps.stdout.decode("utf-8", errors="replace"))
            if isinstance(data, dict) and "tag_name" in data:
                return data
    except Exception:
        pass

    return None


def select_release_asset(release_data):
    """Grąžina tinkamą release ZIP asset'ą arba None. Kitų failų (source code, .exe, .rar) neimame."""
    for asset in release_data.get("assets", []) or []:
        if RELEASE_ASSET_PATTERN.match(asset.get("name", "")):
            return asset
    return None


def validate_update_zip(zip_path, expected_size=0, expected_sha256=None):
    """Patikrina atsisiųstą ZIP. Grąžina (True, "") arba (False, klaidos_tekstas)."""
    if not zip_path or not os.path.exists(zip_path):
        return False, "Atsisiųstas failas nerastas."

    actual_size = os.path.getsize(zip_path)
    if expected_size and actual_size != expected_size:
        return False, f"Atsisiųstas failas nepilnas ({actual_size} iš {expected_size} baitų)."

    if expected_sha256:
        h = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest().lower() != expected_sha256.lower():
            return False, "Atsisiųsto failo kontrolinė suma nesutampa."

    if not zipfile.is_zipfile(zip_path):
        return False, "Atsisiųstas failas nėra ZIP archyvas."

    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = set(n.replace("\\", "/") for n in zf.namelist())
            bad = zf.testzip()
    except Exception as e:
        return False, f"Nepavyko perskaityti ZIP: {e}"

    if bad:
        return False, f"ZIP archyvas sugadintas (failas {bad})."
    if f"{PAYLOAD_DIR_NAME}/{PAYLOAD_EXE_NAME}" not in names:
        return False, f"ZIP archyve nėra {PAYLOAD_DIR_NAME}/{PAYLOAD_EXE_NAME}."

    return True, ""


# ----------------- GITHUB RELEASES TIKRINIMO GIJA -----------------
class VersionCheckWorker(QThread):
    update_available = Signal(dict)   # release_info dict
    no_update = Signal(str)           # message
    check_failed = Signal(str)        # error message

    def __init__(self, repo_slug=DEFAULT_GITHUB_REPO, current_ver=CURRENT_VERSION):
        super().__init__()
        self.repo_slug = (repo_slug or "").strip() or DEFAULT_GITHUB_REPO
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
        remote_ver = tag_name.lstrip("vV")

        if not is_newer_version(remote_ver, self.current_ver):
            self.no_update.emit(f"Jūs naudojate naujausią programos versiją (v{self.current_ver}).")
            return

        asset = select_release_asset(data)
        sha256 = None
        if asset:
            digest = asset.get("digest") or ""
            if digest.lower().startswith("sha256:"):
                sha256 = digest.split(":", 1)[1]

        self.update_available.emit({
            "version": remote_ver,
            "tag_name": tag_name,
            "name": data.get("name", "") or tag_name,
            "changelog": data.get("body", "") or "Pakeitimų sąrašas nenurodytas.",
            "published_at": data.get("published_at", ""),
            "download_url": asset.get("browser_download_url") if asset else None,
            "asset_name": asset.get("name") if asset else None,
            "asset_size": int(asset.get("size", 0) or 0) if asset else 0,
            "asset_sha256": sha256,
            "html_url": data.get("html_url", "")
        })


# ----------------- FAILŲ ATSISIUNTIMO GIJA -----------------
class DownloadWorker(QThread):
    progress = Signal(int, str)       # (procentai, greičio/būsenos tekstas)
    finished = Signal(str)            # patikrinto failo kelias
    failed = Signal(str)              # klaidos tekstas

    def __init__(self, download_url, expected_size=0, expected_sha256=None,
                 target_filename="podbase_update.zip"):
        super().__init__()
        self.download_url = download_url
        self.expected_size = expected_size or 0
        self.expected_sha256 = expected_sha256
        self.target_filename = target_filename
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _remove(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def _emit_progress(self, current_size, start_time):
        elapsed = max(0.1, time.time() - start_time)
        speed_mb = (current_size / (1024 * 1024)) / elapsed
        total = self.expected_size
        if total > 0:
            pct = min(100, int((current_size / total) * 100))
            status = f"{current_size / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"
        else:
            pct = 0
            status = f"{current_size / (1024*1024):.1f} MB ({speed_mb:.1f} MB/s)"
        self.progress.emit(pct, status)

    def _download_with_curl(self, dest_path):
        """Grąžina True (pavyko), False (nepavyko) arba None (atšaukta)."""
        curl_path = _find_curl()
        if not curl_path:
            return False
        try:
            proc = subprocess.Popen(
                [curl_path, "-s", "-f", "-L", "--retry", "2", "--connect-timeout", "15",
                 "-H", "User-Agent: Podbase-Container-Studio", "-o", dest_path, self.download_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_NO_WINDOW
            )
            start_time = time.time()
            while proc.poll() is None:
                if self._is_cancelled:
                    proc.kill()
                    return None
                if os.path.exists(dest_path):
                    self._emit_progress(os.path.getsize(dest_path), start_time)
                time.sleep(0.2)
            return proc.returncode == 0 and os.path.exists(dest_path)
        except Exception:
            return False

    def _download_with_urllib(self, dest_path):
        """Grąžina True (pavyko), None (atšaukta) arba iškelia klaidą."""
        req = urllib.request.Request(self.download_url, headers={
            "User-Agent": "Podbase-Container-Studio-Updater"
        })
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as response:
            start_time = time.time()
            downloaded = 0
            with open(dest_path, "wb") as out_file:
                while True:
                    if self._is_cancelled:
                        return None
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    self._emit_progress(downloaded, start_time)
        return True

    def run(self):
        if not self.download_url:
            self.failed.emit("Nėra atnaujinimo failo atsisiuntimo nuorodos.")
            return

        dest_path = _temp_path(self.target_filename)
        self._remove(dest_path)

        result = self._download_with_curl(dest_path)
        if result is None:
            self._remove(dest_path)
            self.failed.emit("Atsisiuntimas atšauktas.")
            return

        if not result:
            self._remove(dest_path)
            try:
                result = self._download_with_urllib(dest_path)
            except Exception as e:
                self._remove(dest_path)
                self.failed.emit(f"Klaida siunčiant atnaujinimą: {str(e)}")
                return
            if result is None:
                self._remove(dest_path)
                self.failed.emit("Atsisiuntimas atšauktas.")
                return

        ok, err = validate_update_zip(dest_path, self.expected_size, self.expected_sha256)
        if not ok:
            self._remove(dest_path)
            self.failed.emit(err)
            return

        self.progress.emit(100, "Atsisiųsta ir patikrinta.")
        self.finished.emit(dest_path)


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
# PowerShell skriptas. Reikšmės įstatomos kaip PowerShell eilutės viengubose kabutėse
# (žr. _ps_quote), todėl keliai su $, ` ar lietuviškomis raidėmis nesugadinami.
# Skriptas rašomas UTF-8 su BOM, kad Windows PowerShell 5.1 teisingai perskaitytų raides.
UPDATER_PS_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'

$LogFile    = __LOG_PATH__
$ResultFile = __RESULT_PATH__
$TargetPid  = __TARGET_PID__
$ExePath    = __EXE_PATH__
$ExeStem    = __EXE_STEM__
$AppDir     = __APP_DIR__
$ParentDir  = __PARENT_DIR__
$StagingDir = __STAGING_DIR__
$StagedApp  = __STAGED_APP__
$ZipPath    = __ZIP_PATH__
$NewVersion = __NEW_VERSION__
$OldVersion = __OLD_VERSION__

$Internal       = Join-Path $AppDir '_internal'
$InternalBackup = Join-Path $AppDir '_internal.old'
$ExeBackup      = "$ExePath.old"

function Log($msg) {
    $time = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    try { "[$time] $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8 } catch {}
}

function Write-Result($ok, $message) {
    try {
        @{ ok = $ok; version = $NewVersion; old_version = $OldVersion; message = $message; log = $LogFile } |
            ConvertTo-Json | Out-File -FilePath $ResultFile -Encoding utf8
    } catch {}
}

function Run-Robocopy($src, $dst, $extra) {
    # Vietinis nustatymas: robocopy išvestis į stderr neturi virsti PowerShell išimtimi
    $ErrorActionPreference = 'Continue'
    $rargs = @($src, $dst) + $extra + @('/R:10', '/W:1', '/NP', '/NJH', '/NJS', '/NDL')
    $out = & robocopy.exe @rargs 2>&1
    $code = $LASTEXITCODE
    if ($out) { $out | ForEach-Object { Log "  robocopy: $_" } }
    Log "robocopy $src -> $dst : exit $code"
    if ($code -ge 8) { throw "Nepavyko nukopijuoti failų (robocopy klaida $code)." }
}

Log '========================================='
Log "PODBASE UPDATER: v$OldVersion -> v$NewVersion"
Log "App dir: $AppDir"
Log "Staged app: $StagedApp"

$ok = $false
$message = ''
$backupMade = $false

try {
    # 1. Laukiame, kol programa užsidarys
    Wait-Process -Id $TargetPid -Timeout 20 -ErrorAction SilentlyContinue
    Get-Process -Id $TargetPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    # Kiti tos pačios programos (to paties exe) egzemplioriai
    Get-Process -Name $ExeStem -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $ExePath } |
        Stop-Process -Force -ErrorAction SilentlyContinue

    # 2. Laukiame, kol exe bus atrakintas
    $unlocked = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $s = [System.IO.File]::Open($ExePath, 'Open', 'ReadWrite', 'None')
            $s.Close()
            $unlocked = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $unlocked) { throw 'Programos failas vis dar naudojamas (užrakintas).' }
    Log 'Executable unlocked.'

    # 3. Atsarginė kopija: _internal pervadiname, exe nukopijuojame
    if (Test-Path -LiteralPath $InternalBackup) { Remove-Item -LiteralPath $InternalBackup -Recurse -Force }
    if (Test-Path -LiteralPath $ExeBackup) { Remove-Item -LiteralPath $ExeBackup -Force }
    if (Test-Path -LiteralPath $Internal) {
        Rename-Item -LiteralPath $Internal -NewName '_internal.old'
    }
    Copy-Item -LiteralPath $ExePath -Destination $ExeBackup -Force
    $backupMade = $true
    Log 'Backup created.'

    # 4. Naujas _internal (švari kopija, be senų failų)
    Run-Robocopy (Join-Path $StagedApp '_internal') $Internal @('/E')

    # 5. Šakniniai failai (exe ir kt.). Vietinių nustatymų failų neliečiame.
    Run-Robocopy $StagedApp $AppDir @('/E', '/IS', '/IT', '/XD', '_internal', '_internal.old',
        '/XF', 'models.json', 'jigs.json', 'config.json', 'history.json')

    # 6. Pagalbiniai failai šalia programos aplanko (klaidos čia nekritinės)
    try {
        $stagedExt = Join-Path $StagingDir 'Chrome_Extension'
        if (Test-Path -LiteralPath $stagedExt) {
            Run-Robocopy $stagedExt (Join-Path $ParentDir 'Chrome_Extension') @('/E', '/IS', '/IT')
        }
        foreach ($name in @('Paleisti_Programa.bat', 'NAUDOJIMO_INSTRUKCIJA.md')) {
            $p = Join-Path $StagingDir $name
            if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination $ParentDir -Force }
        }
    } catch {
        Log "WARNING (companion files): $($_.Exception.Message)"
    }

    $ok = $true
    $message = "Programa atnaujinta į v$NewVersion."
    Log 'Files deployed successfully.'
}
catch {
    $message = $_.Exception.Message
    Log "ERROR: $message"

    # Atstatome senąją versiją
    if ($backupMade) {
        try {
            Log 'Rolling back to previous version...'
            if (Test-Path -LiteralPath $InternalBackup) {
                if (Test-Path -LiteralPath $Internal) { Remove-Item -LiteralPath $Internal -Recurse -Force }
                Rename-Item -LiteralPath $InternalBackup -NewName '_internal'
            }
            if (Test-Path -LiteralPath $ExeBackup) {
                Copy-Item -LiteralPath $ExeBackup -Destination $ExePath -Force
                Remove-Item -LiteralPath $ExeBackup -Force -ErrorAction SilentlyContinue
            }
            Log 'Rollback completed.'
        } catch {
            Log "ROLLBACK ERROR: $($_.Exception.Message)"
            $message = "$message Senosios versijos atstatyti nepavyko."
        }
    }
}
finally {
    $ErrorActionPreference = 'Continue'
    Write-Result $ok $message

    if ($ok) {
        Remove-Item -LiteralPath $InternalBackup -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ExeBackup -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue

    # 7. Programą paleidžiame VISADA (naują arba atstatytą seną)
    try {
        Start-Process -FilePath $ExePath -WorkingDirectory $AppDir
        Log 'Application restarted.'
    } catch {
        Log "RESTART ERROR: $($_.Exception.Message)"
    }
    Log "=== UPDATER FINISHED (ok=$ok) ==="
}
"""


def _ps_quote(value):
    """Paverčia reikšmę į PowerShell eilutę viengubose kabutėse."""
    return "'" + str(value).replace("'", "''") + "'"


def apply_update_and_restart(downloaded_file_path, new_version=""):
    """
    Išarchyvuoja atnaujinimą, paleidžia PowerShell skriptą ir užbaigia programą.
    Sėkmės atveju negrįžta. Klaidos atveju grąžina klaidos tekstą (programa lieka veikti).
    """
    if not getattr(sys, "frozen", False):
        return "Automatinis atnaujinimas veikia tik sukompiliuotoje (.exe) programoje."

    ok, err = validate_update_zip(downloaded_file_path)
    if not ok:
        return err

    exe_path = sys.executable
    app_dir = os.path.dirname(exe_path)
    parent_dir = os.path.dirname(app_dir)
    exe_stem = os.path.splitext(os.path.basename(exe_path))[0]

    # Išarchyvuojame Python'u (patikimiau nei Expand-Archive ir patikriname rezultatą prieš uždarant programą)
    staging_dir = _temp_path("podbase_update_staging")
    try:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        with zipfile.ZipFile(downloaded_file_path) as zf:
            zf.extractall(staging_dir)
    except Exception as e:
        return f"Nepavyko išarchyvuoti atnaujinimo: {e}"

    staged_app = os.path.join(staging_dir, PAYLOAD_DIR_NAME)
    if not os.path.isfile(os.path.join(staged_app, PAYLOAD_EXE_NAME)) or \
            not os.path.isdir(os.path.join(staged_app, "_internal")):
        shutil.rmtree(staging_dir, ignore_errors=True)
        return "Atnaujinimo archyvo struktūra netinkama (nėra programos failų)."

    # Jei dabartinis exe vadinasi kitaip nei naujame pakete, failai nesutaptų
    if os.path.basename(exe_path).lower() != PAYLOAD_EXE_NAME.lower():
        shutil.rmtree(staging_dir, ignore_errors=True)
        return f"Programos failas vadinasi {os.path.basename(exe_path)}, o atnaujinime {PAYLOAD_EXE_NAME}."

    values = {
        "__LOG_PATH__": UPDATER_LOG_PATH,
        "__RESULT_PATH__": UPDATE_RESULT_PATH,
        "__EXE_PATH__": exe_path,
        "__EXE_STEM__": exe_stem,
        "__APP_DIR__": app_dir,
        "__PARENT_DIR__": parent_dir,
        "__STAGING_DIR__": staging_dir,
        "__STAGED_APP__": staged_app,
        "__ZIP_PATH__": downloaded_file_path,
        "__NEW_VERSION__": new_version,
        "__OLD_VERSION__": CURRENT_VERSION,
    }
    script = UPDATER_PS_TEMPLATE
    for key, val in values.items():
        script = script.replace(key, _ps_quote(val))
    script = script.replace("__TARGET_PID__", str(os.getpid()))

    ps1_path = _temp_path("podbase_updater.ps1")
    try:
        if os.path.exists(UPDATE_RESULT_PATH):
            os.remove(UPDATE_RESULT_PATH)
        with open(ps1_path, "w", encoding="utf-8-sig") as f:
            f.write(script)

        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", ps1_path],
            cwd=tempfile.gettempdir(),
            creationflags=_NO_WINDOW,
            close_fds=True
        )
    except Exception as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return f"Nepavyko paleisti atnaujinimo skripto: {e}"

    try:
        QApplication.quit()
    except Exception:
        pass

    # Užbaigiame procesą iškart, kad atsilaisvintų visi failai
    os._exit(0)


def read_last_update_result():
    """Perskaito ir ištrina paskutinio atnaujinimo rezultatą. Grąžina dict arba None."""
    if not os.path.exists(UPDATE_RESULT_PATH):
        return None
    try:
        with open(UPDATE_RESULT_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:
        data = None
    try:
        os.remove(UPDATE_RESULT_PATH)
    except Exception:
        pass
    return data if isinstance(data, dict) else None


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
        self.postponed_version = None
        self._busy = False  # rodomas dialogas arba vyksta atsisiuntimas

    def check_for_updates(self, repo_slug=DEFAULT_GITHUB_REPO, manual=False):
        if self._busy:
            return
        if self.check_worker and self.check_worker.isRunning():
            return

        self.is_manual_check = manual
        self.check_worker = VersionCheckWorker(repo_slug=repo_slug, current_ver=self.current_version)
        self.check_worker.update_available.connect(self.on_update_available)
        self.check_worker.no_update.connect(self.on_no_update)
        self.check_worker.check_failed.connect(self.on_check_failed)
        self.check_worker.start()

    def on_update_available(self, release_info):
        version = release_info.get("version")
        self.update_checked.emit(True, f"Rasta nauja versija v{version}")

        # Automatinio tikrinimo metu netrukdome, jei ši versija buvo atidėta
        if not self.is_manual_check and self.postponed_version == version and time.time() < self.postpone_until:
            return

        if not release_info.get("download_url"):
            if self.is_manual_check:
                InfoBar.warning(
                    title="Nėra diegimo failo",
                    content=f"Versijai v{version} GitHub'e nėra prisegto Podbase_Studio ZIP failo.",
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.parent_window
                )
            return

        self._busy = True
        try:
            dlg = UpdateConfirmDialog(release_info, current_version=self.current_version, parent=self.parent_window)
            accepted = dlg.exec()
        finally:
            self._busy = False

        if accepted:
            self.start_download(release_info)
        else:
            self.postponed_version = version
            self.postpone_until = time.time() + POSTPONE_SECONDS
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

    def start_download(self, release_info):
        version = release_info.get("version", "")
        self.download_worker = DownloadWorker(
            release_info.get("download_url"),
            expected_size=release_info.get("asset_size", 0),
            expected_sha256=release_info.get("asset_sha256"),
            target_filename=f"podbase_update_v{version}.zip"
        )
        prog_dlg = DownloadProgressDialog(self.download_worker, parent=self.parent_window)

        def on_download_finished(dest_path):
            prog_dlg.accept()
            InfoBar.success(
                title="Atsisiųsta!",
                content="Programa atsinaujina ir netrukus persikraus...",
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self.parent_window
            )
            QTimer.singleShot(1200, lambda: self._apply(dest_path, version))

        def on_download_failed(err_msg):
            prog_dlg.reject()
            InfoBar.error(
                title="Atsisiuntimo klaida",
                content=err_msg,
                position=InfoBarPosition.TOP_RIGHT,
                duration=8000,
                parent=self.parent_window
            )

        self.download_worker.finished.connect(on_download_finished)
        self.download_worker.failed.connect(on_download_failed)
        prog_dlg.cancelButton.clicked.connect(self.download_worker.cancel)

        self._busy = True
        try:
            self.download_worker.start()
            prog_dlg.exec()
        finally:
            self._busy = False

    def _apply(self, dest_path, version):
        err = apply_update_and_restart(dest_path, new_version=version)
        if err:
            InfoBar.error(
                title="Atnaujinti nepavyko",
                content=err,
                position=InfoBarPosition.TOP_RIGHT,
                duration=10000,
                parent=self.parent_window
            )

    def show_last_update_result(self):
        """Parodo, kaip baigėsi paskutinis atnaujinimas (kviečiama paleidus programą)."""
        result = read_last_update_result()
        if not result:
            return
        if result.get("ok"):
            InfoBar.success(
                title="Programa atnaujinta",
                content=f"Dabar naudojate v{self.current_version}.",
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self.parent_window
            )
        else:
            InfoBar.error(
                title="Atnaujinti nepavyko",
                content=f"{result.get('message', '')} Palikta v{self.current_version}. "
                        f"Žurnalas: {result.get('log', UPDATER_LOG_PATH)}",
                position=InfoBarPosition.TOP_RIGHT,
                duration=-1,
                parent=self.parent_window
            )
