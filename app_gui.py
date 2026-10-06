# -*- coding: utf-8 -*-
import sys
import os
import re
import json
import time
import math
import copy
import shutil
import hashlib
import tempfile
import threading
from pathlib import Path
from datetime import datetime

# Enable explicit AppUserModelID on Windows so taskbar displays the custom transparent icon
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('podbase.containercreator.studio.v1')
    except Exception:
        pass

from PySide6.QtCore import Qt, QThread, QThreadPool, QRunnable, QLockFile, Signal, QObject, QTimer, QSize, QUrl, QByteArray, QMimeData, QPoint
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QImage, QImageReader, QDrag, QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QSizePolicy, QFileDialog, QSpacerItem, QTableWidgetItem,
    QLabel, QSpinBox, QSplitter, QScrollArea, QStackedWidget, QHeaderView, QMessageBox
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QLocalServer, QLocalSocket

from ui_kit import (
    SubtitleLabel, TitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel, SecondaryLabel, FieldLabel, SectionLabel,
    PrimaryPushButton, PushButton, SuccessPushButton, DangerPushButton, GhostPushButton, ToolButton,
    TransparentToolButton, ComboBox, LineEdit, SearchLineEdit, SpinBox, CardWidget, CheckBox,
    InfoBar, InfoBarPosition, ProgressBar, FIF, setTheme, Theme, isDarkTheme, SmoothScrollArea,
    StatusBadge, TableWidget, SegmentedWidget, UnderlineTabs, ChipGroup, Notice, MessageBoxBase, confirm, divider,
    tokens, status_colors, tabular, theme_signals, apply_app_theme, icon as tinted_icon,
)

# Import auto-updater module
from updater import AppUpdater, CURRENT_VERSION, DEFAULT_GITHUB_REPO, PERIODIC_CHECK_INTERVAL_MS

from podbase_core import (
    BASE_DIR, DESKTOP_DIR, ICON_FILE, get_res_path, LOG_FILE, NETWORK_HOTFOLDER_DEFAULT, add_history_entry,
    get_cleanup_expiry_seconds, prefetch_scanned_files, FILE_TYPE_GROUPS,
    install_exception_logging, load_app_config, load_history_data, load_jigs_data,
    load_models_data, log, missing_label, perform_temp_folders_cleanup, run_container_job,
    safe_folder_name, save_app_config, save_history_data, save_jigs_data, save_models_data,
)
from api_server import FlaskServerThread


# ----------------- MINIATIŪRŲ ATMINTIS -----------------
# Perpiešiant stalą (sukeitimas, dubliavimas) miniatiūros nebeįkeliamos iš naujo.
_THUMB_CACHE_MAX = 300
_thumb_cache = {}


def _thumb_cache_get(url, dim):
    return _thumb_cache.get((url, dim))


def _thumb_cache_put(url, dim, pix, mtime=None):
    if len(_thumb_cache) >= _THUMB_CACHE_MAX:
        _thumb_cache.pop(next(iter(_thumb_cache)))
    _thumb_cache[(url, dim)] = (pix, mtime)


class _ThumbnailLoader(QObject):
    """Vietinių (dažnai tinklo diske esančių) failų miniatiūros dekoduojamos fone."""
    loaded = Signal(str, int, QImage, float)   # kelias, dydis, vaizdas (tuščias = nepasikeitė / klaida), mtime

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.pending = set()
        self.loaded.connect(lambda url, dim, _img, _mtime: self.pending.discard((url, dim)))

    def request(self, path, dim, known_mtime=None):
        """known_mtime: jei failas nuo to laiko nepasikeitė, iš naujo nedekoduojama."""
        if (path, dim) in self.pending:
            return
        self.pending.add((path, dim))
        self.pool.start(_LocalThumbTask(path, dim, self, known_mtime))


