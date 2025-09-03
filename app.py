import sys, os, json, shutil, uuid, time, pathlib, math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Signal, QUrl, QObject
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QGuiApplication, QKeySequence, QPixmap, QPainterPath, QPen
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStatusBar, QLabel, QToolBar, QStyle,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsProxyWidget, QMenu, QToolButton, QWidget,
    QHBoxLayout, QPushButton, QSlider, QMessageBox, QGraphicsPathItem, QGraphicsEllipseItem
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# ------------------ Tema oscuro ------------------
try:
    import qdarkstyle
    QDARKSTYLE_OK = True
except Exception:
    QDARKSTYLE_OK = False

# ------------------ Storage ------------------
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "WhiteBoard")
AUTOSAVE_JSON = os.path.join(APP_DIR, "last.json")
ASSETS_DIR = os.path.join(APP_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

def new_id() -> str: return uuid.uuid4().hex

def copy_into_assets(src_path: str) -> str:
    try:
        if not src_path:
            return ""
        src_path = os.path.normpath(src_path)
        if not os.path.exists(src_path):
            return ""
        ext = pathlib.Path(src_path).suffix.lower()
        rel = f"{new_id()}{ext}"
        shutil.copy2(src_path, os.path.join(ASSETS_DIR, rel))
        return rel
    except Exception as e:
        print("[assets] copy error:", e)
        return ""

# ------------------ Modelo ------------------
@dataclass
class NotePayload:
    # IDEA
    title: str = ""
    subtitle: str = ""
    # TEXTO
    body: str = ""
    font_pt: int = 12
    # MEDIA
    audio_asset: str = ""
    image_asset: str = ""
    volume: int = 100
    # EMOJI
    emoji_char: str = ""
    emoji_pt: int = 32
    # ARROW
    p1: Tuple[float, float] = (20.0, 20.0)
    p2: Tuple[float, float] = (140.0, 60.0)
    stroke: int = 3

@dataclass
class Note:
    id: str
    type: str  # "idea" | "texto" | "audio" | "image" | "emoji" | "arrow"
    pos: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (260.0, 140.0)
    z: int = 0
    child_board_id: Optional[str] = None  # solo para idea
    payload: NotePayload = field(default_factory=NotePayload)

@dataclass
class Board:
    id: str
    title: str = "Pizarra"
    items_order: List[str] = field(default_factory=list)
    items: Dict[str, Note] = field(default_factory=dict)

@dataclass
class Project:
    version: int
    project_id: str
    root_board_id: str
    boards: Dict[str, Board]
    last_opened: float = field(default_factory=lambda: time.time())

def empty_project() -> Project:
    root_id = new_id()
    root = Board(id=root_id, title="Raíz")
    return Project(version=4, project_id=new_id(), root_board_id=root_id, boards={root_id: root})

def save_project(p: Project, path: str = AUTOSAVE_JSON) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    serial = {
        "version": p.version, "project_id": p.project_id, "root_board_id": p.root_board_id,
        "last_opened": time.time(), "boards": {}
    }
    for bid, b in p.boards.items():
        serial["boards"][bid] = {"id": b.id, "title": b.title, "items_order": b.items_order, "items": {}}
        for nid, n in b.items.items():
            serial["boards"][bid]["items"][nid] = {
                "id": n.id, "type": n.type, "pos": list(n.pos), "size": list(n.size), "z": n.z,
                "child_board_id": n.child_board_id if n.type == "idea" else None,
                "payload": {
                    "title": n.payload.title, "subtitle": n.payload.subtitle,
                    "body": n.payload.body, "font_pt": n.payload.font_pt,
                    "audio_asset": n.payload.audio_asset, "image_asset": n.payload.image_asset,
                    "volume": n.payload.volume,
                    "emoji_char": n.payload.emoji_char, "emoji_pt": n.payload.emoji_pt,
                    "p1": list(n.payload.p1), "p2": list(n.payload.p2), "stroke": n.payload.stroke
                }
            }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serial, f, ensure_ascii=False, indent=2)

def load_project(path: str = AUTOSAVE_JSON) -> Project:
    if not os.path.exists(path):
        return empty_project()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    boards: Dict[str, Board] = {}
    for bid, bd in data["boards"].items():
        items = {}
        for nid, nd in bd["items"].items():
            p = NotePayload(
                title=nd["payload"].get("title",""),
                subtitle=nd["payload"].get("subtitle",""),
                body=nd["payload"].get("body",""),
                font_pt=int(nd["payload"].get("font_pt",12)),
                audio_asset=nd["payload"].get("audio_asset",""),
                image_asset=nd["payload"].get("image_asset",""),
                volume=int(nd["payload"].get("volume",100)),
                emoji_char=nd["payload"].get("emoji_char",""),
                emoji_pt=int(nd["payload"].get("emoji_pt",32)),
                p1=tuple(nd["payload"].get("p1",[20,20])),
                p2=tuple(nd["payload"].get("p2",[140,60])),
                stroke=int(nd["payload"].get("stroke",3)),
            )
            items[nid] = Note(
                id=nd["id"], type=nd["type"], pos=tuple(nd["pos"]), size=tuple(nd["size"]),
                z=int(nd["z"]), child_board_id=nd.get("child_board_id") if nd["type"]=="idea" else None,
                payload=p
            )
        boards[bid] = Board(id=bd["id"], title=bd.get("title","Pizarra"),
                            items_order=bd.get("items_order", list(items.keys())), items=items)
    return Project(version=int(data.get("version",4)), project_id=data.get("project_id", new_id()),
                   root_board_id=data["root_board_id"], boards=boards,
                   last_opened=float(data.get("last_opened", time.time())))

# ------------------ Helpers ------------------
def overlap_ratio(rect_a: QRectF, rect_b: QRectF) -> float:
    inter = rect_a.intersected(rect_b)
    if inter.isEmpty(): return 0.0
    return (inter.width()*inter.height()) / (rect_a.width()*rect_a.height())

# ------------------ Graphics Items (QObject mixin for signals) ------------------
class BaseNoteItem(QObject, QGraphicsRectItem):
    # señales comunes
    request_open_child = Signal(str)      # idea -> abrir subpizarra
    request_delete = Signal(str)
    request_nest_into = Signal(str, str)  # dragged_id, target_id
    request_copy = Signal(str)
    request_cut = Signal(str)
    request_edit = Signal(str)
    request_dirty = Signal()              # para autosave inmediato

    def __init__(self, note: Note):
        QObject.__init__(self)
        QGraphicsRectItem.__init__(self)
        self.note = note
        self.setRect(QRectF(0, 0, note.size[0], note.size[1]))
        self.setPos(QPointF(note.pos[0], note.pos[1]))
        self.setZValue(note.z)
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable |
            QGraphicsRectItem.ItemIsSelectable |
            QGraphicsRectItem.ItemSendsScenePositionChanges
        )
        self.setAcceptHoverEvents(True)
        self._hovering = False

    # ---- estilo borde/hover
    def paint(self, painter, option, widget=None):
        color = QColor(90, 90, 90, 180)
        if self.isSelected(): color = QColor(70, 130, 180, 220)
        elif self._hovering:  color = QColor(130, 130, 130, 200)
        painter.setBrush(QBrush(QColor(30, 30, 30, 180)))
        painter.setPen(color)
        super().paint(painter, option, widget)

    def hoverEnterEvent(self, e): self._hovering=True; self.update(); super().hoverEnterEvent(e)
    def hoverLeaveEvent(self, e): self._hovering=False; self.update(); super().hoverLeaveEvent(e)

    # ---- actualizar posición en modelo + autosave
    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged:
            self.note.pos = (self.pos().x(), self.pos().y())
            self.request_dirty.emit()
        return super().itemChange(change, value)

    # ---- anidar (requiere soltar con solapamiento suficiente) solo sobre IDEA
    def mouseReleaseEvent(self, event):
        scene = self.scene()
        if scene:
            my_rect = self.mapToScene(self.boundingRect()).boundingRect()
            for it in scene.items(event.scenePos()):
                if isinstance(it, BaseNoteItem) and it is not self and it.note.type == "idea":
                    ratio = overlap_ratio(my_rect, it.mapToScene(it.boundingRect()).boundingRect())
                    if ratio >= 0.35:
                        self.request_nest_into.emit(self.note.id, it.note.id)
                        break
        super().mouseReleaseEvent(event)

    # ---- menú básico (para clases hijas)
    def _common_menu(self, with_open: bool):
        menu = QMenu()
        act_edit = menu.addAction("Editar")
        act_open = menu.addAction("Entrar (doble clic)") if with_open else None
        act_del = menu.addAction("Eliminar")
        menu.addSeparator()
        act_cut = menu.addAction("Cortar")
        act_copy = menu.addAction("Copiar")
        return menu, act_edit, act_open, act_del, act_cut, act_copy