class _LocalThumbTask(QRunnable):
    def __init__(self, path, dim, loader, known_mtime=None):
        super().__init__()
        self.path = path
        self.dim = dim
        self.loader = loader
        self.known_mtime = known_mtime

    def run(self):
        img = QImage()
        mtime = 0.0
        try:
            mtime = os.path.getmtime(self.path) if os.path.isfile(self.path) else 0.0
            if mtime and mtime != self.known_mtime:
                reader = QImageReader(self.path)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid() and (size.width() > self.dim * 2 or size.height() > self.dim * 2):
                    # Dideli spaudos failai dekoduojami iškart sumažinti – greičiau ir mažiau atminties
                    reader.setScaledSize(size.scaled(self.dim * 2, self.dim * 2, Qt.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    img = img.scaled(self.dim, self.dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            log.warning(f"Miniatiūros klaida {self.path}: {e}")
        self.loader.loaded.emit(self.path, self.dim, img, mtime)


_thumb_loader = None


def thumbnail_loader():
    global _thumb_loader
    if _thumb_loader is None:
        _thumb_loader = _ThumbnailLoader()
    return _thumb_loader


# ----------------- DRAG & DROP MIME PARSER -----------------
def parse_dropped_items(mime_data):
    items = []
    if mime_data.hasUrls():
        for url in mime_data.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                stem = Path(local_path).stem
                items.append({
                    "name": stem,
                    "url": local_path
                })
            else:
                raw_url = url.toString()
                filename = raw_url.split("?")[0].split("/")[-1]
                stem = os.path.splitext(filename)[0] or "Dizainas"
                items.append({
                    "name": stem,
                    "url": raw_url
                })
    elif mime_data.hasHtml():
        html = mime_data.html()
        src_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        alt_matches = re.findall(r'<img[^>]+alt=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for i, src in enumerate(src_matches):
            alt = alt_matches[i] if i < len(alt_matches) else ""
            filename = src.split("?")[0].split("/")[-1]
            stem = alt.strip() or os.path.splitext(filename)[0] or "Dizainas"
            items.append({
                "name": stem,
                "url": src
            })
    elif mime_data.hasText():
        txt = mime_data.text().strip()
        if not txt.startswith("uv-slot:"):
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://") or os.path.exists(line):
                    is_loc = os.path.exists(line)
                    stem = Path(line).stem if is_loc else os.path.splitext(line.split("?")[0].split("/")[-1])[0]
                    items.append({
                        "name": stem or "Dizainas",
                        "url": line
                    })
                elif line:
                    items.append({
                        "name": line,
                        "url": ""
                    })
    return items

class ContainerJobWorker(QThread):
    progress = Signal(int, int, str)   # (atlikta, iš viso, tekstas)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan

    def run(self):
        try:
            res = run_container_job(self.plan, lambda d, t, txt: self.progress.emit(d, t, txt))
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(res)


# ----------------- RESPONSIVE UV SLOT CARD WITH FLUID DRAG & DROP & ANIMATION -----------------
class UVSlotWidget(QFrame):
    slot_cleared = Signal(int)
    slot_swapped = Signal(int, int)
    slot_duplicated = Signal(int)
    external_items_dropped = Signal(int, list)
    slot_clicked = Signal(int)

    def __init__(self, row, col, parent=None, is_single_row=False):
        super().__init__(parent)
        self.setObjectName("slot")
        self.grid_r = row
        self.grid_c = col
        self.item_idx = None
        self.is_single_row = is_single_row
        thumbnail_loader().loaded.connect(self._on_local_thumb_loaded)
        self.design_name = ""
        self.design_url = ""
        self.current_reply = None
        self.net_mgr = QNetworkAccessManager(self)
        self.drag_start_pos = None

        # Paskutinio generavimo žyma: None, "error" (failas nerastas) arba "warning" (keli kandidatai)
        self.mark = None
        self.is_blinking = False   # suderinamumui: True, kai lizdas pažymėtas kaip nerastas
        self.drag_over = False

        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_Hover, True)

        if self.is_single_row:
            self.setMinimumHeight(180)
            self.setMaximumHeight(320)
        else:
            self.setMinimumHeight(96)

        self.init_ui()
        theme_signals.changed.connect(self.refresh_style)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(2)
        self.badge = QLabel("", self)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.badge.setFixedHeight(20)
        tabular(self.badge)
        top_bar.addWidget(self.badge)
        top_bar.addStretch(1)

        self.btn_dup = TransparentToolButton(FIF.ADD, self)
        self.btn_dup.setFixedSize(26, 26)
        self.btn_dup.setIconSize(QSize(14, 14))
        self.btn_dup.setToolTip("Dublikuoti")
        self.btn_dup.clicked.connect(self.on_dup_clicked)
        self.btn_dup.hide()
        top_bar.addWidget(self.btn_dup)

        self.btn_clear = TransparentToolButton(FIF.DELETE, self)
        self.btn_clear.setFixedSize(26, 26)
        self.btn_clear.setIconSize(QSize(14, 14))
        self.btn_clear.setToolTip("Išimti iš lizdo")
        self.btn_clear.clicked.connect(self.on_clear_clicked)
        self.btn_clear.hide()
        top_bar.addWidget(self.btn_clear)
        layout.addLayout(top_bar)

        self.thumb_label = QLabel(self)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.thumb_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.thumb_label, 1)

        self.title_label = QLabel("Laisvas", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label)

        self.set_empty()

    def start_blinking(self):
        """Lizdo failas nerastas – raudona žyma (be animacijos)."""
        self.set_mark("error")

    def stop_blinking(self):
        if self.mark == "error":
            self.set_mark(None)

    def set_mark(self, mark):
        self.mark = mark
        self.is_blinking = (mark == "error")
        self.refresh_style()

    def on_dup_clicked(self):
        self.stop_blinking()
        if self.item_idx is not None:
            self.slot_duplicated.emit(self.item_idx)

    def on_clear_clicked(self):
        self.stop_blinking()
        if self.item_idx is not None:
            self.slot_cleared.emit(self.item_idx)

    def refresh_style(self):
        t = tokens()
        occupied = self.is_occupied()
        if self.drag_over:
            fg, bg, _ = status_colors("info")
            border, border_style, hover_border = fg, "solid", fg
        elif occupied and self.mark in ("error", "warning"):
            fg, bg, _ = status_colors(self.mark)
            border, border_style, hover_border = fg, "solid", fg
        elif occupied:
            fg, bg = t["text"], t["card"]
            border, border_style, hover_border = t["border"], "solid", t["strong"]
        else:
            fg, bg = t["muted"], t["page"]
            border, border_style, hover_border = t["strong"], "dashed", t["muted"]

        self.setStyleSheet(f"""
            QFrame#slot {{ background: {bg}; border: 1px {border_style} {border}; border-radius: 12px; }}
            QFrame#slot:hover {{ border-color: {hover_border}; }}
        """)

        num = self.badge.property("num") or ""
        if occupied and self.mark in ("error", "warning"):
            m_fg, _m_bg, _ = status_colors(self.mark)
            suffix = "Nerasta" if self.mark == "error" else "Keli failai"
            self.badge.setText(f"{num} · {suffix}")
            self.badge.setStyleSheet(
                f"background: {t['card']}; color: {m_fg}; border-radius: 10px; padding: 0 8px; "
                f"font-size: 11px; font-weight: 600;")
            self.title_label.setStyleSheet(f"color: {m_fg}; font-size: 12px; font-weight: 600;")
        elif occupied:
            self.badge.setText(num)
            self.badge.setStyleSheet(
                f"background: {t['fill']}; color: {t['secondary']}; border-radius: 10px; padding: 0 8px; "
                f"font-size: 11px; font-weight: 600;")
            self.title_label.setStyleSheet(f"color: {t['text']}; font-size: 12px; font-weight: 600;")
        else:
            self.badge.setText(num)
            self.badge.setStyleSheet(
                f"background: transparent; color: {t['muted']}; padding: 0 2px; font-size: 11px; font-weight: 500;")
            self.title_label.setStyleSheet(f"color: {t['muted']}; font-size: 12px;")
            self.thumb_label.setStyleSheet(f"color: {t['disabled']}; font-size: 22px; font-weight: 400;")

    def set_file_info(self, path=None, mtime=0, ambiguous=False):
        """Užvedus pelę parodo, kuris spaudos failas buvo paimtas paskutinio generavimo metu."""
        if not path:
            self.setToolTip("")
            return
        when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else "?"
        tip = f"Failas: {os.path.basename(path)}\nAplankas: {os.path.dirname(path)}\nData: {when}"
        if ambiguous:
            tip = "Rasti keli tinkami failai – paimtas naujausias.\n" + tip
            self.set_mark("warning")
        self.setToolTip(tip)

    def set_data(self, name, url="", item_idx=None):
        self.mark = None
        self.is_blinking = False
        self.setToolTip("")
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        self.item_idx = item_idx
        self.design_name = name.strip()
        self.design_url = url.strip()
        self.btn_dup.show()
        self.btn_clear.show()
        self.title_label.setText(self.design_name)
        self.badge.setProperty("num", f"{item_idx + 1:02d}" if item_idx is not None else "")
        self.refresh_style()

        thumb_dim = 95 if self.is_single_row else 75
        self.thumb_label.clear()
        self.thumb_label.setPixmap(QPixmap())

        if self.design_url:
            cached = _thumb_cache_get(self.design_url, thumb_dim)
            is_remote = self.design_url.lower().startswith(("http://", "https://", "data:"))
            if cached is not None:
                self.thumb_label.setPixmap(cached[0])
                self.thumb_label.setText("")
                if not is_remote:
                    # Fone patikrinama, ar failas nebuvo perrašytas nauja versija
                    thumbnail_loader().request(self.design_url, thumb_dim, known_mtime=cached[1])
            elif is_remote:
                self.load_thumbnail(self.design_url)
            else:
                # Vietinis / tinklo kelias – įkeliama fone, langas neužstringa
                thumbnail_loader().request(self.design_url, thumb_dim)
        else:
            self.thumb_label.setPixmap(tinted_icon(FIF.PHOTO, tokens()["muted"]).pixmap(28, 28))

    def _on_local_thumb_loaded(self, url, dim, img, mtime):
        if img.isNull():
            return
        pix = QPixmap.fromImage(img)
        _thumb_cache_put(url, dim, pix, mtime)
        thumb_dim = 95 if self.is_single_row else 75
        if self.is_occupied() and self.design_url == url and thumb_dim == dim:
            self.thumb_label.setPixmap(pix)
            self.thumb_label.setText("")

    def set_empty(self, placeholder_num=None):
        self.mark = None
        self.is_blinking = False
        self.setToolTip("")
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        self.item_idx = None
        self.design_name = ""
        self.design_url = ""
        self.btn_dup.hide()
        self.btn_clear.hide()
        self.thumb_label.clear()
        self.thumb_label.setPixmap(QPixmap())
        self.thumb_label.setText("+")
        self.title_label.setText("Laisvas")
        self.badge.setProperty("num", f"{placeholder_num:02d}" if placeholder_num is not None else "")
        self.refresh_style()

    def is_occupied(self):
        return bool(self.design_name)

    def load_thumbnail(self, url):
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        req = QNetworkRequest(QUrl(url))
        self.current_reply = self.net_mgr.get(req)
        self.current_reply.finished.connect(lambda reply=self.current_reply, target_url=url: self.on_thumbnail_loaded(reply, target_url))

    def on_thumbnail_loaded(self, reply, target_url):
        if not self.is_occupied() or self.design_url != target_url:
            try:
                reply.deleteLater()
            except Exception:
                pass
            if self.current_reply == reply:
                self.current_reply = None
            return

        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            img = QImage()
            if img.loadFromData(data):
                thumb_dim = 95 if self.is_single_row else 75
                pix = QPixmap.fromImage(img).scaled(thumb_dim, thumb_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                _thumb_cache_put(target_url, thumb_dim, pix)
                self.thumb_label.setPixmap(pix)
                self.thumb_label.setText("")
        
        try:
            reply.deleteLater()
        except Exception:
            pass
        if self.current_reply == reply:
            self.current_reply = None

    def mousePressEvent(self, event):
        self.stop_blinking()
        if event.button() == Qt.LeftButton and self.is_occupied():
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"uv-slot:{self.item_idx if self.item_idx is not None else -1}")
        drag.setMimeData(mime_data)

        pixmap = self.grab()
        drag.setPixmap(pixmap.scaled(80, 85, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(40, 42))
        drag.exec_(Qt.MoveAction)
        self.drag_start_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasImage():
            event.acceptProposedAction()
            self.drag_over = True
            self.refresh_style()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drag_over = False
        self.refresh_style()

    def dropEvent(self, event):
        self.stop_blinking()
        mime = event.mimeData()
        if mime.hasText() and mime.text().startswith("uv-slot:"):
            try:
                src_idx = int(mime.text().split(":")[1])
                target_idx = self.item_idx if self.item_idx is not None else -1
                if src_idx != -1 and src_idx != target_idx:
                    self.slot_swapped.emit(src_idx, target_idx)
            except Exception as e:
                log.warning(f"dropEvent swap error: {e}")
            event.acceptProposedAction()
        else:
            items = parse_dropped_items(mime)
            if items:
                self.external_items_dropped.emit(self.item_idx if self.item_idx is not None else -1, items)
                event.acceptProposedAction()
        self.drag_over = False
        self.refresh_style()


# ----------------- MAIN STUDIO INTERFACE -----------------
class ContainerStudioInterface(QWidget):
    container_generated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.models_data = []
        self.jigs_data = []
        self.active_jig = None
        self.grid_slots = []

        self.beds = [[]]
        self.bed_names = [""]
        self.current_bed_index = 0
        self.missing_items_by_bed = {}
        self.found_items_by_bed = {}      # {stalas: {vieta: (kelias, mtime)}}
        self._prefetch_source = ""
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(700)
        self._prefetch_timer.timeout.connect(lambda: prefetch_scanned_files(self._prefetch_source))
        self.ambiguous_items_by_bed = {}  # {stalas: {vieta, ...}}
        self._job_worker = None
        self._job_context = None

        self.setAcceptDrops(True)
        self.load_data()
        self.init_ui()

    def load_data(self):
        self.models_data = load_models_data()
        self.jigs_data = load_jigs_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Užsakymo kortelė: laukai viršuje, stalo valdymas apačioje
        top_card = CardWidget(self)
        top_v = QVBoxLayout(top_card)
        top_v.setContentsMargins(20, 16, 20, 12)
        top_v.setSpacing(12)

        fields = QHBoxLayout()
        fields.setSpacing(16)

        def field(label_text, widget, stretch=0):
            box = QVBoxLayout()
            box.setSpacing(6)
            box.addWidget(FieldLabel(label_text, self))
            box.addWidget(widget)
            fields.addLayout(box, stretch)

        self.job_edit = LineEdit(self)
        self.job_edit.setPlaceholderText("pvz. BID-6363")
        self.job_edit.setMinimumWidth(200)
        self.job_edit.textChanged.connect(self.on_job_name_changed)
        field("Konteinerio pavadinimas", self.job_edit, 3)

        self.model_combo = ComboBox(self)
        self.model_combo.setMinimumWidth(220)
        self.populate_models_combo()
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        field("Modelis", self.model_combo, 3)

        self.lbl_jig_name = SecondaryLabel("—", self)
        self.lbl_jig_name.setFixedHeight(40)
        tabular(self.lbl_jig_name)
        field("Rėmas", self.lbl_jig_name, 1)

        mode_wrap = QWidget(self)
        mode_l = QHBoxLayout(mode_wrap)
        mode_l.setContentsMargins(0, 0, 0, 0)
        self.lbl_mode_badge = StatusBadge("", "neutral", mode_wrap)
        mode_l.addWidget(self.lbl_mode_badge)
        mode_l.addStretch(1)
        mode_wrap.setFixedHeight(40)
        field("Išvestis", mode_wrap, 1)

        top_v.addLayout(fields)
        top_v.addWidget(divider(self))

        bed_nav_layout = QHBoxLayout()
        bed_nav_layout.setSpacing(8)

        self.btn_prev_bed = ToolButton(FIF.LEFT_ARROW, self)
        self.btn_prev_bed.setFixedSize(32, 32)
        self.btn_prev_bed.setToolTip("Ankstesnis stalas")
        self.btn_prev_bed.clicked.connect(self.prev_bed)
        bed_nav_layout.addWidget(self.btn_prev_bed)

        self.lbl_bed_page = StrongBodyLabel("Stalas 1 iš 1", self)
        tabular(self.lbl_bed_page)
        self.lbl_bed_page.setMinimumWidth(96)
        self.lbl_bed_page.setAlignment(Qt.AlignCenter)
        bed_nav_layout.addWidget(self.lbl_bed_page)

        self.btn_next_bed = ToolButton(FIF.RIGHT_ARROW, self)
        self.btn_next_bed.setFixedSize(32, 32)
        self.btn_next_bed.setToolTip("Kitas stalas")
        self.btn_next_bed.clicked.connect(self.next_bed)
        bed_nav_layout.addWidget(self.btn_next_bed)

        self.btn_add_bed = PushButton(FIF.ADD, "Naujas stalas", self)
        self.btn_add_bed.setFixedHeight(32)
        self.btn_add_bed.clicked.connect(self.add_new_bed)
        bed_nav_layout.addWidget(self.btn_add_bed)

        bed_nav_layout.addSpacing(16)
        self.capacity_bar = ProgressBar(self)
        self.capacity_bar.setFixedWidth(120)
        bed_nav_layout.addWidget(self.capacity_bar)

        self.lbl_capacity_text = SecondaryLabel("0 / 0", self)
        tabular(self.lbl_capacity_text)
        bed_nav_layout.addWidget(self.lbl_capacity_text)

        bed_nav_layout.addStretch(1)

        self.btn_add_slot = PushButton(FIF.ADD, "Pridėti", self)
        self.btn_add_slot.setFixedHeight(32)
        self.btn_add_slot.clicked.connect(self.add_manual_design)
        bed_nav_layout.addWidget(self.btn_add_slot)

        self.btn_reverse = PushButton(FIF.SYNC, "Apversti tvarką", self)
        self.btn_reverse.setFixedHeight(32)
        self.btn_reverse.clicked.connect(self.reverse_slots_order)
        bed_nav_layout.addWidget(self.btn_reverse)

        self.btn_clear_all = DangerPushButton(FIF.DELETE, "Išvalyti stalą", self)
        self.btn_clear_all.setFixedHeight(32)
        self.btn_clear_all.clicked.connect(self.clear_current_bed)
        bed_nav_layout.addWidget(self.btn_clear_all)

        top_v.addLayout(bed_nav_layout)
        main_layout.addWidget(top_card)

        # 2. Stalo tinklelis
        self.grid_widget = CardWidget(self)
        self.grid_widget.setObjectName("uvTableBedGrid")
        self.grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid_widget.setAcceptDrops(True)

        self.table_grid_layout = QGridLayout(self.grid_widget)
        self.table_grid_layout.setContentsMargins(16, 16, 16, 16)
        self.table_grid_layout.setSpacing(8)

        main_layout.addWidget(self.grid_widget, 1)

        # 3. Veiksmų juosta: vienas pagrindinis veiksmas
        bot_layout = QHBoxLayout()
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)

        self.btn_open_folder = PushButton(FIF.FOLDER, "Atidaryti aplanką", self)
        self.btn_open_folder.setFixedHeight(48)
        self.btn_open_folder.clicked.connect(self.open_current_output_folder)
        bot_layout.addWidget(self.btn_open_folder)

        self.lbl_generate_hint = SecondaryLabel("", self)
        bot_layout.addWidget(self.lbl_generate_hint, 1, Qt.AlignRight | Qt.AlignVCenter)

        self.btn_generate = PrimaryPushButton("Sukurti konteinerį", self)
        self.btn_generate.setFixedHeight(48)
        self.btn_generate.setMinimumWidth(260)
        self.btn_generate.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.btn_generate.clicked.connect(self.generate_container)
        bot_layout.addWidget(self.btn_generate)

        main_layout.addLayout(bot_layout)

        self.on_model_changed()

    def on_job_name_changed(self, text):
        if 0 <= self.current_bed_index < len(self.bed_names):
            self.bed_names[self.current_bed_index] = text.strip()

    def open_current_output_folder(self):
        m_data = self.get_selected_model_data()
        dest = m_data.get("destination", "") if m_data else ""
        output_mode = m_data.get("output_mode", "temp_folder") if m_data else "temp_folder"
        
        if output_mode == "direct_hotfolder" and dest:
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception:
                pass
            if os.path.exists(dest):
                os.startfile(dest)
                return

        if dest and os.path.exists(dest):
            os.startfile(dest)
            return

        if os.path.exists(DESKTOP_DIR):
            os.startfile(DESKTOP_DIR)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasText() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        items = parse_dropped_items(event.mimeData())
        if items:
            self.place_dropped_items(items)
            event.acceptProposedAction()

    def update_bed_container_style(self):
        for row in self.grid_slots:
            for s in row:
                s.refresh_style()

    def populate_models_combo(self):
        self.model_combo.clear()
        for m in self.models_data:
            self.model_combo.addItem(m.get("name", ""))

    def get_selected_model_data(self):
        name = self.model_combo.currentText()
        return next((m for m in self.models_data if m.get("name") == name), None)

    def get_active_jig_capacity(self):
        if self.active_jig:
            return self.active_jig.get("rows", 2) * self.active_jig.get("cols", 5)
        return 10

    def on_model_changed(self):
        m_data = self.get_selected_model_data()
        if not m_data:
            return
        # Išankstinis skenavimas su delsa – vartant modelių sąrašą nepaleidžiama daug skenavimų
        self._prefetch_source = m_data.get("source", "")
        self._prefetch_timer.start()

        jig_id = m_data.get("jig_id", "jig_2x5")
        jig = next((j for j in self.jigs_data if j.get("id") == jig_id), None)
        if not jig:
            jig = self.jigs_data[0] if self.jigs_data else {"rows": 2, "cols": 5, "name": "Standartinis 2x5"}

        self.active_jig = jig
        self.lbl_jig_name.setText(f"{jig.get('name', 'Standartinis')} · {jig.get('rows', 2)} × {jig.get('cols', 5)}")
        self._apply_output_mode(m_data.get("output_mode", "temp_folder"))

        self.build_grid_layout()
        self.render_current_bed()

    def build_grid_layout(self):
        if not self.active_jig:
            return
        rows = self.active_jig.get("rows", 2)
        cols = self.active_jig.get("cols", 5)
        is_single_row = (rows == 1)

        while self.table_grid_layout.count():
            item = self.table_grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for r in range(25):
            self.table_grid_layout.setRowStretch(r, 0)
        for c in range(35):
            self.table_grid_layout.setColumnStretch(c, 0)

        self.grid_slots = []

        if is_single_row:
            self.table_grid_layout.setRowStretch(0, 1)
            self.table_grid_layout.setRowStretch(1, 0)
            self.table_grid_layout.setRowStretch(2, 1)

            row_slots = []
            for c in range(cols):
                self.table_grid_layout.setColumnStretch(c, 1)
                slot = UVSlotWidget(0, c, self.grid_widget, is_single_row=True)
                slot.slot_cleared.connect(self.on_slot_cleared)
                slot.slot_swapped.connect(self.on_slots_swapped)
                slot.slot_duplicated.connect(self.on_slot_duplicated)
                slot.external_items_dropped.connect(self.on_external_items_dropped)
                self.table_grid_layout.addWidget(slot, 1, c)
                row_slots.append(slot)
            self.grid_slots.append(row_slots)
        else:
            for r in range(rows):
                self.table_grid_layout.setRowStretch(r, 1)
            for c in range(cols):
                self.table_grid_layout.setColumnStretch(c, 1)

            for r in range(rows):
                row_slots = []
                for c in range(cols):
                    slot = UVSlotWidget(r, c, self.grid_widget, is_single_row=False)
                    slot.slot_cleared.connect(self.on_slot_cleared)
                    slot.slot_swapped.connect(self.on_slots_swapped)
                    slot.slot_duplicated.connect(self.on_slot_duplicated)
                    slot.external_items_dropped.connect(self.on_external_items_dropped)
                    self.table_grid_layout.addWidget(slot, r, c)
                    row_slots.append(slot)
                self.grid_slots.append(row_slots)

    def _clear_job_marks(self):
        """Stalo turinys pasikeitė – ankstesnio generavimo žymos nebegalioja."""
        self.missing_items_by_bed.clear()
        self.found_items_by_bed.clear()
        self.ambiguous_items_by_bed.clear()

    def render_current_bed(self):
        if not self.active_jig:
            return

        rows = self.active_jig.get("rows", 2)
        cols = self.active_jig.get("cols", 5)

        if self.current_bed_index >= len(self.beds):
            self.current_bed_index = max(0, len(self.beds) - 1)

        while len(self.bed_names) < len(self.beds):
            idx = len(self.bed_names)
            base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
            new_name = f"{base_name}_{idx + 1}" if base_name else f"Stalas_{idx + 1}"
            self.bed_names.append(new_name)

        current_name = self.bed_names[self.current_bed_index] if self.current_bed_index < len(self.bed_names) else ""
        self.job_edit.blockSignals(True)
        self.job_edit.setText(current_name)
        self.job_edit.blockSignals(False)

        current_items = [it for it in self.beds[self.current_bed_index] if it and it.get("name")]
        num_items = len(current_items)
        missing_indices = self.missing_items_by_bed.get(self.current_bed_index, set())
        found_info = self.found_items_by_bed.get(self.current_bed_index, {})
        ambiguous_indices = self.ambiguous_items_by_bed.get(self.current_bed_index, set())

        # 1. Reset all slots to completely empty
        for r in range(rows):
            for c in range(cols):
                if r < len(self.grid_slots) and c < len(self.grid_slots[r]):
                    self.grid_slots[r][c].set_empty()

        # 2. Map items dynamically to grid coordinates
        k_bottom = min(num_items, cols)
        for i in range(num_items):
            it = current_items[i]
            if i < cols:
                r = rows - 1
                c = (k_bottom - 1) - i
            else:
                row_from_bottom = i // cols
                r = (rows - 1) - row_from_bottom
                c = (cols - 1) - (i % cols)

            if 0 <= r < len(self.grid_slots) and 0 <= c < len(self.grid_slots[r]):
                slot_w = self.grid_slots[r][c]
                slot_w.set_data(it.get("name", ""), it.get("url", ""), item_idx=i)
                if i in missing_indices:
                    slot_w.start_blinking()
                else:
                    slot_w.stop_blinking()
                if i in found_info:
                    slot_w.set_file_info(*found_info[i], ambiguous=i in ambiguous_indices)

        self.update_bed_navigation()

    def save_current_bed_state(self):
        while len(self.bed_names) < len(self.beds):
            self.bed_names.append("")
        if self.current_bed_index < len(self.bed_names):
            self.bed_names[self.current_bed_index] = self.job_edit.text().strip()

    def update_bed_navigation(self):
        total_beds = len(self.beds)
        curr_page = self.current_bed_index + 1

        self.lbl_bed_page.setText(f"Stalas {curr_page} iš {total_beds}")
        self.btn_prev_bed.setEnabled(self.current_bed_index > 0)
        self.btn_next_bed.setEnabled(self.current_bed_index < total_beds - 1)

        capacity = self.get_active_jig_capacity()
        occupied = len([it for it in self.beds[self.current_bed_index] if it and it.get("name")])
        pct = int((occupied / capacity) * 100) if capacity > 0 else 0

        self.capacity_bar.setValue(pct)
        self.lbl_capacity_text.setText(f"{occupied} / {capacity}")

    def prev_bed(self):
        self.save_current_bed_state()
        if self.current_bed_index > 0:
            self.current_bed_index -= 1
            self.render_current_bed()

    def next_bed(self):
        self.save_current_bed_state()
        if self.current_bed_index < len(self.beds) - 1:
            self.current_bed_index += 1
            self.render_current_bed()

    def add_new_bed(self):
        self.save_current_bed_state()
        self.beds.append([])

        base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
        new_bed_num = len(self.beds)
        new_name = f"{base_name}_{new_bed_num}" if base_name else f"Stalas_{new_bed_num}"
        self.bed_names.append(new_name)

        self.current_bed_index = len(self.beds) - 1
        self.render_current_bed()
        InfoBar.success(
            title="Pridėtas naujas stalas",
            content=f"Stalas {self.current_bed_index + 1}: {new_name}",
            orient=Qt.Horizontal,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def on_slot_cleared(self, item_idx):
        self._clear_job_marks()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= item_idx < len(curr_items):
                del curr_items[item_idx]
                self.render_current_bed()

    def on_slots_swapped(self, src_idx, target_idx):
        self._clear_job_marks()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= src_idx < len(curr_items):
                if target_idx == -1 or target_idx >= len(curr_items):
                    item = curr_items.pop(src_idx)
                    curr_items.append(item)
                elif 0 <= target_idx < len(curr_items):
                    curr_items[src_idx], curr_items[target_idx] = curr_items[target_idx], curr_items[src_idx]
                self.render_current_bed()

    def on_slot_duplicated(self, item_idx):
        self._clear_job_marks()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= item_idx < len(curr_items):
                dup_item = dict(curr_items[item_idx])
                capacity = self.get_active_jig_capacity()

                if len(curr_items) < capacity:
                    curr_items.append(dup_item)
                    self.render_current_bed()
                    InfoBar.success(
                        title="Dizainas dublikuotas",
                        content="Kopija pridėta į stalą.",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=2500,
                        parent=self
                    )
                else:
                    self.save_current_bed_state()
                    next_bed_idx = self.current_bed_index + 1
                    if next_bed_idx >= len(self.beds):
                        self.beds.append([])
                        base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
                        self.bed_names.append(f"{base_name}_{len(self.beds)}" if base_name else f"Stalas_{len(self.beds)}")

                    self.current_bed_index = next_bed_idx
                    self.beds[self.current_bed_index].append(dup_item)
                    self.render_current_bed()
                    InfoBar.info(
                        title="Rėmas buvo pilnas",
                        content=f"Kopija pridėta į stalą {self.current_bed_index + 1}.",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=3000,
                        parent=self
                    )

    def on_external_items_dropped(self, target_idx, items):
        self._clear_job_marks()
        if not items:
            return

        curr_items = self.beds[self.current_bed_index]
        if len(items) == 1 and target_idx != -1 and 0 <= target_idx < len(curr_items):
            curr_items[target_idx] = items[0]
            self.render_current_bed()
            InfoBar.success(
                title="Dizainas pakeistas",
                content=f"Lizdas {target_idx + 1} pakeistas nauju dizainu.",
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500,
                parent=self
            )
        else:
            self.place_dropped_items(items)

    def place_dropped_items(self, items):
        if not items:
            return

        self._clear_job_marks()
        self.save_current_bed_state()
        capacity = self.get_active_jig_capacity()

        for it in items:
            curr_items = self.beds[self.current_bed_index]
            if len(curr_items) < capacity:
                curr_items.append(it)
            else:
                self.save_current_bed_state()
                next_bed_idx = self.current_bed_index + 1
                if next_bed_idx >= len(self.beds):
                    self.beds.append([])
                    base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
                    self.bed_names.append(f"{base_name}_{len(self.beds)}" if base_name else f"Stalas_{len(self.beds)}")
                self.current_bed_index = next_bed_idx
                self.beds[self.current_bed_index].append(it)

        self.render_current_bed()
        InfoBar.success(
            title="Dizainai įkelti",
            content=f"Įkelta {len(items)} vnt.",
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def add_manual_design(self):
        self._clear_job_marks()
        capacity = self.get_active_jig_capacity()
        curr_items = self.beds[self.current_bed_index]

        if len(curr_items) < capacity:
            curr_items.append({"name": f"PID-{1000 + len(curr_items) + 1:04d}", "url": ""})
            self.render_current_bed()
        else:
            self.add_new_bed()
            self.beds[self.current_bed_index].append({"name": "PID-1001", "url": ""})
            self.render_current_bed()

    def clear_current_bed(self):
        if self.beds[self.current_bed_index] and not confirm(
                self, "Išvalyti stalą?",
                f"Iš stalo {self.current_bed_index + 1} bus išimti visi dizainai. Spaudos failai neliečiami.",
                "Išvalyti"):
            return
        self._clear_job_marks()
        self.beds[self.current_bed_index] = []
        self.render_current_bed()

    def reverse_slots_order(self):
        self._clear_job_marks()
        self.beds[self.current_bed_index].reverse()
        self.render_current_bed()

    def set_data_from_extension(self, payload):
        self._clear_job_marks()
        designs = payload.get("designs", [])
        model = payload.get("model", None)
        job_name = payload.get("jobName", None) or ""

        matched_idx = -1
        if model:
            for idx, m in enumerate(self.models_data):
                m_name = m.get("name", "")
                aliases = m.get("aliases", [])
                if model.lower() == m_name.lower() or any(model.lower() == a.lower() for a in aliases) or any(a.lower() in model.lower() for a in aliases):
                    matched_idx = idx
                    break

        current_idx = self.model_combo.currentIndex()
        is_same_model = (matched_idx != -1 and matched_idx == current_idx)

        capacity = self.get_active_jig_capacity()

        if is_same_model:
            self.save_current_bed_state()

            for d in designs:
                placed = False
                for b_idx in range(len(self.beds)):
                    bed_items = self.beds[b_idx]
                    if len(bed_items) < capacity:
                        bed_items.append(d)
                        placed = True
                        break

                if not placed:
                    new_b_num = len(self.beds) + 1
                    self.beds.append([d])
                    new_b_name = f"{job_name}_{new_b_num}" if job_name else f"Stalas_{new_b_num}"
                    self.bed_names.append(new_b_name)

            self.render_current_bed()
            InfoBar.info(
                title="Pridėta prie esamo užsakymo",
                content=f"Pridėta {len(designs)} vnt. Iš viso stalų: {len(self.beds)}.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self
            )
        else:
            if matched_idx != -1:
                self.model_combo.setCurrentIndex(matched_idx)

            capacity = self.get_active_jig_capacity()

            self.beds = []
            self.bed_names = []
            num_beds = max(1, math.ceil(len(designs) / capacity)) if capacity > 0 else 1

            for b in range(num_beds):
                start_i = b * capacity
                end_i = start_i + capacity
                chunk = designs[start_i:end_i]
                self.beds.append(chunk)

                if num_beds == 1:
                    self.bed_names.append(job_name)
                else:
                    self.bed_names.append(f"{job_name}_{b+1}" if job_name else f"Stalas_{b+1}")

            self.current_bed_index = 0
            self.render_current_bed()

            msg = f"{job_name or 'Užsakymas'}: {len(designs)} vnt."
            if len(self.beds) > 1:
                msg += f" ({len(self.beds)} stalai)."

            InfoBar.success(
                title="Užsakymas gautas iš naršyklės",
                content=msg,
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self
            )

    def load_from_history_entry(self, entry):
        self._clear_job_marks()
        job_name = entry.get("job_name", "")
        model_name = entry.get("model_name", "")
        beds = entry.get("beds", [[]])
        bed_names = entry.get("bed_names", [])

        idx = self.model_combo.findText(model_name)
        if idx != -1:
            self.model_combo.setCurrentIndex(idx)

        self.beds = beds if beds else [[]]
        if bed_names and len(bed_names) == len(self.beds):
            self.bed_names = bed_names
        else:
            self.bed_names = []
            for i in range(len(self.beds)):
                if len(self.beds) == 1:
                    self.bed_names.append(job_name)
                else:
                    self.bed_names.append(f"{job_name}_{i+1}" if job_name else f"Stalas_{i+1}")

        self.current_bed_index = 0
        self.render_current_bed()

        InfoBar.success(
            title="Istorijos užsakymas įkeltas",
            content=f"Užsakymas „{job_name}“ paruoštas redaguoti.",
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
            parent=self
        )

    def generate_container(self):
        if self._job_worker is not None and self._job_worker.isRunning():
            return

        self.save_current_bed_state()
        self._clear_job_marks()

        valid_beds = []
        for idx, bed_items in enumerate(self.beds):
            occupied = [it for it in bed_items if it is not None and it.get("name")]
            if occupied:
                valid_beds.append((idx + 1, occupied))

        if not valid_beds:
            InfoBar.warning(
                title="Tuščias stalas",
                content="Pridėkite bent vieną dizainą į stalą.",
                position=InfoBarPosition.TOP,
                parent=self
            )
            return

        m_data = self.get_selected_model_data()
        if not m_data:
            InfoBar.error(
                title="Klaida",
                content="Pasirinkite modelį.",
                position=InfoBarPosition.TOP,
                parent=self
            )
            return

        source_dir = m_data.get("source", "").strip()
        dest_dir = m_data.get("destination", "").strip()
        output_mode = m_data.get("output_mode", "temp_folder")
        file_types = m_data.get("file_types") or []
        is_direct_hotfolder = (output_mode == "direct_hotfolder")

        if is_direct_hotfolder and not dest_dir:
            InfoBar.error(
                title="Nenurodytas HotFolderio kelias",
                content="Šiam modeliui nustatymuose nenurodytas 'Paskirtis (HotFolderis)' kelias.\nNustatykite jį Nustatymų skirtuke.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self
            )
            return

        beds_plan = []
        for bed_num, occupied_items in valid_beds:
            real_bed_idx = bed_num - 1
            if real_bed_idx < len(self.bed_names) and self.bed_names[real_bed_idx]:
                bed_title = self.bed_names[real_bed_idx]
            else:
                bed_title = f"Stalas_{bed_num}"
            clean_bed_title = safe_folder_name(bed_title, f"Stalas_{bed_num}")
            beds_plan.append({
                "bed_idx": real_bed_idx,
                "title": clean_bed_title,
                "items": [it.get("name", "") for it in occupied_items]
            })

        plan = {
            "source_dir": source_dir,
            "dest_dir": dest_dir,
            "hotfolder": is_direct_hotfolder,
            "file_types": file_types,
            "beds": beds_plan
        }

        main_job_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else m_data.get("name", "Job")
        self._job_context = {
            "is_hot": is_direct_hotfolder,
            "dest_dir": dest_dir,
            "bed_count": len(valid_beds),
            "beds_snapshot": [[(it or {}).get("name") for it in bed] for bed in self.beds],
            "history": {
                "id": f"hist_{int(time.time())}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "job_name": main_job_name,
                "bed_names": list(self.bed_names),
                "model_name": m_data.get("name", ""),
                "jig_name": self.active_jig.get("name", "") if self.active_jig else "",
                "output_mode": output_mode,
                "total_beds": len(valid_beds),
                "total_designs": sum(len(items) for _, items in valid_beds),
                "beds": copy.deepcopy(self.beds),
                "source_dir": source_dir,
                "dest_dir": dest_dir,
                "file_types": file_types
            }
        }

        self._set_generate_busy(True)
        worker = ContainerJobWorker(plan, self)
        worker.progress.connect(self._on_job_progress)
        worker.finished_ok.connect(self._on_job_finished)
        worker.failed.connect(self._on_job_failed)
        self._job_worker = worker
        worker.start()

    def _apply_output_mode(self, output_mode):
        if output_mode == "direct_hotfolder":
            self.btn_generate.setText("Siųsti į HotFolderį")
            self.btn_open_folder.setText("Atidaryti HotFolderį")
            self.lbl_mode_badge.set_status("info", "Tiesiogiai į HotFolderį")
        else:
            minutes = round(get_cleanup_expiry_seconds() / 60)
            self.btn_generate.setText("Sukurti konteinerį")
            self.btn_open_folder.setText("Atidaryti aplanką")
            self.lbl_mode_badge.set_status("neutral", f"Laikinas aplankas · {minutes} min.")

    def _set_generate_busy(self, busy):
        self.btn_generate.setEnabled(not busy)
        if busy:
            self.btn_generate.setText("Ieškoma spaudos failų…")
            return
        self.lbl_generate_hint.setText("")
        m_data = self.get_selected_model_data() or {}
        self._apply_output_mode(m_data.get("output_mode", "temp_folder"))

    def _on_job_progress(self, done, total, text):
        self.btn_generate.setText("Vykdoma…")
        self.lbl_generate_hint.setText(text)

    def _on_job_failed(self, err_msg):
        self._set_generate_busy(False)
        InfoBar.error(
            title="Nepavyko sukurti konteinerio",
            content=err_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self
        )

    def _on_job_finished(self, res):
        self._set_generate_busy(False)
        ctx = self._job_context or {}
        is_hot = ctx.get("is_hot", False)

        history_entry = dict(ctx.get("history", {}))
        history_entry["folders"] = res.get("folders", [])
        try:
            add_history_entry(history_entry)
        except Exception as e:
            log.warning(f"[history klaida]: {e}")
        self.container_generated.emit()

        missing = res.get("missing", [])
        errors = res.get("errors", [])

        warnings = res.get("warnings", [])

        # Žymos ant lizdų – tik jei stalas nepasikeitė, kol vyko kopijavimas
        current_snapshot = [[(it or {}).get("name") for it in bed] for bed in self.beds]
        if current_snapshot == ctx.get("beds_snapshot"):
            self._clear_job_marks()
            for bed_idx, item_idx, _name, path, mtime in res.get("found", []):
                self.found_items_by_bed.setdefault(bed_idx, {})[item_idx] = (path, mtime)
            for warn_key in res.get("ambiguous", []):
                self.ambiguous_items_by_bed.setdefault(warn_key[0], set()).add(warn_key[1])
            for bed_idx, item_idx, _name in missing:
                self.missing_items_by_bed.setdefault(bed_idx, set()).add(item_idx)
            if self.missing_items_by_bed:
                self.current_bed_index = min(self.missing_items_by_bed.keys())
        self.render_current_bed()

        if warnings:
            InfoBar.warning(
                title="Patikrinkite: rasti keli tinkami failai",
                content="\n".join(warnings[:5]) + (f"\n... ir dar {len(warnings) - 5}" if len(warnings) > 5 else ""),
                orient=Qt.Vertical,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=10000,
                parent=self
            )

        if not is_hot:
            for fold in res.get("folders", []):
                try:
                    if os.path.exists(fold):
                        os.startfile(fold)
                except Exception as e:
                    log.warning(f"startfile error: {e}")

        if missing:
            names = ", ".join(missing_label(n) for _, _, n in missing)
            content = f"Nerasti {len(missing)} failai: {names}\nNukopijuota: {res.get('copied', 0)}. Trūkstami lizdai pažymėti raudonai."
            if errors:
                content += "\nKopijavimo klaidos: " + "; ".join(errors[:3])
            InfoBar.error(
                title="Ne visi failai išsiųsti",
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=-1,
                parent=self
            )
            return

        if is_hot:
            msg = f"{res.get('copied', 0)} vnt. nusiųsta į HotFolderį: {ctx.get('dest_dir', '')}"
        else:
            minutes = round(get_cleanup_expiry_seconds() / 60)
            msg = f"{ctx.get('bed_count', 0)} st., {res.get('copied', 0)} failų. Aplankas bus išvalytas po {minutes} min."
        InfoBar.success(
            title="Konteineris sukurtas",
            content=msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4500,
            parent=self
        )

# ----------------- HISTORY INTERFACE -----------------
class HistoryInterface(QWidget):
    load_order_to_studio = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_items = []
        self.filtered_items = []
        self.selected_item = None
        self._job_worker = None
        self._regen_btn_text = "Siųsti dar kartą"
        self.init_ui()
        self.reload_history()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(TitleLabel("Generavimo istorija", self))
        top_bar.addStretch(1)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("Ieškoti pagal užsakymą ar modelį")
        self.search_edit.setFixedWidth(280)
        self.search_edit.textChanged.connect(self.filter_history)
        top_bar.addWidget(self.search_edit)

        self.btn_refresh = PushButton(FIF.SYNC, "Atnaujinti", self)
        self.btn_refresh.clicked.connect(self.reload_history)
        top_bar.addWidget(self.btn_refresh)

        self.btn_clear_history = DangerPushButton(FIF.DELETE, "Išvalyti istoriją", self)
        self.btn_clear_history.clicked.connect(self.clear_all_history)
        top_bar.addWidget(self.btn_clear_history)

        main_layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(16)
        splitter.setChildrenCollapsible(False)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Data", "Užsakymas", "Modelis", "Stalai", "Dizainai"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(self.on_row_selected)
        table_layout.addWidget(self.table)

        splitter.addWidget(table_card)

        self.detail_card = CardWidget(self)
        self.detail_card.setMinimumWidth(360)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(20, 20, 20, 20)
        detail_layout.setSpacing(12)

        self.lbl_detail_title = SubtitleLabel("Pasirinkite įrašą", self)
        detail_layout.addWidget(self.lbl_detail_title)

        self.lbl_detail_info = SecondaryLabel("Pasirinkite užsakymą lentelėje, kad pamatytumėte detales.", self)
        self.lbl_detail_info.setWordWrap(True)
        detail_layout.addWidget(self.lbl_detail_info)

        detail_layout.addWidget(divider(self))

        self.preview_scroll = SmoothScrollArea(self)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_container.setObjectName("scrollContent")
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 4, 0)
        self.preview_layout.setSpacing(2)
        self.preview_scroll.setWidget(self.preview_container)
        detail_layout.addWidget(self.preview_scroll, 1)

        actions_box = QVBoxLayout()
        actions_box.setSpacing(8)

        self.btn_load_to_studio = PrimaryPushButton(FIF.EDIT, "Įkelti į redaktorių", self)
        self.btn_load_to_studio.setFixedHeight(44)
        self.btn_load_to_studio.clicked.connect(self.load_selected_to_studio)
        self.btn_load_to_studio.setEnabled(False)
        actions_box.addWidget(self.btn_load_to_studio)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_quick_regenerate = PushButton(FIF.SYNC, self._regen_btn_text, self)
        self.btn_quick_regenerate.clicked.connect(self.quick_regenerate_selected)
        self.btn_quick_regenerate.setEnabled(False)
        row.addWidget(self.btn_quick_regenerate, 1)

        self.btn_open_saved_folder = PushButton(FIF.FOLDER, "Atidaryti aplanką", self)
        self.btn_open_saved_folder.clicked.connect(self.open_selected_folder)
        self.btn_open_saved_folder.setEnabled(False)
        row.addWidget(self.btn_open_saved_folder, 1)
        actions_box.addLayout(row)

        self.btn_del_entry = DangerPushButton(FIF.DELETE, "Ištrinti įrašą", self)
        self.btn_del_entry.setFixedHeight(32)
        self.btn_del_entry.setVariant("danger")
        self.btn_del_entry.clicked.connect(self.delete_selected_entry)
        self.btn_del_entry.setEnabled(False)
        actions_box.addWidget(self.btn_del_entry, 0, Qt.AlignLeft)

        detail_layout.addLayout(actions_box)
        splitter.addWidget(self.detail_card)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

    def reload_history(self):
        self.history_items = load_history_data()
        self.filter_history(self.search_edit.text().strip())

    def filter_history(self, search_text=""):
        s = search_text.lower()
        if not s:
            self.filtered_items = list(self.history_items)
        else:
            self.filtered_items = [
                it for it in self.history_items
                if s in it.get("job_name", "").lower()
                or s in it.get("model_name", "").lower()
                or s in it.get("timestamp", "").lower()
            ]

        self.table.setRowCount(len(self.filtered_items))
        for row, it in enumerate(self.filtered_items):
            self.table.setItem(row, 0, QTableWidgetItem(it.get("timestamp", "")))
            self.table.setItem(row, 1, QTableWidgetItem(it.get("job_name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(it.get("model_name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(f"{it.get('total_beds', 1)} st."))
            self.table.setItem(row, 4, QTableWidgetItem(f"{it.get('total_designs', 0)} vnt."))

        if self.filtered_items:
            self.table.selectRow(0)
            self.on_row_selected(0, 0)
        else:
            self.selected_item = None
            self.lbl_detail_title.setText("Istorija tuščia")
            self.lbl_detail_info.setText("Sugeneruoti konteineriai atsiras čia.")
            self.clear_preview_layout()
            self.btn_load_to_studio.setEnabled(False)
            self.btn_quick_regenerate.setEnabled(False)
            self.btn_open_saved_folder.setEnabled(False)
            self.btn_del_entry.setEnabled(False)

    def clear_preview_layout(self):
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def on_row_selected(self, row, col):
        if 0 <= row < len(self.filtered_items):
            self.selected_item = self.filtered_items[row]
            it = self.selected_item

            self.lbl_detail_title.setText(it.get('job_name', 'Užsakymas') or "Užsakymas")
            mode = "HotFolderis" if it.get("output_mode") == "direct_hotfolder" else "Laikinas aplankas"
            muted = tokens()["muted"]
            rows = [("Data", it.get('timestamp', '')), ("Modelis", it.get('model_name', '')),
                    ("Rėmas", it.get('jig_name', '')), ("Išvestis", mode),
                    ("Kiekis", f"{it.get('total_beds', 1)} st. · {it.get('total_designs', 0)} vnt.")]
            info_str = "<table cellspacing='0' cellpadding='2'>" + "".join(
                f"<tr><td style='color:{muted}; padding-right:16px'>{k}</td><td>{v}</td></tr>" for k, v in rows
            ) + "</table>"
            self.lbl_detail_info.setText(info_str)

            self.clear_preview_layout()
            beds = it.get("beds", [])
            bed_names = it.get("bed_names", [])
            for b_idx, bed_items in enumerate(beds):
                b_name = bed_names[b_idx] if b_idx < len(bed_names) and bed_names[b_idx] else f"Stalas #{b_idx + 1}"
                b_lbl = SectionLabel(b_name, self.preview_container)
                b_lbl.setContentsMargins(0, 8 if b_idx else 0, 0, 4)
                self.preview_layout.addWidget(b_lbl)

                for s_idx, d in enumerate(bed_items):
                    if d:
                        row_lbl = QLabel(
                            f"<span style='color:{tokens()['muted']}'>{s_idx + 1:02d}</span>&nbsp;&nbsp;{d.get('name')}",
                            self.preview_container)
                        row_lbl.setStyleSheet("font-size: 13px; padding: 2px 0;")
                        self.preview_layout.addWidget(row_lbl)

            self.preview_layout.addStretch(1)

            self.btn_load_to_studio.setEnabled(True)
            self.btn_quick_regenerate.setEnabled(True)
            self.btn_open_saved_folder.setEnabled(True)
            self.btn_del_entry.setEnabled(True)

    def load_selected_to_studio(self):
        if self.selected_item:
            self.load_order_to_studio.emit(self.selected_item)

    def quick_regenerate_selected(self):
        if not self.selected_item:
            return
        if self._job_worker is not None and self._job_worker.isRunning():
            return

        it = self.selected_item
        source_dir = it.get("source_dir", "").strip()
        dest_dir = it.get("dest_dir", "").strip()
        job_title = it.get("job_name", "Job")
        beds = it.get("beds", [])
        bed_names = it.get("bed_names", [])
        is_direct_hotfolder = (it.get("output_mode", "temp_folder") == "direct_hotfolder")
        model = next((m for m in load_models_data() if m.get("name") == it.get("model_name")), {})
        file_types = (model.get("file_types") if "file_types" in model else it.get("file_types")) or []

        if is_direct_hotfolder and not dest_dir:
            InfoBar.error(
                title="Nenurodytas HotFolderis",
                content="Šiam modeliui nenurodytas paskirties HotFolderis.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self
            )
            return

        valid_beds = []
        for idx, bed_items in enumerate(beds):
            occupied = [x for x in bed_items if x and x.get("name")]
            if occupied:
                valid_beds.append((idx + 1, occupied))

        beds_plan = []
        for bed_num, occupied_items in valid_beds:
            real_bed_idx = bed_num - 1
            if real_bed_idx < len(bed_names) and bed_names[real_bed_idx]:
                bed_title = bed_names[real_bed_idx]
            else:
                bed_title = f"{job_title}_{bed_num}" if len(valid_beds) > 1 else job_title
            clean_bed_title = safe_folder_name(bed_title, f"Stalas_{bed_num}")
            beds_plan.append({
                "bed_idx": real_bed_idx,
                "title": clean_bed_title,
                "items": [x.get("name", "") for x in occupied_items]
            })

        plan = {
            "source_dir": source_dir,
            "dest_dir": dest_dir,
            "hotfolder": is_direct_hotfolder,
            "file_types": file_types,
            "beds": beds_plan
        }

        self.btn_quick_regenerate.setEnabled(False)
        self.btn_quick_regenerate.setText("Siunčiama…")
        worker = ContainerJobWorker(plan, self)
        worker.progress.connect(lambda d, t, txt: self.btn_quick_regenerate.setText("Siunčiama…"))
        worker.finished_ok.connect(lambda res: self._on_regenerate_finished(res, job_title, is_direct_hotfolder))
        worker.failed.connect(self._on_regenerate_failed)
        self._job_worker = worker
        worker.start()

    def _restore_regenerate_button(self):
        self.btn_quick_regenerate.setText(self._regen_btn_text)
        self.btn_quick_regenerate.setEnabled(self.selected_item is not None)

    def _on_regenerate_failed(self, err_msg):
        self._restore_regenerate_button()
        InfoBar.error(
            title="Nepavyko išsiųsti",
            content=err_msg,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self
        )

    def _on_regenerate_finished(self, res, job_title, is_direct_hotfolder):
        self._restore_regenerate_button()

        if not is_direct_hotfolder:
            for fold in res.get("folders", []):
                try:
                    if os.path.exists(fold):
                        os.startfile(fold)
                except Exception:
                    pass

        warnings = res.get("warnings", [])
        if warnings:
            InfoBar.warning(
                title="Patikrinkite: rasti keli tinkami failai",
                content="\n".join(warnings[:5]) + (f"\n... ir dar {len(warnings) - 5}" if len(warnings) > 5 else ""),
                orient=Qt.Vertical,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=10000,
                parent=self
            )

        missing = res.get("missing", [])
        if missing:
            names = ", ".join(missing_label(n) for _, _, n in missing)
            InfoBar.error(
                title="Ne visi failai rasti",
                content=f"Užsakymas '{job_title}': nukopijuota {res.get('copied', 0)}, nerasta {len(missing)}: {names}",
                position=InfoBarPosition.TOP_RIGHT,
                duration=-1,
                parent=self
            )
            return

        if is_direct_hotfolder:
            msg = f"Užsakymas '{job_title}' nukopijuotas tiesiai į HotFolderį ({res.get('copied', 0)} failų)."
        else:
            msg = f"Užsakymas '{job_title}' nukopijuotas į laikiną aplanką ({res.get('copied', 0)} failų)."
        InfoBar.success(
            title="Išsiųsta",
            content=msg,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
            parent=self
        )

    def open_selected_folder(self):
        if not self.selected_item:
            return
        dest_dir = self.selected_item.get("dest_dir", "").strip()
        output_mode = self.selected_item.get("output_mode", "temp_folder")

        if output_mode == "direct_hotfolder" and dest_dir and os.path.exists(dest_dir):
            os.startfile(dest_dir)
            return

        folders = self.selected_item.get("folders", [])
        opened = False
        for f in folders:
            if os.path.exists(f):
                os.startfile(f)
                opened = True
        if not opened:
            if os.path.exists(DESKTOP_DIR):
                os.startfile(DESKTOP_DIR)

    def delete_selected_entry(self):
        if not self.selected_item:
            return
        if not confirm(self, "Ištrinti įrašą?",
                       f"Įrašas „{self.selected_item.get('job_name', '')}“ bus pašalintas iš istorijos. "
                       "Spaudos failai neliečiami."):
            return
        target_id = self.selected_item.get("id")
        self.history_items = [it for it in self.history_items if it.get("id") != target_id]
        save_history_data(self.history_items)
        self.filter_history(self.search_edit.text().strip())

    def clear_all_history(self):
        if not self.history_items:
            return
        if not confirm(self, "Išvalyti visą istoriją?",
                       f"Bus ištrinti visi {len(self.history_items)} įrašai. Šio veiksmo atšaukti negalima.",
                       "Išvalyti"):
            return
        self.history_items = []
        save_history_data([])
        self.filter_history("")
        InfoBar.info(
            title="Istorija išvalyta",
            content="Visi istoriniai generavimo įrašai sėkmingai išvalyti.",
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self
        )


# ----------------- ADVANCED SETTINGS INTERFACE -----------------
class ModelsSettingsInterface(QWidget):
    settings_updated = Signal()
    theme_changed = Signal(str)

    def __init__(self, updater=None, parent=None):
        super().__init__(parent)
        self.updater = updater
        self.models_list = []
        self.jigs_list = []
        self.current_model_idx = -1
        self.current_jig_idx = -1
        self.load_all_data()
        self.init_ui()

    def load_all_data(self):
        self.models_list = load_models_data()
        self.jigs_list = load_jigs_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        top_box = QHBoxLayout()
        top_box.setSpacing(12)
        top_box.addWidget(TitleLabel("Nustatymai", self))
        top_box.addStretch(1)

        self.theme_segment = SegmentedWidget(self)
        self.theme_segment.addItem("light", "Šviesi", lambda: self.on_theme_selected("LIGHT"))
        self.theme_segment.addItem("dark", "Tamsi", lambda: self.on_theme_selected("DARK"))
        cfg = load_app_config()
        curr_th = cfg.get("theme", "LIGHT").lower()
        self.theme_segment.setCurrentItem(curr_th if curr_th in ("light", "dark") else "light")
        top_box.addWidget(self.theme_segment)

        self.btn_save_all = PrimaryPushButton(FIF.SAVE, "Išsaugoti", self)
        self.btn_save_all.clicked.connect(self.save_all_data)
        top_box.addWidget(self.btn_save_all)
        main_layout.addLayout(top_box)

        self.segmented_nav = SegmentedWidget(self)
        self.stack = QStackedWidget(self)

        self.models_tab = QWidget()
        self.init_models_tab(self.models_tab)
        self.stack.addWidget(self.models_tab)

        self.jigs_tab = QWidget()
        self.init_jigs_tab(self.jigs_tab)
        self.stack.addWidget(self.jigs_tab)

        self.updates_tab = QWidget()
        self.init_updates_tab(self.updates_tab)
        self.stack.addWidget(self.updates_tab)

        self.search_tab = QWidget()
        self.init_search_tab(self.search_tab)
        self.stack.addWidget(self.search_tab)

        self.segmented_nav.addItem("modelsTab", "Modeliai", lambda: self.stack.setCurrentIndex(0))
        self.segmented_nav.addItem("jigsTab", "Rėmai", lambda: self.stack.setCurrentIndex(1))
        self.segmented_nav.addItem("searchTab", "Paieškos aplankai", lambda: self.stack.setCurrentIndex(3))
        self.segmented_nav.addItem("updatesTab", "Atnaujinimai", lambda: self.stack.setCurrentIndex(2))
        self.segmented_nav.setCurrentItem("modelsTab")

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.segmented_nav)
        nav_row.addStretch(1)
        main_layout.addLayout(nav_row)
        main_layout.addWidget(self.stack, 1)

    def show_tab(self, index):
        keys = ["modelsTab", "jigsTab", "updatesTab", "searchTab"]
        if 0 <= index < len(keys):
            self.segmented_nav.setCurrentItem(keys[index])
            self.stack.setCurrentIndex(index)

    @staticmethod
    def _field(parent, label_text, widget, hint=None):
        box = QVBoxLayout()
        box.setSpacing(6)
        box.addWidget(FieldLabel(label_text, parent))
        if isinstance(widget, QWidget):
            box.addWidget(widget)
        else:
            box.addLayout(widget)
        if hint:
            h = CaptionLabel(hint, parent)
            h.setWordWrap(True)
            box.addWidget(h)
        return box

    def _list_card(self, parent_widget, title):
        card = CardWidget(parent_widget)
        card.setFixedWidth(300)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(12)
        head = SectionLabel(title, parent_widget)
        head.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(head)
        return card, lay

    def on_theme_selected(self, theme_mode):
        cfg = load_app_config()
        cfg["theme"] = theme_mode
        save_app_config(cfg)
        self.theme_changed.emit(theme_mode)

    def init_models_tab(self, parent_widget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        left_card, left_layout = self._list_card(parent_widget, "Modeliai")

        self.search_model_edit = SearchLineEdit(parent_widget)
        self.search_model_edit.setPlaceholderText("Ieškoti modelio")
        self.search_model_edit.textChanged.connect(self.filter_models_table)
        left_layout.addWidget(self.search_model_edit)

        self.models_table = TableWidget(parent_widget)
        self.models_table.setColumnCount(1)
        self.models_table.setHorizontalHeaderLabels(["Pavadinimas"])
        self.models_table.horizontalHeader().setStretchLastSection(True)
        self.models_table.horizontalHeader().hide()
        self.models_table.cellClicked.connect(self.on_model_selected)
        left_layout.addWidget(self.models_table, 1)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        self.btn_add_model = PushButton(FIF.ADD, "Naujas", parent_widget)
        self.btn_add_model.clicked.connect(self.add_model)
        btn_box.addWidget(self.btn_add_model, 1)

        self.btn_del_model = DangerPushButton(FIF.DELETE, "Ištrinti", parent_widget)
        self.btn_del_model.clicked.connect(self.delete_model)
        btn_box.addWidget(self.btn_del_model, 1)
        left_layout.addLayout(btn_box)

        layout.addWidget(left_card)

        self.model_detail_card = CardWidget(parent_widget)
        detail_layout = QVBoxLayout(self.model_detail_card)
        detail_layout.setContentsMargins(24, 20, 24, 20)
        detail_layout.setSpacing(20)

        self.model_detail_title = SubtitleLabel("Pasirinkite modelį", parent_widget)
        detail_layout.addWidget(self.model_detail_title)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(16)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)

        self.edit_m_name = LineEdit(parent_widget)
        self.edit_m_name.textChanged.connect(self.on_model_edited)
        form.addLayout(self._field(parent_widget, "Modelio pavadinimas", self.edit_m_name), 0, 0, 1, 2)

        self.combo_m_jig = ComboBox(parent_widget)
        self.combo_m_jig.currentIndexChanged.connect(self.on_model_edited)
        form.addLayout(self._field(parent_widget, "Rėmas", self.combo_m_jig), 1, 0)

        self.combo_m_output_mode = ComboBox(parent_widget)
        self.combo_m_output_mode.addItem("Laikinas aplankas", userData="temp_folder")
        self.combo_m_output_mode.addItem("Tiesiogiai į ColorGATE HotFolderį", userData="direct_hotfolder")
        self.combo_m_output_mode.currentIndexChanged.connect(self.on_model_edited)
        form.addLayout(self._field(parent_widget, "Išvestis", self.combo_m_output_mode), 1, 1)

        self.chips_m_types = ChipGroup(parent_widget)
        for key, text in (("tif", "TIF"), ("png", "PNG"), ("jpg", "JPG"), ("webp", "WEBP")):
            self.chips_m_types.addChip(key, text)
        self.chips_m_types.changed.connect(self.on_model_edited)
        form.addLayout(self._field(parent_widget, "Ieškomi failų tipai", self.chips_m_types,
                                   "Ieškoma tik pažymėtų tipų failų. Jei pažymėti visi arba nė vienas – ieškoma visų."),
                       5, 0, 1, 2)

        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self.edit_m_source = LineEdit(parent_widget)
        self.edit_m_source.setPlaceholderText(r"pvz. \\192.168.1.143\podbase-hotfolder\MacBook")
        self.edit_m_source.textChanged.connect(self.on_model_edited)
        src_row.addWidget(self.edit_m_source, 1)
        self.btn_browse_source = PushButton(FIF.FOLDER, "Naršyti…", parent_widget)
        self.btn_browse_source.clicked.connect(self.browse_source)
        src_row.addWidget(self.btn_browse_source)
        form.addLayout(self._field(parent_widget, "Spaudos failų aplankas", src_row), 2, 0, 1, 2)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        self.edit_m_dest = LineEdit(parent_widget)
        self.edit_m_dest.setPlaceholderText(r"pvz. C:/ProgramData/ColorGATE Software/Productionserver25/HotDir/IPAD")
        self.edit_m_dest.textChanged.connect(self.on_model_edited)
        dst_row.addWidget(self.edit_m_dest, 1)
        self.btn_browse_dest = PushButton(FIF.FOLDER, "Naršyti…", parent_widget)
        self.btn_browse_dest.clicked.connect(self.browse_dest)
        dst_row.addWidget(self.btn_browse_dest)
        form.addLayout(self._field(parent_widget, "Paskirtis (HotFolderis arba aplankas)", dst_row), 3, 0, 1, 2)

        self.edit_m_aliases = LineEdit(parent_widget)
        self.edit_m_aliases.setPlaceholderText("pvz. MacBook Air 13, A1932, A2179")
        self.edit_m_aliases.textChanged.connect(self.on_model_edited)
        form.addLayout(self._field(parent_widget, "Kiti pavadinimai", self.edit_m_aliases,
                                   "Atskirkite kableliais. Pagal juos atpažįstamas modelis iš naršyklės plėtinio."),
                       4, 0, 1, 2)

        detail_layout.addLayout(form)
        detail_layout.addStretch(1)

        layout.addWidget(self.model_detail_card, 1)

        self.update_jig_combos()
        self.populate_models_table()
        if self.models_list:
            self.select_model_row(0)

    def init_jigs_tab(self, parent_widget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        left_card, left_layout = self._list_card(parent_widget, "Rėmai")
        self.jigs_table = TableWidget(parent_widget)
        self.jigs_table.setColumnCount(1)
        self.jigs_table.setHorizontalHeaderLabels(["Pavadinimas"])
        self.jigs_table.horizontalHeader().setStretchLastSection(True)
        self.jigs_table.horizontalHeader().hide()
        self.jigs_table.cellClicked.connect(self.on_jig_selected)
        left_layout.addWidget(self.jigs_table, 1)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        self.btn_add_jig = PushButton(FIF.ADD, "Naujas", parent_widget)
        self.btn_add_jig.clicked.connect(self.add_jig)
        btn_box.addWidget(self.btn_add_jig, 1)

        self.btn_del_jig = DangerPushButton(FIF.DELETE, "Ištrinti", parent_widget)
        self.btn_del_jig.clicked.connect(self.delete_jig)
        btn_box.addWidget(self.btn_del_jig, 1)
        left_layout.addLayout(btn_box)

        layout.addWidget(left_card)

        self.jig_detail_card = CardWidget(parent_widget)
        detail_layout = QVBoxLayout(self.jig_detail_card)
        detail_layout.setContentsMargins(24, 20, 24, 20)
        detail_layout.setSpacing(20)

        self.jig_detail_title = SubtitleLabel("Rėmo nustatymai", parent_widget)
        detail_layout.addWidget(self.jig_detail_title)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(16)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)

        self.edit_j_name = LineEdit(parent_widget)
        self.edit_j_name.setPlaceholderText("pvz. Rėmas 2x5 (iPad)")
        self.edit_j_name.textChanged.connect(self.on_jig_edited)
        form.addLayout(self._field(parent_widget, "Rėmo pavadinimas", self.edit_j_name), 0, 0, 1, 2)

        self.spin_j_rows = SpinBox(parent_widget)
        self.spin_j_rows.setRange(1, 20)
        self.spin_j_rows.setValue(2)
        self.spin_j_rows.valueChanged.connect(self.on_jig_edited)
        form.addLayout(self._field(parent_widget, "Eilutės", self.spin_j_rows), 1, 0)

        self.spin_j_cols = SpinBox(parent_widget)
        self.spin_j_cols.setRange(1, 30)
        self.spin_j_cols.setValue(5)
        self.spin_j_cols.valueChanged.connect(self.on_jig_edited)
        form.addLayout(self._field(parent_widget, "Stulpeliai", self.spin_j_cols), 1, 1)

        total_row = QHBoxLayout()
        self.lbl_j_total = StatusBadge("10 lizdų", "neutral", parent_widget, dot=False)
        total_row.addWidget(self.lbl_j_total)
        total_row.addStretch(1)
        form.addLayout(self._field(parent_widget, "Lizdų iš viso", total_row), 2, 0, 1, 2)

        self.edit_j_desc = LineEdit(parent_widget)
        self.edit_j_desc.setPlaceholderText("pvz. Skirtas iPad / MacBook")
        self.edit_j_desc.textChanged.connect(self.on_jig_edited)
        form.addLayout(self._field(parent_widget, "Pastaba", self.edit_j_desc), 3, 0, 1, 2)

        detail_layout.addLayout(form)
        detail_layout.addStretch(1)

        layout.addWidget(self.jig_detail_card, 1)

        self.populate_jigs_table()
        if self.jigs_list:
            self.select_jig_row(0)

    def init_updates_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        ver_card = CardWidget(parent_widget)
        v_layout = QHBoxLayout(ver_card)
        v_layout.setContentsMargins(20, 20, 20, 20)
        v_layout.setSpacing(16)

        lbl_app_logo = QLabel(ver_card)
        if os.path.exists(ICON_FILE):
            lbl_app_logo.setPixmap(QPixmap(ICON_FILE).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        v_layout.addWidget(lbl_app_logo)

        v_info_box = QVBoxLayout()
        v_info_box.setSpacing(2)
        v_info_box.addWidget(SubtitleLabel("Podbase Container Studio", ver_card))
        v_ver_lbl = SecondaryLabel(f"Įdiegta versija v{CURRENT_VERSION}", ver_card)
        tabular(v_ver_lbl)
        v_info_box.addWidget(v_ver_lbl)
        v_layout.addLayout(v_info_box)

        v_layout.addStretch(1)

        self.btn_open_log = PushButton(FIF.DOCUMENT, "Atidaryti žurnalą", ver_card)
        self.btn_open_log.setToolTip(f"Programos klaidų žurnalas: {LOG_FILE}")
        self.btn_open_log.clicked.connect(self.open_log_file)
        v_layout.addWidget(self.btn_open_log)

        self.btn_check_updates = PrimaryPushButton(FIF.SYNC, "Tikrinti atnaujinimus", ver_card)
        self.btn_check_updates.clicked.connect(self.on_manual_check_updates)
        v_layout.addWidget(self.btn_check_updates)

        layout.addWidget(ver_card)

        repo_card = CardWidget(parent_widget)
        r_layout = QVBoxLayout(repo_card)
        r_layout.setContentsMargins(20, 20, 20, 20)
        r_layout.setSpacing(16)

        r_layout.addWidget(SubtitleLabel("Automatiniai atnaujinimai", repo_card))

        cfg = load_app_config()
        self.edit_github_repo = LineEdit(repo_card)
        self.edit_github_repo.setText(cfg.get("github_repo", DEFAULT_GITHUB_REPO))
        self.edit_github_repo.setPlaceholderText("pvz. lkuprys/CC")
        self.edit_github_repo.setMaximumWidth(420)
        r_layout.addLayout(self._field(repo_card, "GitHub repozitorija", self.edit_github_repo))

        self.chk_auto_updates = CheckBox("Tikrinti paleidus programą ir kas 30 min.", repo_card)
        self.chk_auto_updates.setChecked(cfg.get("auto_check_updates", True))
        r_layout.addWidget(self.chk_auto_updates)

        layout.addWidget(repo_card)
        layout.addStretch(1)

    def init_search_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = CardWidget(parent_widget)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(16)

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(SubtitleLabel("Brokų aplankas", card))
        hint = SecondaryLabel(
            "Papildomas aplankas, kuriame visiems modeliams ieškoma spaudos failų pagal PID, įskaitant poaplankius. "
            "Jei tas pats PID randamas keliuose aplankuose, imamas naujausias failas.", card)
        hint.setWordWrap(True)
        head.addWidget(hint)
        c_layout.addLayout(head)

        cfg = load_app_config()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit_reject_folder = LineEdit(card)
        self.edit_reject_folder.setText(cfg.get("reject_folder", ""))
        self.edit_reject_folder.setPlaceholderText(r"pvz. \\192.168.1.143\podbase-hotfolder\REJECTED")
        self.edit_reject_folder.setClearButtonEnabled(True)
        row.addWidget(self.edit_reject_folder, 1)

        btn_browse = PushButton(FIF.FOLDER, "Pasirinkti…", card)
        btn_browse.clicked.connect(self.browse_reject_folder)
        row.addWidget(btn_browse)
        c_layout.addLayout(self._field(card, "Aplanko kelias", row))

        status_row = QHBoxLayout()
        self.lbl_reject_status = StatusBadge("", "neutral", card)
        status_row.addWidget(self.lbl_reject_status)
        status_row.addStretch(1)
        c_layout.addLayout(status_row)

        # Tinklo kelio tikrinimas gali užtrukti, todėl tikriname tik nustojus rašyti
        self._reject_check_timer = QTimer(self)
        self._reject_check_timer.setSingleShot(True)
        self._reject_check_timer.setInterval(600)
        self._reject_check_timer.timeout.connect(self.update_reject_status)
        self.edit_reject_folder.textChanged.connect(self._reject_check_timer.start)
        self.update_reject_status()

        layout.addWidget(card)

        layout.addWidget(Notice(
            "info", "Visada ieškoma ir šiuose aplankuose",
            f"Modelio spaudos failų aplanke ir bendrame tinklo aplanke {NETWORK_HOTFOLDER_DEFAULT}. "
            "Pakeitę kelią, paspauskite „Išsaugoti“.", parent_widget))
        layout.addStretch(1)

    def browse_reject_folder(self):
        curr = self.edit_reject_folder.text().strip() or NETWORK_HOTFOLDER_DEFAULT
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite brokų (rejected) aplanką", curr)
        if folder:
            self.edit_reject_folder.setText(os.path.normpath(folder))

    def update_reject_status(self):
        path = self.edit_reject_folder.text().strip()
        if not path:
            self.lbl_reject_status.set_status("neutral", "Nenustatytas")
        elif os.path.exists(path):
            self.lbl_reject_status.set_status("success", "Pasiekiamas")
        else:
            self.lbl_reject_status.set_status("error", "Nerastas arba nepasiekiamas")

    def open_log_file(self):
        if not os.path.exists(LOG_FILE):
            InfoBar.info(
                title="Žurnalo dar nėra",
                content=f"Failas {LOG_FILE} nesukurtas (įrašų dar nebuvo arba programos aplankas neleidžia rašyti).",
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self.window()
            )
            return
        try:
            os.startfile(LOG_FILE)
        except Exception as e:
            log.warning(f"Nepavyko atidaryti žurnalo: {e}")

    def on_manual_check_updates(self):
        if self.updater:
            repo_slug = self.edit_github_repo.text().strip() or DEFAULT_GITHUB_REPO
            self.updater.check_for_updates(repo_slug=repo_slug, manual=True)

    def update_jig_combos(self):
        self.combo_m_jig.blockSignals(True)
        self.combo_m_jig.clear()
        for j in self.jigs_list:
            self.combo_m_jig.addItem(j.get("name", "Rėmas"), userData=j.get("id"))
        self.combo_m_jig.blockSignals(False)

    def populate_models_table(self, filter_text=""):
        self.models_table.setRowCount(0)
        row_idx = 0
        for real_idx, m in enumerate(self.models_list):
            name = m.get("name", "")
            if not filter_text or filter_text.lower() in name.lower():
                self.models_table.insertRow(row_idx)
                item = QTableWidgetItem(name)
                item.setData(Qt.UserRole, real_idx)
                self.models_table.setItem(row_idx, 0, item)
                row_idx += 1

    def populate_jigs_table(self):
        self.jigs_table.setRowCount(len(self.jigs_list))
        for row, j in enumerate(self.jigs_list):
            self.jigs_table.setItem(row, 0, QTableWidgetItem(j.get("name", "Rėmas")))

    def filter_models_table(self, text):
        self.populate_models_table(filter_text=text)

    def on_model_selected(self, row, col):
        item = self.models_table.item(row, 0)
        if item:
            real_idx = item.data(Qt.UserRole)
            self.select_model_row(real_idx)

    def select_model_row(self, real_idx):
        if 0 <= real_idx < len(self.models_list):
            self.current_model_idx = real_idx
            m = self.models_list[real_idx]
            self.model_detail_title.setText(m.get('name', '') or "Modelis")

            self.edit_m_name.blockSignals(True)
            self.edit_m_source.blockSignals(True)
            self.edit_m_dest.blockSignals(True)
            self.edit_m_aliases.blockSignals(True)
            self.combo_m_jig.blockSignals(True)
            self.combo_m_output_mode.blockSignals(True)

            self.edit_m_name.setText(m.get("name", ""))
            self.edit_m_source.setText(m.get("source", ""))
            self.edit_m_dest.setText(m.get("destination", ""))
            self.edit_m_aliases.setText(", ".join(m.get("aliases", [])))
            self.chips_m_types.setCheckedKeys(m.get("file_types") or list(FILE_TYPE_GROUPS))

            out_mode = m.get("output_mode", "temp_folder")
            idx_mode = self.combo_m_output_mode.findData(out_mode)
            if idx_mode != -1:
                self.combo_m_output_mode.setCurrentIndex(idx_mode)
            else:
                self.combo_m_output_mode.setCurrentIndex(0)

            j_id = m.get("jig_id", "")
            idx = self.combo_m_jig.findData(j_id)
            if idx != -1:
                self.combo_m_jig.setCurrentIndex(idx)
            else:
                for j_idx, j in enumerate(self.jigs_list):
                    if j.get("id") == j_id:
                        self.combo_m_jig.setCurrentIndex(j_idx)
                        break
                else:
                    self.combo_m_jig.setCurrentIndex(0)

            self.edit_m_name.blockSignals(False)
            self.edit_m_source.blockSignals(False)
            self.edit_m_dest.blockSignals(False)
            self.edit_m_aliases.blockSignals(False)
            self.combo_m_jig.blockSignals(False)
            self.combo_m_output_mode.blockSignals(False)

    def on_model_edited(self):
        if 0 <= self.current_model_idx < len(self.models_list):
            m = self.models_list[self.current_model_idx]
            m["name"] = self.edit_m_name.text().strip()
            m["source"] = self.edit_m_source.text().strip()
            m["destination"] = self.edit_m_dest.text().strip()
            m["output_mode"] = self.combo_m_output_mode.currentData() or "temp_folder"
            
            curr_jig_id = self.combo_m_jig.currentData()
            if not curr_jig_id and 0 <= self.combo_m_jig.currentIndex() < len(self.jigs_list):
                curr_jig_id = self.jigs_list[self.combo_m_jig.currentIndex()].get("id")
            if curr_jig_id:
                m["jig_id"] = curr_jig_id

            aliases_raw = self.edit_m_aliases.text().split(",")
            m["aliases"] = [a.strip() for a in aliases_raw if a.strip()]
            types = self.chips_m_types.checkedKeys()
            # Visi arba nė vienas pažymėtas = ieškoma visų tipų
            m["file_types"] = [] if len(types) in (0, len(FILE_TYPE_GROUPS)) else types
            self.model_detail_title.setText(m['name'] or "Modelis")

    def on_jig_selected(self, row, col):
        self.select_jig_row(row)

    def select_jig_row(self, row):
        if 0 <= row < len(self.jigs_list):
            self.current_jig_idx = row
            j = self.jigs_list[row]
            self.jig_detail_title.setText(j.get('name', '') or "Rėmas")

            self.edit_j_name.blockSignals(True)
            self.spin_j_rows.blockSignals(True)
            self.spin_j_cols.blockSignals(True)
            self.edit_j_desc.blockSignals(True)

            self.edit_j_name.setText(j.get("name", ""))
            rows = j.get("rows", 2)
            cols = j.get("cols", 5)
            self.spin_j_rows.setValue(rows)
            self.spin_j_cols.setValue(cols)
            self.lbl_j_total.setText(f"{rows * cols} lizdų · {rows} × {cols}")
            self.edit_j_desc.setText(j.get("description", ""))

            self.edit_j_name.blockSignals(False)
            self.spin_j_rows.blockSignals(False)
            self.spin_j_cols.blockSignals(False)
            self.edit_j_desc.blockSignals(False)

    def on_jig_edited(self):
        if 0 <= self.current_jig_idx < len(self.jigs_list):
            j = self.jigs_list[self.current_jig_idx]
            j["name"] = self.edit_j_name.text().strip()
            rows = self.spin_j_rows.value()
            cols = self.spin_j_cols.value()
            j["rows"] = rows
            j["cols"] = cols
            j["total_slots"] = rows * cols
            j["description"] = self.edit_j_desc.text().strip()

            self.lbl_j_total.setText(f"{rows * cols} lizdų · {rows} × {cols}")
            self.jig_detail_title.setText(j['name'] or "Rėmas")

    def browse_source(self):
        curr = self.edit_m_source.text().strip() or "C:/"
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite spaudos failų šaltinio aplanką", curr)
        if folder:
            self.edit_m_source.setText(folder.replace("\\", "/"))
            self.on_model_edited()

    def browse_dest(self):
        curr = self.edit_m_dest.text().strip() or "C:/ProgramData/ColorGATE Software"
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite paskirties aplanką arba ColorGATE HotFolderį", curr)
        if folder:
            self.edit_m_dest.setText(folder.replace("\\", "/"))
            self.on_model_edited()

    def add_model(self):
        new_m = {
            "name": f"Naujas modelis {len(self.models_list) + 1}",
            "jig_id": self.jigs_list[0].get("id") if self.jigs_list else "jig_2x5",
            "source": r"\\192.168.1.143\podbase-hotfolder\BENDRAS_PODBASE_HOTFOLDER",
            "destination": "",
            "output_mode": "temp_folder",
            "aliases": []
        }
        self.models_list.append(new_m)
        self.populate_models_table()
        self.select_model_row(len(self.models_list) - 1)

    def delete_model(self):
        if 0 <= self.current_model_idx < len(self.models_list):
            name = self.models_list[self.current_model_idx].get("name", "")
            if not confirm(self, "Ištrinti modelį?",
                           f"Modelis „{name}“ bus pašalintas. Pakeitimas įsigalios paspaudus „Išsaugoti“."):
                return
            del self.models_list[self.current_model_idx]
            self.populate_models_table()
            if self.models_list:
                self.select_model_row(min(self.current_model_idx, len(self.models_list) - 1))

    def add_jig(self):
        new_id = f"jig_{int(time.time())}"
        new_j = {
            "id": new_id,
            "name": f"Naujas rėmas {len(self.jigs_list) + 1}",
            "rows": 2,
            "cols": 5,
            "total_slots": 10,
            "description": ""
        }
        self.jigs_list.append(new_j)
        self.populate_jigs_table()
        self.update_jig_combos()
        self.select_jig_row(len(self.jigs_list) - 1)

    def delete_jig(self):
        if 0 <= self.current_jig_idx < len(self.jigs_list):
            name = self.jigs_list[self.current_jig_idx].get("name", "")
            if not confirm(self, "Ištrinti rėmą?",
                           f"Rėmas „{name}“ bus pašalintas. Modeliai, kurie jį naudoja, gaus pirmąjį sąrašo rėmą. "
                           "Pakeitimas įsigalios paspaudus „Išsaugoti“."):
                return
            del self.jigs_list[self.current_jig_idx]
            self.populate_jigs_table()
            self.update_jig_combos()
            if self.jigs_list:
                self.select_jig_row(min(self.current_jig_idx, len(self.jigs_list) - 1))

    def save_all_data(self):
        try:
            if 0 <= self.current_model_idx < len(self.models_list):
                self.on_model_edited()
            if 0 <= self.current_jig_idx < len(self.jigs_list):
                self.on_jig_edited()

            save_models_data(self.models_list)
            save_jigs_data(self.jigs_list)

            cfg = load_app_config()
            cfg["github_repo"] = self.edit_github_repo.text().strip() or DEFAULT_GITHUB_REPO
            cfg["auto_check_updates"] = self.chk_auto_updates.isChecked()
            cfg["reject_folder"] = self.edit_reject_folder.text().strip()
            save_app_config(cfg)

            saved_model_idx = self.current_model_idx
            saved_jig_idx = self.current_jig_idx

            self.update_jig_combos()
            self.populate_models_table()
            self.populate_jigs_table()

            if 0 <= saved_model_idx < len(self.models_list):
                self.select_model_row(saved_model_idx)
            if 0 <= saved_jig_idx < len(self.jigs_list):
                self.select_jig_row(saved_jig_idx)

            self.settings_updated.emit()

            InfoBar.success(
                title="Nustatymai išsaugoti",
                content="Pakeitimai pritaikyti.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title="Klaida išsaugant",
                content=str(e),
                position=InfoBarPosition.TOP_RIGHT,
                parent=self
            )


# ----------------- MAIN FLUENT WINDOW -----------------
class TopBar(QFrame):
    """Balta viršutinė juosta: logotipas ir pavadinimas kairėje, būsena ir piktogramų mygtukai dešinėje."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 16, 0)
        lay.setSpacing(10)

        logo = QLabel(self)
        if os.path.exists(ICON_FILE):
            logo.setPixmap(QPixmap(ICON_FILE).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(logo)
        name = QLabel("Podbase Container Studio", self)
        name.setProperty("role", "appname")
        lay.addWidget(name)
        lay.addStretch(1)

        self.status_badge = StatusBadge("Plėtinio ryšys veikia", "success", self)
        self.status_badge.setToolTip("Naršyklės plėtinys siunčia užsakymus į 127.0.0.1:5000")
        lay.addWidget(self.status_badge)

        self.lbl_version = CaptionLabel(f"v{CURRENT_VERSION}", self)
        tabular(self.lbl_version)
        lay.addSpacing(4)
        lay.addWidget(self.lbl_version)
        lay.addSpacing(4)

        self.btn_log = TransparentToolButton(FIF.DOCUMENT, self)
        self.btn_log.setToolTip("Atidaryti žurnalą")
        lay.addWidget(self.btn_log)

        self.btn_updates = TransparentToolButton(FIF.SYNC, self)
        self.btn_updates.setToolTip("Tikrinti atnaujinimus")
        lay.addWidget(self.btn_updates)

        self.btn_theme = TransparentToolButton(FIF.CONSTRACT, self)
        self.btn_theme.setToolTip("Šviesi / tamsi tema")
        lay.addWidget(self.btn_theme)

        self._apply_style()
        theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        t = tokens()
        self.setStyleSheet(
            f"QFrame#topBar {{ background: {t['card']}; border: none; border-bottom: 1px solid {t['divider']}; }}")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("appRoot")
        self.setWindowTitle(f"Podbase Container Studio (v{CURRENT_VERSION})")
        if os.path.exists(ICON_FILE):
            app_icon = QIcon(ICON_FILE)
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)

        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)
        # Paleidus nė vienas laukas neturi fokuso (kitaip pirmasis laukas rodomas su juodu rėmeliu)
        self.setFocusPolicy(Qt.ClickFocus)

        cfg = load_app_config()
        setTheme(Theme.DARK if cfg.get("theme", "LIGHT") == "DARK" else Theme.LIGHT)

        self.updater = AppUpdater(self, current_version=CURRENT_VERSION)

        self.studio_interface = ContainerStudioInterface(self)
        self.studio_interface.setObjectName("studioInterface")

        self.history_interface = HistoryInterface(self)
        self.history_interface.setObjectName("historyInterface")
        self.history_interface.load_order_to_studio.connect(self.on_load_order_to_studio)
        self.studio_interface.container_generated.connect(self.history_interface.reload_history)

        self.settings_interface = ModelsSettingsInterface(updater=self.updater, parent=self)
        self.settings_interface.setObjectName("settingsInterface")
        self.settings_interface.settings_updated.connect(self.on_settings_updated)
        self.settings_interface.theme_changed.connect(self.on_theme_changed)

        self.init_navigation()

        self.server_thread = FlaskServerThread(port=5000, host=(load_app_config().get("api_host") or "127.0.0.1"))
        self.server_thread.designs_received.connect(self.on_designs_received)
        self.server_thread.server_failed.connect(self.on_server_failed)
        self.server_thread.start()

        # Laikinų aplankų valymas (tikrinama kas 30 s)
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setInterval(30000)
        self.cleanup_timer.timeout.connect(self.run_auto_cleanup)
        self.cleanup_timer.start()
        self.run_auto_cleanup()

        # Parodome, kaip baigėsi paskutinis atnaujinimas (jei programa ką tik persikrovė po jo)
        QTimer.singleShot(1500, self.updater.show_last_update_result)

        # Atnaujinimų tikrinimas: po 3.5 s nuo paleidimo ir toliau periodiškai
        QTimer.singleShot(3500, self.run_periodic_update_check)
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(PERIODIC_CHECK_INTERVAL_MS)
        self.update_check_timer.timeout.connect(self.run_periodic_update_check)
        self.update_check_timer.start()

    def run_periodic_update_check(self):
        cfg = load_app_config()
        if cfg.get("auto_check_updates", True):
            repo_slug = cfg.get("github_repo", DEFAULT_GITHUB_REPO)
            self.updater.check_for_updates(repo_slug=repo_slug, manual=False)

    def run_auto_cleanup(self):
        try:
            perform_temp_folders_cleanup()
        except Exception as e:
            log.warning(f"[run_auto_cleanup error]: {e}")

    def init_navigation(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = TopBar(self)
        self.top_bar.btn_log.clicked.connect(self.settings_interface.open_log_file)
        self.top_bar.btn_updates.clicked.connect(self.settings_interface.on_manual_check_updates)
        self.top_bar.btn_theme.clicked.connect(self.toggle_theme)
        root.addWidget(self.top_bar)

        self.tabs_bar = QFrame(self)
        self.tabs_bar.setObjectName("tabsBar")
        tabs_l = QHBoxLayout(self.tabs_bar)
        tabs_l.setContentsMargins(24, 0, 24, 0)
        self.tabs = UnderlineTabs(self.tabs_bar)
        tabs_l.addWidget(self.tabs)
        root.addWidget(self.tabs_bar)

        self.pages = QStackedWidget(self)
        self.pages.setObjectName("pages")
        root.addWidget(self.pages, 1)

        self._page_widgets = []
        for title, page in (("Konteineriai", self.studio_interface),
                            ("Istorija", self.history_interface),
                            ("Nustatymai", self.settings_interface)):
            self.tabs.addTab(title)
            self.pages.addWidget(page)
            self._page_widgets.append(page)
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)

        self._apply_chrome_style()
        theme_signals.changed.connect(self._apply_chrome_style)

    def _apply_chrome_style(self):
        t = tokens()
        self.tabs_bar.setStyleSheet(
            f"QFrame#tabsBar {{ background: {t['card']}; border: none; border-bottom: 1px solid {t['border']}; }}")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.setFocus)

    def switchTo(self, widget):
        if widget in self._page_widgets:
            idx = self._page_widgets.index(widget)
            self.pages.setCurrentIndex(idx)
            self.tabs.setCurrentIndex(idx)

    def toggle_theme(self):
        mode = "LIGHT" if isDarkTheme() else "DARK"
        self.settings_interface.on_theme_selected(mode)
        self.settings_interface.theme_segment.setCurrentItem(mode.lower())

    def on_load_order_to_studio(self, entry):
        self.studio_interface.load_from_history_entry(entry)
        self.switchTo(self.studio_interface)

    def on_theme_changed(self, theme_mode):
        setTheme(Theme.DARK if theme_mode == "DARK" else Theme.LIGHT)
        self.studio_interface.update_bed_container_style()

    def on_settings_updated(self):
        self.studio_interface.load_data()
        self.studio_interface.populate_models_combo()
        self.studio_interface.on_model_changed()

    def on_server_failed(self, err):
        self.top_bar.status_badge.set_status("error", "Plėtinio ryšys neveikia")
        InfoBar.error(
            title="Naršyklės plėtinio ryšys neveikia",
            content=f"Nepavyko paleisti serverio 5000 prievade ({err}). "
                    "Galbūt programa jau atidaryta kitame lange.",
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self
        )

    def on_designs_received(self, payload):
        self.studio_interface.set_data_from_extension(payload)
        self.switchTo(self.studio_interface)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        running = [w for w in (getattr(self.studio_interface, "_job_worker", None),
                               getattr(self.history_interface, "_job_worker", None))
                   if w is not None and w.isRunning()]
        if running:
            InfoBar.warning(
                title="Vyksta generavimas",
                content="Palaukite, kol bus nukopijuoti failai, ir uždarykite programą iš naujo.",
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self
            )
            event.ignore()
            return
        self.server_thread.stop()
        super().closeEvent(event)


# ----------------- TIK VIENAS PROGRAMOS LANGAS -----------------
# Antras paleidimas tik iškelia jau atidarytą langą (kitaip jis liktų be plėtinio ryšio, nes 5000 prievadas užimtas).
# Raktas pagal programos aplanką (kelios skirtingose vietose įdiegtos kopijos netrukdo viena kitai);
# tik raidės ir skaičiai – tinka ir užrakto failo, ir Windows named pipe pavadinimui
SINGLE_INSTANCE_KEY = "PodbaseContainerStudio_" + hashlib.sha1(
    os.path.normcase(os.path.abspath(BASE_DIR)).encode("utf-8")).hexdigest()[:16]


def notify_running_instance(timeout_ms=1500):
    """True, jei veikianti programa atsakė ir iškėlė savo langą."""
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show")
    sock.flush()
    # Atsakymas įrodo, kad programa tikrai veikia (o ne tik dar neužsidarė)
    answered = sock.waitForReadyRead(timeout_ms) and sock.readAll().data().startswith(b"ok")
    sock.disconnectFromServer()
    return answered


def _bring_to_front(window):
    if window.isMinimized():
        window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
    window.show()
    window.raise_()
    window.activateWindow()


class SingleInstanceGuard:
    """
    Užrakto failas užtikrina, kad programa veiktų tik vieną kartą, o vietinis serveris leidžia
    antram paleidimui paprašyti iškelti jau atidarytą langą.
    """

    def __init__(self):
        self.lock = QLockFile(os.path.join(tempfile.gettempdir(), SINGLE_INSTANCE_KEY + ".lock"))
        # 0 = užraktas nelaikomas pasenusiu pagal laiką; tik jei jį laikęs procesas nebeveikia
        self.lock.setStaleLockTime(0)
        self.server = None
        self.window = None
        self._show_requested = False

    def acquire(self):
        """True – šis paleidimas yra vienintelis ir gali tęsti."""
        if self.lock.tryLock(100):
            return True
        if notify_running_instance():
            log.info("Programa jau atidaryta – iškeliamas esamas langas.")
            return False
        # Ankstesnis langas ką tik uždarytas, bet procesas dar baigiasi – palaukiame
        if self.lock.tryLock(8000):
            return True
        log.warning("Programa jau veikia, bet neatsako.")
        QMessageBox.warning(
            None, "Podbase Container Studio",
            "Programa jau paleista, bet neatsako.\n"
            "Palaukite kelias sekundes arba uždarykite ją per Užduočių tvarkytuvę ir bandykite dar kartą."
        )
        return False

    def start_server(self):
        self.server = QLocalServer()
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # likęs po netikėto išjungimo (užraktas jau mūsų)
        if not self.server.listen(SINGLE_INSTANCE_KEY):
            log.warning(f"Nepavyko paleisti vieno lango apsaugos serverio: {self.server.errorString()}")
            return
        self.server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.disconnected.connect(conn.deleteLater)
        conn.write(b"ok")
        conn.flush()
        if self.window is not None:
            _bring_to_front(self.window)
        else:
            self._show_requested = True  # langas dar kuriamas

    def attach_window(self, window):
        self.window = window
        if self._show_requested:
            _bring_to_front(window)

    def release(self):
        if self.server is not None:
            self.server.close()
        self.lock.unlock()


if __name__ == "__main__":
    install_exception_logging()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        sys.exit(0)
    instance_guard.start_server()
    # Uždarant langą iškart atlaisviname užraktą ir sustabdome fono darbus,
    # kad naujas paleidimas nelauktų, kol senas procesas galutinai baigsis
    app.aboutToQuit.connect(instance_guard.release)
    app.aboutToQuit.connect(lambda: thumbnail_loader().pool.clear())
    log.info(f"Paleidžiama Podbase Container Studio v{CURRENT_VERSION}")
    if os.path.exists(ICON_FILE):
        app.setWindowIcon(QIcon(ICON_FILE))
    cfg = load_app_config()
    apply_app_theme(app, dark=cfg.get("theme", "LIGHT") == "DARK", font_dir=get_res_path("fonts"))
    w = MainWindow()
    w.show()
    instance_guard.attach_window(w)
    sys.exit(app.exec())