# ---- IDEA (resizable estilo PowerPoint)
class IdeaNoteItem(BaseNoteItem):
    HANDLE = 12
    def __init__(self, note: Note):
        super().__init__(note)
        self.title_item = QGraphicsTextItem(note.payload.title, self)
        f1 = QFont(); f1.setPointSize(12); f1.setBold(True)
        self.title_item.setFont(f1); self.title_item.setDefaultTextColor(QColor("white"))
        self.title_item.setTextInteractionFlags(Qt.TextEditorInteraction); self.title_item.setPos(8,8)

        self.subtitle_item = QGraphicsTextItem(note.payload.subtitle, self)
        f2 = QFont(); f2.setPointSize(9)
        self.subtitle_item.setFont(f2); self.subtitle_item.setDefaultTextColor(QColor("#cccccc"))
        self.subtitle_item.setTextInteractionFlags(Qt.TextEditorInteraction); self.subtitle_item.setPos(8,34)

        self.handle = QGraphicsRectItem(self); self._reposition_handle()

    def _reposition_handle(self):
        r = self.rect()
        self.handle.setRect(r.right()-self.HANDLE, r.bottom()-self.HANDLE, self.HANDLE, self.HANDLE)
        self.handle.setBrush(QBrush(QColor(180,180,180)))
        self.handle.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIgnoresTransformations)
        self.handle.setZValue(self.zValue()+1)

    def mouseMoveEvent(self, event):
        if self.handle.isUnderMouse():
            p = event.scenePos()
            tl = self.mapToScene(self.rect().topLeft())
            new_w = max(200, p.x() - tl.x())
            new_h = max(80,  p.y() - tl.y())
            self.setRect(QRectF(0,0,new_w,new_h))
            self._reposition_handle()
            self.note.size = (new_w, new_h)
            self.request_dirty.emit()
        else:
            super().mouseMoveEvent(event)

    def commit(self):
        self.note.payload.title = self.title_item.toPlainText()
        self.note.payload.subtitle = self.subtitle_item.toPlainText()
        self.request_dirty.emit()

    def contextMenuEvent(self, event):
        menu, act_edit, act_open, act_del, act_cut, act_copy = self._common_menu(with_open=True)
        chosen = menu.exec(event.screenPos())
        if chosen == act_edit: self.request_edit.emit(self.note.id)
        elif act_open and chosen == act_open: self.request_open_child.emit(self.note.id)
        elif chosen == act_del: self.request_delete.emit(self.note.id)
        elif chosen == act_copy: self.request_copy.emit(self.note.id)
        elif chosen == act_cut: self.request_cut.emit(self.note.id)

    def mouseDoubleClickEvent(self, event): self.request_open_child.emit(self.note.id)

# ---- TEXTO (resizable + reflow + font +/-)
class TextoNoteItem(BaseNoteItem):
    HANDLE = 12
    def __init__(self, note: Note):
        super().__init__(note)
        self.body_item = QGraphicsTextItem(note.payload.body, self)
        self.body_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.body_item.setDefaultTextColor(QColor("#eaeaea"))
        f = QFont(); f.setPointSize(max(6, note.payload.font_pt)); self.body_item.setFont(f)
        self._pad = 8
        self._apply_text_width()
        self.handle = QGraphicsRectItem(self); self._reposition_handle()

    def _reposition_handle(self):
        r = self.rect()
        self.handle.setRect(r.right()-self.HANDLE, r.bottom()-self.HANDLE, self.HANDLE, self.HANDLE)
        self.handle.setBrush(QBrush(QColor(180,180,180)))
        self.handle.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIgnoresTransformations)
        self.handle.setZValue(self.zValue()+1)

    def _apply_text_width(self):
        w = max(120, self.rect().width() - 2*self._pad)
        self.body_item.setTextWidth(w)
        self.body_item.setPos(self._pad, self._pad)

    def contextMenuEvent(self, event):
        menu, act_edit, _a, act_del, act_cut, act_copy = self._common_menu(with_open=False)
        act_bigger = menu.addAction("Aumentar tamaño texto")
        act_smaller = menu.addAction("Reducir tamaño texto")
        chosen = menu.exec(event.screenPos())
        if chosen == act_edit: self.request_edit.emit(self.note.id)
        elif chosen == act_bigger: self._bump_font(+1)
        elif chosen == act_smaller: self._bump_font(-1)
        elif chosen == act_del: self.request_delete.emit(self.note.id)
        elif chosen == act_copy: self.request_copy.emit(self.note.id)
        elif chosen == act_cut: self.request_cut.emit(self.note.id)

    def _bump_font(self, delta: int):
        f = self.body_item.font()
        size = max(6, min(72, f.pointSize()+delta))
        f.setPointSize(size)
        self.body_item.setFont(f)
        self.note.payload.font_pt = size
        self._apply_text_width()
        self.request_dirty.emit()
        self.update()

    def mouseMoveEvent(self, event):
        if self.handle.isUnderMouse():
            p = event.scenePos()
            tl = self.mapToScene(self.rect().topLeft())
            new_w = max(160, p.x() - tl.x())
            new_h = max(80,  p.y() - tl.y())
            self.setRect(QRectF(0,0,new_w,new_h))
            self._reposition_handle(); self._apply_text_width()
            self.note.size = (new_w, new_h)
            self.request_dirty.emit()
        else:
            super().mouseMoveEvent(event)

    def focusOutEvent(self, event):
        self.note.payload.body = self.body_item.toPlainText()
        self.request_dirty.emit()
        super().focusOutEvent(event)

# ---- IMAGEN (resizable estilo PowerPoint + menú eliminar)
class ImageNoteItem(BaseNoteItem):
    HANDLE = 12
    def __init__(self, note: Note):
        super().__init__(note)
        self.pix_item = QGraphicsPixmapItem(self)
        self._reload_pixmap()
        self.handle = QGraphicsRectItem(self); self._reposition_handle()

    def _reload_pixmap(self):
        self.pix_item.setPos(2, 24)
        label = QGraphicsTextItem("Imagen", self); label.setDefaultTextColor(QColor("#aaaaaa")); label.setPos(8,4)
        if self.note.payload.image_asset:
            abs_path = os.path.join(ASSETS_DIR, self.note.payload.image_asset)
            if os.path.exists(abs_path):
                self.pix_item.setPixmap(QPixmap(abs_path).scaled(
                    int(self.rect().width()-4), int(self.rect().height()-28),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))

    def _reposition_handle(self):
        r = self.rect()
        self.handle.setRect(r.right()-self.HANDLE, r.bottom()-self.HANDLE, self.HANDLE, self.HANDLE)
        self.handle.setBrush(QBrush(QColor(180,180,180)))
        self.handle.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIgnoresTransformations)
        self.handle.setZValue(self.zValue()+1)

    def mouseMoveEvent(self, event):
        if self.handle.isUnderMouse():
            p = event.scenePos()
            tl = self.mapToScene(self.rect().topLeft())
            new_w = max(180, p.x() - tl.x())
            new_h = max(120, p.y() - tl.y())
            self.setRect(QRectF(0,0,new_w,new_h))
            self._reposition_handle(); self._reload_pixmap()
            self.note.size = (new_w, new_h)
            self.request_dirty.emit()
        else:
            super().mouseMoveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("Eliminar")
        act_cut = menu.addAction("Cortar")
        act_copy = menu.addAction("Copiar")
        chosen = menu.exec(event.screenPos())
        if chosen == act_del: self.request_delete.emit(self.note.id)
        elif chosen == act_copy: self.request_copy.emit(self.note.id)
        elif chosen == act_cut: self.request_cut.emit(self.note.id)

# ---- AUDIO (menú eliminar + no duplicarse al mover)
class AudioWidget(QWidget):
    def __init__(self, abs_audio_path: str, init_volume: int = 100, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        if abs_audio_path: self.player.setSource(QUrl.fromLocalFile(abs_audio_path))
        self.audio.setVolume(max(0.0, min(1.0, init_volume/100.0)))
        lay = QHBoxLayout(self); lay.setContentsMargins(6,6,6,6)
        self.btn = QPushButton("Play", self); self.btn.clicked.connect(self.toggle)
        self.vol = QSlider(Qt.Horizontal, self); self.vol.setRange(0,100); self.vol.setValue(init_volume)
        self.vol.valueChanged.connect(lambda v: self.audio.setVolume(max(0.0, min(1.0, v/100.0))))
        lay.addWidget(self.btn); lay.addWidget(QLabel("Vol")); lay.addWidget(self.vol)
        self.player.playbackStateChanged.connect(self.on_state)
    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause()
        else: self.player.play()
    def on_state(self, st):
        self.btn.setText("Pause" if st==QMediaPlayer.PlayingState else "Play")

class AudioNoteItem(BaseNoteItem):
    def __init__(self, note: Note):
        super().__init__(note)
        label = QGraphicsTextItem("Audio", self); label.setDefaultTextColor(QColor("#aaaaaa")); label.setPos(8,4)
        abs_path = os.path.join(ASSETS_DIR, note.payload.audio_asset) if note.payload.audio_asset else ""
        self.widget = AudioWidget(abs_path, note.payload.volume)
        self.proxy = QGraphicsProxyWidget(self); self.proxy.setWidget(self.widget); self.proxy.setPos(8,28)
        self.setRect(QRectF(0,0,max(260, self.proxy.size().width()+16), 110))

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("Eliminar")
        act_cut = menu.addAction("Cortar")
        act_copy = menu.addAction("Copiar")
        chosen = menu.exec(event.screenPos())
        if chosen == act_del: self.request_delete.emit(self.note.id)
        elif chosen == act_copy: self.request_copy.emit(self.note.id)
        elif chosen == act_cut: self.request_cut.emit(self.note.id)

# ---- ARROW (dos puntos arrastrables)
class ArrowNoteItem(BaseNoteItem):
    def __init__(self, note: Note):
        super().__init__(note)
        # el rect es solo un contenedor visual mínimo:
        self.setRect(QRectF(0,0,max(160, self.note.size[0]), max(80, self.note.size[1])))
        self.path_item = QGraphicsPathItem(self)
        self.path_item.setPen(QPen(QColor("#eaeaea"), self.note.payload.stroke))
        self.h1 = QGraphicsEllipseItem(-5,-5,10,10, self)
        self.h2 = QGraphicsEllipseItem(-5,-5,10,10, self)
        self.h1.setBrush(QBrush(QColor("#eaeaea"))); self.h2.setBrush(QBrush(QColor("#eaeaea")))
        self.h1.setFlags(QGraphicsEllipseItem.ItemIsMovable | QGraphicsEllipseItem.ItemIgnoresTransformations)
        self.h2.setFlags(QGraphicsEllipseItem.ItemIsMovable | QGraphicsEllipseItem.ItemIgnoresTransformations)
        self._sync_handles_from_payload()
        self._rebuild_path()

    def _sync_handles_from_payload(self):
        self.h1.setPos(self.note.payload.p1[0], self.note.payload.p1[1])
        self.h2.setPos(self.note.payload.p2[0], self.note.payload.p2[1])

    def _rebuild_path(self):
        p = QPainterPath()
        p.moveTo(self.h1.pos()); p.lineTo(self.h2.pos())
        # punta flecha
        ang = math.atan2(self.h2.y()-self.h1.y(), self.h2.x()-self.h1.x())
        L = 12
        left = QPointF(self.h2.x() - L*math.cos(ang - math.pi/6), self.h2.y() - L*math.sin(ang - math.pi/6))
        right= QPointF(self.h2.x() - L*math.cos(ang + math.pi/6), self.h2.y() - L*math.sin(ang + math.pi/6))
        p.moveTo(self.h2.pos()); p.lineTo(left)
        p.moveTo(self.h2.pos()); p.lineTo(right)
        self.path_item.setPath(p)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # si arrastras los handles, actualizar flecha
        self.note.payload.p1 = (self.h1.x(), self.h1.y())
        self.note.payload.p2 = (self.h2.x(), self.h2.y())
        self._rebuild_path()
        self.request_dirty.emit()

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("Eliminar")
        chosen = menu.exec(event.screenPos())
        if chosen == act_del: self.request_delete.emit(self.note.id)

# ------------------ Escena / Vista ------------------
class BoardScene(QGraphicsScene):
    request_new_idea = Signal(QPointF)
    request_new_texto = Signal(QPointF)
    request_new_emoji = Signal(QPointF)
    request_new_arrow = Signal(QPointF)
    request_paste = Signal(QPointF)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        if not item:
            menu = QMenu()
            act_idea = menu.addAction("Nueva Idea")
            act_texto = menu.addAction("Nuevo Texto")
            act_emoji = menu.addAction("Nuevo Emoji 😀")
            act_arrow = menu.addAction("Nueva Flecha →")
            menu.addSeparator()
            act_paste = menu.addAction("Pegar")
            chosen = menu.exec(event.screenPos())
            if chosen == act_idea:  self.request_new_idea.emit(event.scenePos())
            elif chosen == act_texto: self.request_new_texto.emit(event.scenePos())
            elif chosen == act_emoji: self.request_new_emoji.emit(event.scenePos())
            elif chosen == act_arrow: self.request_new_arrow.emit(event.scenePos())
            elif chosen == act_paste: self.request_paste.emit(event.scenePos())
        else:
            super().contextMenuEvent(event)

class BoardView(QGraphicsView):
    dropped_files = Signal(list)
    def __init__(self, scene: BoardScene, parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragEnterEvent(e)
    def dragMoveEvent(self, e): e.acceptProposedAction()
    def dropEvent(self, e):
        try:
            if e.mimeData().hasUrls():
                files = []
                for u in e.mimeData().urls():
                    if u.isLocalFile(): files.append(os.path.normpath(u.toLocalFile()))
                if files: self.dropped_files.emit(files)
                e.acceptProposedAction()
            else:
                super().dropEvent(e)
        except Exception as err:
            print("[drop] error:", err)

# ------------------ MainWindow ------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhiteBoard — PySide6")
        self.resize(1280, 800)

        try: self.project = load_project()
        except Exception: self.project = empty_project()

        self.current_board_id = self.project.root_board_id
        self.back_stack: List[str] = []
        self.forward_stack: List[str] = []
        self.mru: List[str] = []

        # Toolbar
        self.toolbar = QToolBar("Navegación"); self.toolbar.setMovable(False); self.addToolBar(self.toolbar)
        self.act_back = self.toolbar.addAction(self.style().standardIcon(QStyle.SP_ArrowBack), "Atrás")
        self.act_forward = self.toolbar.addAction(self.style().standardIcon(QStyle.SP_ArrowForward), "Adelante")
        self.act_back.triggered.connect(self.go_back); self.act_forward.triggered.connect(self.go_forward)
        self.btn_history = QToolButton(self); self.btn_history.setText("Historial"); self.btn_history.setPopupMode(QToolButton.InstantPopup)
        self.menu_history = QMenu(self.btn_history); self.btn_history.setMenu(self.menu_history); self.toolbar.addWidget(self.btn_history)
        self.breadcrumb = QLabel("Raíz"); self.breadcrumb.setStyleSheet("font-weight:600; margin-left:12px;"); self.toolbar.addWidget(self.breadcrumb)

        # Scene/View
        self.scene = BoardScene(self); self.view = BoardView(self.scene, self); self.setCentralWidget(self.view)

        # Footer
        self.status = QStatusBar(self); self.setStatusBar(self.status)
        self._setup_centered_footer("© 2025 Gabriel Golker")

        # Conexiones
        self.scene.request_new_idea.connect(self.create_idea_at)
        self.scene.request_new_texto.connect(self.create_texto_at)
        self.scene.request_new_emoji.connect(self.create_emoji_at)
        self.scene.request_new_arrow.connect(self.create_arrow_at)
        self.scene.request_paste.connect(self.paste_at)
        self.view.dropped_files.connect(self.handle_dropped_files)

        # Shortcuts
        self.addAction(self._shortcut("Ctrl+X", self.cut_selected))
        self.addAction(self._shortcut("Ctrl+C", self.copy_selected))
        self.addAction(self._shortcut("Ctrl+V", lambda: self.paste_at(None)))

        self.refresh_board()

    # helpers
    def _shortcut(self, seq: str, fn):
        act = QAction(self); act.setShortcut(QKeySequence(seq)); act.triggered.connect(fn); return act

    def _setup_centered_footer(self, text: str):
        for w in self.status.children():
            if isinstance(w, QWidget) and w is not self.status: w.setParent(None)
        left = QLabel(""); mid = QLabel(text); right = QLabel("")
        mid.setAlignment(Qt.AlignCenter)
        self.status.addWidget(left,1); self.status.addWidget(mid,0); self.status.addWidget(right,1)

    # navegación
    def go_to_board(self, board_id: str, push_history: bool = True):
        if push_history and board_id != self.current_board_id:
            self.back_stack.append(self.current_board_id); self.forward_stack.clear()
        self.current_board_id = board_id
        self._push_mru(board_id)
        self.refresh_board()
        self.autosave()  # autoguardar al navegar

    def go_back(self):
        if not self.back_stack: return
        prev = self.back_stack.pop()
        self.forward_stack.append(self.current_board_id)
        self.current_board_id = prev
        self._push_mru(prev)
        self.refresh_board()
        self.autosave()

    def go_forward(self):
        if not self.forward_stack: return
        nxt = self.forward_stack.pop()
        self.back_stack.append(self.current_board_id)
        self.current_board_id = nxt
        self._push_mru(nxt)
        self.refresh_board()
        self.autosave()

    def _push_mru(self, bid: str):
        if bid in self.mru: self.mru.remove(bid)
        self.mru.insert(0, bid); self.mru = self.mru[:12]
        self.menu_history.clear()
        for bid2 in self.mru:
            title = self.project.boards.get(bid2, Board(bid2)).title or bid2[:6]
            act = QAction(title, self)
            act.triggered.connect(lambda _=False, b=bid2: self.go_to_board(b, True))
            self.menu_history.addAction(act)

    def _update_breadcrumb(self):
        self.breadcrumb.setText("Raíz" if self.current_board_id == self.project.root_board_id else "… > (pizarra)")

    # escena
    def clear_scene(self): self.scene.clear()

    def refresh_board(self):
        self.clear_scene()
        board = self.project.boards[self.current_board_id]
        order = board.items_order or list(board.items.keys())
        for nid in list(order):
            n = board.items.get(nid)
            if not n:
                try: order.remove(nid)
                except: pass
                continue
            item = self._create_item(n)
            if item:
                # conectar señales (closures seguras)
                item.request_open_child.connect(lambda note_id=n.id: self.open_child_of_note(note_id))
                item.request_delete.connect(lambda note_id=n.id: self.delete_note(note_id))
                item.request_nest_into.connect(self.nest_note_into)
                item.request_copy.connect(lambda note_id=n.id: self.copy_note(note_id))
                item.request_cut.connect(lambda note_id=n.id: self.cut_note(note_id))
                item.request_edit.connect(lambda note_id=n.id: self.edit_note(note_id))
                item.request_dirty.connect(self.autosave)
        self._update_breadcrumb()

    def _create_item(self, n: Note) -> Optional[BaseNoteItem]:
        it = None
        if n.type == "idea": it = IdeaNoteItem(n)
        elif n.type == "texto": it = TextoNoteItem(n)
        elif n.type == "image": it = ImageNoteItem(n)
        elif n.type == "audio": it = AudioNoteItem(n)
        elif n.type == "emoji": it = TextoNoteItem(n)  # usamos TextoNoteItem con body=emoji
        elif n.type == "arrow": it = ArrowNoteItem(n)
        if n.type == "emoji":
            # asegurar formato emoji
            it.body_item.setPlainText(n.payload.emoji_char or "😀")
            f = it.body_item.font(); f.setPointSize(max(16, n.payload.emoji_pt)); it.body_item.setFont(f)
        if it: self.scene.addItem(it)
        return it

    # crear
    def create_idea_at(self, pos: QPointF):
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="idea", pos=(pos.x(), pos.y()), size=(260,140))
        note.payload.title = "Idea"; note.payload.subtitle = "Descripción…"
        b.items[nid] = note; b.items_order.append(nid)
        self.refresh_board(); self.autosave(); self.status.showMessage("Idea creada", 1200)

    def create_texto_at(self, pos: QPointF):
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="texto", pos=(pos.x(), pos.y()), size=(300,160))
        note.payload.body = "Escribe aquí…"; note.payload.font_pt = 12
        b.items[nid] = note; b.items_order.append(nid)
        self.refresh_board(); self.autosave(); self.status.showMessage("Texto creado", 1200)

    def create_emoji_at(self, pos: QPointF):
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="emoji", pos=(pos.x(), pos.y()), size=(100,100))
        note.payload.emoji_char = "😀"; note.payload.emoji_pt = 48
        note.payload.body = note.payload.emoji_char; note.payload.font_pt = note.payload.emoji_pt
        b.items[nid] = note; b.items_order.append(nid)
        self.refresh_board(); self.autosave(); self.status.showMessage("Emoji creado", 1200)

    def create_arrow_at(self, pos: QPointF):
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="arrow", pos=(pos.x(), pos.y()), size=(180,100))
        note.payload.p1 = (20, 50); note.payload.p2 = (160, 50); note.payload.stroke = 3
        b.items[nid] = note; b.items_order.append(nid)
        self.refresh_board(); self.autosave(); self.status.showMessage("Flecha creada", 1200)

    # DnD
    def handle_dropped_files(self, files: List[str]):
        any_created = False
        for f in files:
            try:
                ext = pathlib.Path(f).suffix.lower()
                if ext in [".png",".jpg",".jpeg",".gif",".webp"]:
                    self._create_image_note_from(f); any_created = True
                elif ext in [".mp3",".wav"]:
                    self._create_audio_note_from(f); any_created = True
            except Exception as e:
                print("[dnd] error with", f, e)
        if any_created:
            self.autosave()
            self.status.showMessage("Recurso(s) añadido(s)", 1500)
        else:
            self.status.showMessage("Formato no soportado", 2000)

    def _create_image_note_from(self, src_path: str):
        rel = copy_into_assets(src_path)
        if not rel:
            self.status.showMessage("No se pudo copiar imagen", 2000); return
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="image", pos=(40,40), size=(320,220))
        note.payload.image_asset = rel
        b.items[nid]=note; b.items_order.append(nid)
        self.refresh_board();  # autosave se dispara por refresh_board -> request_dirty al mover/resize; aquí guardamos explícito:
        self.autosave()

    def _create_audio_note_from(self, src_path: str):
        rel = copy_into_assets(src_path)
        if not rel:
            self.status.showMessage("No se pudo copiar audio", 2000); return
        b = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="audio", pos=(60,60), size=(280,120))
        note.payload.audio_asset = rel; note.payload.volume = 100
        b.items[nid]=note; b.items_order.append(nid)
        self.refresh_board(); self.autosave()

    # editar (enfocar campos)
    def edit_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items.get(note_id)
        if not n: return
        for it in self.scene.items():
            if isinstance(it, IdeaNoteItem) and it.note.id==note_id:
                it.title_item.setFocus(); return
            if isinstance(it, TextoNoteItem) and it.note.id==note_id:
                it.body_item.setFocus(); return

    # abrir subpizarra (solo idea)
    def open_child_of_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items.get(note_id)
        if not n or n.type != "idea": return
        if not n.child_board_id:
            child_id = new_id(); n.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=n.payload.title or "Sub-pizarra")
        self.go_to_board(n.child_board_id, push_history=True)

    # eliminar
    def delete_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items.get(note_id)
        if not n: return
        if n.type=="idea" and n.child_board_id:
            reply = QMessageBox.question(self, "Eliminar",
                "Esta idea tiene una sub-pizarra.\n¿Eliminar también todo su contenido?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return
            self._delete_board_recursive(n.child_board_id)
        b.items.pop(note_id, None)
        if note_id in b.items_order: b.items_order.remove(note_id)
        self.refresh_board(); self.autosave()

    def _delete_board_recursive(self, board_id: str):
        bd = self.project.boards.get(board_id)
        if not bd: return
        for n in list(bd.items.values()):
            if n.type=="idea" and n.child_board_id:
                self._delete_board_recursive(n.child_board_id)
        self.project.boards.pop(board_id, None)

    # anidar (solo sobre idea, con threshold de solapamiento: 35%)
    def nest_note_into(self, dragged_id: str, target_id: str):
        if dragged_id == target_id: return
        b = self.project.boards[self.current_board_id]
        src = b.items.get(dragged_id); tgt = b.items.get(target_id)
        if not src or not tgt or tgt.type != "idea": return
        if not tgt.child_board_id:
            child_id = new_id(); tgt.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=tgt.payload.title or "Sub-pizarra")
        child = self.project.boards[tgt.child_board_id]
        if dragged_id in child.items:  # ya está dentro
            return
        b.items.pop(dragged_id, None)
        if dragged_id in b.items_order: b.items_order.remove(dragged_id)
        src.pos = (40,40)
        child.items[dragged_id] = src; child.items_order.append(dragged_id)
        self.refresh_board(); self.autosave()

    # clipboard
    def _selected_note_id(self) -> Optional[str]:
        for it in self.scene.selectedItems():
            if isinstance(it, BaseNoteItem): return it.note.id
        return None

    def copy_selected(self):
        sel = self._selected_note_id()
        if sel: self.copy_note(sel)

    def cut_selected(self):
        sel = self._selected_note_id()
        if sel: self.cut_note(sel)

    def copy_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items.get(note_id)
        if not n: return
        subtree = self._collect_subtree(n)
        QGuiApplication.clipboard().setText(json.dumps({"whiteboard_clip": True, "root": subtree}))

    def cut_note(self, note_id: str):
        self.copy_note(note_id); self.delete_note(note_id)

    def paste_at(self, pos: Optional[QPointF]):
        clip = QGuiApplication.clipboard().text()
        try: data = json.loads(clip)
        except Exception: return
        if not isinstance(data, dict) or not data.get("whiteboard_clip"): return
        self._paste_subtree(data["root"], self.current_board_id, pos)
        self.refresh_board(); self.autosave()

    def _collect_subtree(self, note: Note) -> dict:
        node = {
            "note": {
                "type": note.type, "size": note.size, "z": note.z,
                "payload": {
                    "title": note.payload.title, "subtitle": note.payload.subtitle,
                    "body": note.payload.body, "font_pt": note.payload.font_pt,
                    "audio_asset": note.payload.audio_asset, "image_asset": note.payload.image_asset,
                    "volume": note.payload.volume,
                    "emoji_char": note.payload.emoji_char, "emoji_pt": note.payload.emoji_pt,
                    "p1": list(note.payload.p1), "p2": list(note.payload.p2), "stroke": note.payload.stroke
                }
            },
            "children": []
        }
        if note.type=="idea" and note.child_board_id:
            b = self.project.boards[note.child_board_id]
            for nid in b.items_order:
                node["children"].append(self._collect_subtree(b.items[nid]))
        return node

    def _paste_subtree(self, node: dict, board_id: str, pos: Optional[QPointF]):
        b = self.project.boards[board_id]
        nid = new_id()
        pld = node["note"]["payload"]
        # duplicar assets si aplica
        audio_asset = image_asset = ""
        if pld.get("audio_asset"):
            src = os.path.join(ASSETS_DIR, pld["audio_asset"])
            if os.path.exists(src): audio_asset = copy_into_assets(src)
        if pld.get("image_asset"):
            src = os.path.join(ASSETS_DIR, pld["image_asset"])
            if os.path.exists(src): image_asset = copy_into_assets(src)
        n = Note(
            id=nid, type=node["note"]["type"],
            pos=(pos.x(), pos.y()) if pos else (60,60),
            size=tuple(node["note"].get("size", (260,140))), z=int(node["note"].get("z",0)),
            child_board_id=None,
            payload=NotePayload(
                title=pld.get("title",""), subtitle=pld.get("subtitle",""),
                body=pld.get("body",""), font_pt=int(pld.get("font_pt",12)),
                audio_asset=audio_asset, image_asset=image_asset, volume=int(pld.get("volume",100)),
                emoji_char=pld.get("emoji_char",""), emoji_pt=int(pld.get("emoji_pt",32)),
                p1=tuple(pld.get("p1",[20,20])), p2=tuple(pld.get("p2",[140,60])),
                stroke=int(pld.get("stroke",3))
            )
        )
        b.items[nid]=n; b.items_order.append(nid)
        if n.type=="idea" and node.get("children"):
            child_id = new_id(); n.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=n.payload.title or "Sub-pizarra")
            for ch in node["children"]:
                self._paste_subtree(ch, child_id, None)

    # autosave inmediato
    def autosave(self):
        try:
            save_project(self.project, AUTOSAVE_JSON)
            self.status.showMessage("Guardado", 1000)
        except Exception as e:
            self.status.showMessage(f"Error guardando: {e}", 3000)

def main():
    app = QApplication(sys.argv)
    if QDARKSTYLE_OK:
        try: app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))
        except Exception: pass
    w = MainWindow(); w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())



