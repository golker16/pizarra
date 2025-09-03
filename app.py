import sys, os, json, shutil, uuid, time, pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QSizeF, Signal, QObject, QUrl
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QGuiApplication, QKeySequence, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStatusBar, QLabel, QToolBar, QStyle,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsProxyWidget, QMenu, QToolButton, QWidget,
    QHBoxLayout, QPushButton, QSlider, QMessageBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# --- QDarkStyle (tema oscuro para PySide6) ---
try:
    import qdarkstyle
    QDARKSTYLE_OK = True
except Exception:
    QDARKSTYLE_OK = False

# -----------------------------
# Utilidades / almacenamiento
# -----------------------------
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "WhiteBoard")
AUTOSAVE_JSON = os.path.join(APP_DIR, "last.json")
ASSETS_DIR = os.path.join(APP_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

def new_id() -> str:
    return uuid.uuid4().hex

def copy_into_assets(src_path: str) -> str:
    if not src_path or not os.path.exists(src_path):
        return ""
    ext = pathlib.Path(src_path).suffix.lower()
    dst_rel = f"{new_id()}{ext}"
    shutil.copy2(src_path, os.path.join(ASSETS_DIR, dst_rel))
    return dst_rel

# -----------------------------
# Modelo de datos
# -----------------------------
@dataclass
class NotePayload:
    # IDEA
    title: str = ""
    subtitle: str = ""
    # TEXTO
    body: str = ""
    font_pt: int = 12
    # MEDIA
    audio_asset: str = ""   # assets/<id>.mp3|wav
    image_asset: str = ""   # assets/<id>.png|jpg|...
    volume: int = 100

@dataclass
class Note:
    id: str
    type: str  # "idea" | "texto" | "audio" | "image"
    pos: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (260.0, 140.0)
    z: int = 0
    child_board_id: Optional[str] = None  # solo válido para "idea"
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
    return Project(version=3, project_id=new_id(), root_board_id=root_id, boards={root_id: root})

def save_project(p: Project, path: str = AUTOSAVE_JSON) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    serial = {
        "version": p.version,
        "project_id": p.project_id,
        "root_board_id": p.root_board_id,
        "last_opened": time.time(),
        "boards": {},
    }
    for bid, b in p.boards.items():
        serial["boards"][bid] = {
            "id": b.id, "title": b.title, "items_order": b.items_order, "items": {}
        }
        for nid, n in b.items.items():
            serial["boards"][bid]["items"][nid] = {
                "id": n.id, "type": n.type, "pos": list(n.pos), "size": list(n.size),
                "z": n.z, "child_board_id": n.child_board_id if n.type=="idea" else None,
                "payload": {
                    "title": n.payload.title, "subtitle": n.payload.subtitle,
                    "body": n.payload.body, "font_pt": n.payload.font_pt,
                    "audio_asset": n.payload.audio_asset, "image_asset": n.payload.image_asset,
                    "volume": n.payload.volume
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
            payload = NotePayload(
                title=nd["payload"].get("title",""),
                subtitle=nd["payload"].get("subtitle",""),
                body=nd["payload"].get("body",""),
                font_pt=int(nd["payload"].get("font_pt", 12)),
                audio_asset=nd["payload"].get("audio_asset",""),
                image_asset=nd["payload"].get("image_asset",""),
                volume=int(nd["payload"].get("volume",100)),
            )
            items[nid] = Note(
                id=nd["id"], type=nd["type"], pos=tuple(nd["pos"]), size=tuple(nd["size"]),
                z=int(nd["z"]),
                child_board_id=nd.get("child_board_id") if nd["type"]=="idea" else None,
                payload=payload
            )
        boards[bid] = Board(id=bd["id"], title=bd.get("title","Pizarra"),
                            items_order=bd.get("items_order", list(items.keys())), items=items)
    return Project(version=int(data.get("version",3)),
                   project_id=data.get("project_id", new_id()),
                   root_board_id=data["root_board_id"], boards=boards,
                   last_opened=float(data.get("last_opened", time.time())))

# -----------------------------
# Items visuales (QGraphics)
# -----------------------------
class BaseNoteItem(QGraphicsRectItem):
    request_open_child = Signal(str)      # note_id (solo idea)
    request_delete = Signal(str)          # note_id
    request_nest_into = Signal(str, str)  # dragged_note_id, target_note_id
    request_copy = Signal(str)            # note_id
    request_cut = Signal(str)             # note_id
    request_edit = Signal(str)            # note_id

    def __init__(self, note: Note):
        super().__init__()
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

    # Menú contextual estándar para todas las notas
    def contextMenuEvent(self, event):
        menu = QMenu()
        act_edit = menu.addAction("Editar")
        # Entrar solo si es idea
        if self.note.type == "idea":
            act_open = menu.addAction("Entrar (doble clic)")
        act_del = menu.addAction("Eliminar")
        menu.addSeparator()
        act_cut = menu.addAction("Cortar")
        act_copy = menu.addAction("Copiar")
        chosen = menu.exec(event.screenPos())
        if chosen == act_edit:
            self.request_edit.emit(self.note.id)
        elif self.note.type == "idea" and chosen and chosen.text().startswith("Entrar"):
            self.request_open_child.emit(self.note.id)
        elif chosen == act_del:
            self.request_delete.emit(self.note.id)
        elif chosen == act_copy:
            self.request_copy.emit(self.note.id)
        elif chosen == act_cut:
            self.request_cut.emit(self.note.id)

    def mouseDoubleClickEvent(self, event):
        if self.note.type == "idea":
            self.request_open_child.emit(self.note.id)
        super().mouseDoubleClickEvent(event)

    def hoverEnterEvent(self, e): self._hovering=True; self.update(); super().hoverEnterEvent(e)
    def hoverLeaveEvent(self, e): self._hovering=False; self.update(); super().hoverLeaveEvent(e)

    def paint(self, painter, option, widget=None):
        color = QColor(90, 90, 90, 180)
        if self.isSelected(): color = QColor(70, 130, 180, 220)
        elif self._hovering:  color = QColor(130, 130, 130, 200)
        painter.setBrush(QBrush(QColor(30, 30, 30, 180)))
        painter.setPen(color)
        super().paint(painter, option, widget)

    def mouseReleaseEvent(self, event):
        # Detectar drop sobre otra **idea** para anidar en su subpizarra
        scene = self.scene()
        if scene:
            items = scene.items(self.mapToScene(self.boundingRect().center()))
            for it in items:
                if isinstance(it, BaseNoteItem) and it is not self and it.note.type == "idea":
                    self.request_nest_into.emit(self.note.id, it.note.id)
                    break
        super().mouseReleaseEvent(event)

# ---- Nota IDEA (título + subtítulo, con subpizarra)
class IdeaNoteItem(BaseNoteItem):
    def __init__(self, note: Note):
        super().__init__(note)
        self.title_item = QGraphicsTextItem(note.payload.title, self)
        f1 = QFont(); f1.setPointSize(12); f1.setBold(True)
        self.title_item.setFont(f1)
        self.title_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.title_item.setDefaultTextColor(QColor("white"))
        self.title_item.setPos(8, 8)

        self.subtitle_item = QGraphicsTextItem(note.payload.subtitle, self)
        f2 = QFont(); f2.setPointSize(9)
        self.subtitle_item.setFont(f2)
        self.subtitle_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.subtitle_item.setDefaultTextColor(QColor("#cccccc"))
        self.subtitle_item.setPos(8, 34)

    def commit(self):
        self.note.payload.title = self.title_item.toPlainText()
        self.note.payload.subtitle = self.subtitle_item.toPlainText()

# ---- Nota TEXTO (puro texto, sin subpizarra) + resize + font +/- + reflow
class TextoNoteItem(BaseNoteItem):
    RESIZE_HANDLE_SIZE = 12

    def __init__(self, note: Note):
        super().__init__(note)
        self.body_item = QGraphicsTextItem(note.payload.body, self)
        self.body_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.body_item.setDefaultTextColor(QColor("#eaeaea"))
        f = QFont(); f.setPointSize(max(6, note.payload.font_pt))
        self.body_item.setFont(f)
        self._padding = 8
        self._apply_text_width()

        # Mini handle de resize en esquina inferior derecha
        self.handle = QGraphicsRectItem(self)
        self.handle.setRect(
            self.rect().right()-self.RESIZE_HANDLE_SIZE,
            self.rect().bottom()-self.RESIZE_HANDLE_SIZE,
            self.RESIZE_HANDLE_SIZE, self.RESIZE_HANDLE_SIZE
        )
        self.handle.setBrush(QBrush(QColor(180,180,180)))
        self.handle.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIgnoresTransformations)
        self.handle.setZValue(self.zValue()+1)

    def _apply_text_width(self):
        w = max(120, self.rect().width() - 2*self._padding)
        self.body_item.setTextWidth(w)
        self.body_item.setPos(self._padding, self._padding)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_edit = menu.addAction("Editar")
        act_bigger = menu.addAction("Aumentar tamaño texto")
        act_smaller = menu.addAction("Reducir tamaño texto")
        act_del = menu.addAction("Eliminar")
        menu.addSeparator()
        act_cut = menu.addAction("Cortar")
        act_copy = menu.addAction("Copiar")
        chosen = menu.exec(event.screenPos())
        if chosen == act_edit:
            self.request_edit.emit(self.note.id)
        elif chosen == act_bigger:
            self._bump_font(+1)
        elif chosen == act_smaller:
            self._bump_font(-1)
        elif chosen == act_del:
            self.request_delete.emit(self.note.id)
        elif chosen == act_copy:
            self.request_copy.emit(self.note.id)
        elif chosen == act_cut:
            self.request_cut.emit(self.note.id)

    def _bump_font(self, delta: int):
        f = self.body_item.font()
        size = max(6, min(64, f.pointSize()+delta))
        f.setPointSize(size)
        self.body_item.setFont(f)
        self.note.payload.font_pt = size
        self._apply_text_width()
        self.update()

    def mouseMoveEvent(self, event):
        # si estás arrastrando el handle, redimensiona
        if self.handle.isUnderMouse():
            p = event.scenePos()
            tl = self.mapToScene(self.rect().topLeft())
            new_w = max(160, p.x() - tl.x())
            new_h = max(80, p.y() - tl.y())
            r = QRectF(0, 0, new_w, new_h)
            self.setRect(r)
            # recolocar handle
            self.handle.setRect(r.right()-self.RESIZE_HANDLE_SIZE, r.bottom()-self.RESIZE_HANDLE_SIZE,
                                self.RESIZE_HANDLE_SIZE, self.RESIZE_HANDLE_SIZE)
            # reflow
            self._apply_text_width()
            self.note.size = (new_w, new_h)
        else:
            super().mouseMoveEvent(event)

    def focusOutEvent(self, event):
        self.note.payload.body = self.body_item.toPlainText()
        super().focusOutEvent(event)

# ---- Nota IMAGEN
class ImageNoteItem(BaseNoteItem):
    def __init__(self, note: Note):
        super().__init__(note)
        self.pix = QGraphicsPixmapItem(self)
        if note.payload.image_asset:
            abs_path = os.path.join(ASSETS_DIR, note.payload.image_asset)
            if os.path.exists(abs_path):
                self.pix.setPixmap(QPixmap(abs_path).scaled(
                    int(note.size[0]-4), int(note.size[1]-28), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
        self.pix.setPos(2, 24)
        label = QGraphicsTextItem("Imagen", self)
        label.setDefaultTextColor(QColor("#aaaaaa"))
        label.setPos(8, 4)

# ---- Nota AUDIO
class AudioWidget(QWidget):
    def __init__(self, abs_audio_path: str, init_volume: int = 100, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setSource(QUrl.fromLocalFile(abs_audio_path))
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
        label = QGraphicsTextItem("Audio", self)
        label.setDefaultTextColor(QColor("#aaaaaa"))
        label.setPos(8, 4)
        abs_path = os.path.join(ASSETS_DIR, note.payload.audio_asset) if note.payload.audio_asset else ""
        self.widget = AudioWidget(abs_path, note.payload.volume)
        self.proxy = QGraphicsProxyWidget(self); self.proxy.setWidget(self.widget)
        self.proxy.setPos(8, 28)
        self.setRect(QRectF(0,0,max(260, self.proxy.size().width()+16), 110))

# -----------------------------
# Escena / Vista
# -----------------------------
class BoardScene(QGraphicsScene):
    request_new_idea = Signal(QPointF)
    request_new_texto = Signal(QPointF)
    request_paste = Signal(QPointF)
    def contextMenuEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        if not item:
            menu = QMenu()
            act_idea = menu.addAction("Nueva Idea")
            act_texto = menu.addAction("Nuevo Texto")
            act_paste = menu.addAction("Pegar")
            chosen = menu.exec(event.screenPos())
            if chosen == act_idea:  self.request_new_idea.emit(event.scenePos())
            elif chosen == act_texto: self.request_new_texto.emit(event.scenePos())
            elif chosen == act_paste: self.request_paste.emit(event.scenePos())
        else:
            super().contextMenuEvent(event)

class BoardView(QGraphicsView):
    dropped_files = Signal(list)  # rutas
    def __init__(self, scene: BoardScene, parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragEnterEvent(e)
    def dragMoveEvent(self, e): e.acceptProposedAction()
    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if files: self.dropped_files.emit(files)
            e.acceptProposedAction()
        else: super().dropEvent(e)

# -----------------------------
# Ventana principal
# -----------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhiteBoard — PySide6")
        self.resize(1280, 800)

        # Autoload
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

        # Escena/Vista
        self.scene = BoardScene(self); self.view = BoardView(self.scene, self); self.setCentralWidget(self.view)

        # Footer
        self.status = QStatusBar(self); self.setStatusBar(self.status); self._setup_centered_footer("© 2025 Gabriel Golker")

        # Conexiones
        self.scene.request_new_idea.connect(self.create_idea_at)
        self.scene.request_new_texto.connect(self.create_texto_at)
        self.scene.request_paste.connect(self.paste_at)
        self.view.dropped_files.connect(self.handle_dropped_files)

        # Atajos
        self.addAction(self._shortcut("Ctrl+X", self.cut_selected))
        self.addAction(self._shortcut("Ctrl+C", self.copy_selected))
        self.addAction(self._shortcut("Ctrl+V", lambda: self.paste_at(None)))

        # Autosave
        self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(60_000)
        self.autosave_timer.timeout.connect(self.autosave); self.autosave_timer.start()

        self.refresh_board()

    # Helpers UI
    def _shortcut(self, seq: str, fn):
        act = QAction(self); act.setShortcut(QKeySequence(seq)); act.triggered.connect(fn); return act
    def _setup_centered_footer(self, text: str):
        for w in self.status.children():
            if isinstance(w, QWidget) and w is not self.status: w.setParent(None)
        left = QLabel(""); mid = QLabel(text); right = QLabel("")
        mid.setAlignment(Qt.AlignCenter)
        self.status.addWidget(left,1); self.status.addWidget(mid,0); self.status.addWidget(right,1)

    # Navegación
    def go_to_board(self, board_id: str, push_history: bool = True):
        if push_history and board_id != self.current_board_id:
            self.back_stack.append(self.current_board_id); self.forward_stack.clear()
        self.current_board_id = board_id; self._push_mru(board_id); self.refresh_board()

    def go_back(self):
        if not self.back_stack: return
        prev = self.back_stack.pop(); self.forward_stack.append(self.current_board_id)
        self.current_board_id = prev; self._push_mru(prev); self.refresh_board()

    def go_forward(self):
        if not self.forward_stack: return
        nxt = self.forward_stack.pop(); self.back_stack.append(self.current_board_id)
        self.current_board_id = nxt; self._push_mru(nxt); self.refresh_board()

    def _push_mru(self, bid: str):
        if bid in self.mru: self.mru.remove(bid)
        self.mru.insert(0, bid); self.mru = self.mru[:12]
        self.menu_history.clear()
        for b in self.mru:
            title = self.project.boards.get(b, Board(b)).title or b[:6]
            act = QAction(title, self); act.triggered.connect(lambda _=False, x=b: self.go_to_board(x, True))
            self.menu_history.addAction(act)

    def _update_breadcrumb(self):
        if self.current_board_id == self.project.root_board_id: self.breadcrumb.setText("Raíz"); return
        self.breadcrumb.setText("… > (pizarra)")

    # Pintar
    def clear_scene(self): self.scene.clear()

    def refresh_board(self):
        self.clear_scene()
        board = self.project.boards[self.current_board_id]
        order = board.items_order or list(board.items.keys())
        for nid in order:
            n = board.items.get(nid); 
            if not n: continue
            item = self._create_item(n)
            if item:
                item.request_open_child.connect(self.open_child_of_note)
                item.request_delete.connect(self.delete_note)
                item.request_nest_into.connect(self.nest_note_into)
                item.request_copy.connect(lambda nid=n.id: self.copy_note(nid))
                item.request_cut.connect(lambda nid=n.id: self.cut_note(nid))
                item.request_edit.connect(lambda nid=n.id: self.edit_note(nid))
        self._update_breadcrumb()

    def _create_item(self, n: Note) -> Optional[BaseNoteItem]:
        if n.type == "idea":   it = IdeaNoteItem(n)
        elif n.type == "texto": it = TextoNoteItem(n)
        elif n.type == "image": it = ImageNoteItem(n)
        elif n.type == "audio": it = AudioNoteItem(n)
        else: return None
        self.scene.addItem(it); return it

    # Crear notas
    def create_idea_at(self, pos: QPointF):
        board = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="idea", pos=(pos.x(), pos.y()))
        note.payload.title = "Idea"; note.payload.subtitle = "Descripción…"
        board.items[nid] = note; board.items_order.append(nid)
        self.refresh_board(); self.autosave()

    def create_texto_at(self, pos: QPointF):
        board = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="texto", pos=(pos.x(), pos.y()), size=(280,160))
        note.payload.body = "Escribe aquí…"; note.payload.font_pt = 12
        board.items[nid] = note; board.items_order.append(nid)
        self.refresh_board(); self.autosave()

    # DnD de archivos
    def handle_dropped_files(self, files: List[str]):
        for f in files:
            ext = pathlib.Path(f).suffix.lower()
            if ext in [".png",".jpg",".jpeg",".gif",".webp"]: self._create_image_note_from(f)
            elif ext in [".mp3",".wav"]: self._create_audio_note_from(f)
        self.autosave()

    def _create_image_note_from(self, src_path: str):
        rel = copy_into_assets(src_path); board = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="image", pos=(40,40), size=(320,220))
        note.payload.image_asset = rel
        board.items[nid]=note; board.items_order.append(nid)
        self.refresh_board()

    def _create_audio_note_from(self, src_path: str):
        rel = copy_into_assets(src_path); board = self.project.boards[self.current_board_id]
        nid = new_id()
        note = Note(id=nid, type="audio", pos=(60,60), size=(280,120))
        note.payload.audio_asset = rel; note.payload.volume = 100
        board.items[nid]=note; board.items_order.append(nid)
        self.refresh_board()

    # Editar nota
    def edit_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items.get(note_id)
        if not n: return
        # Para idea: foco en título; para texto: foco en el body
        for it in self.scene.items():
            if isinstance(it, IdeaNoteItem) and it.note.id==note_id:
                it.title_item.setFocus(); return
            if isinstance(it, TextoNoteItem) and it.note.id==note_id:
                it.body_item.setFocus(); return

    # Entrar a subpizarra (solo idea)
    def open_child_of_note(self, note_id: str):
        b = self.project.boards[self.current_board_id]; n = b.items[note_id]
        if n.type != "idea": return
        if not n.child_board_id:
            child_id = new_id(); n.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=n.payload.title or "Sub-pizarra")
        self.go_to_board(n.child_board_id, push_history=True); self.autosave()

    # Eliminar
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

    # Anidar arrastrando: solo si target es IDEA
    def nest_note_into(self, dragged_id: str, target_id: str):
        if dragged_id == target_id: return
        b = self.project.boards[self.current_board_id]
        src = b.items.get(dragged_id); tgt = b.items.get(target_id)
        if not src or not tgt or tgt.type != "idea": return
        if not tgt.child_board_id:
            child_id = new_id(); tgt.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=tgt.payload.title or "Sub-pizarra")
        child = self.project.boards[tgt.child_board_id]
        b.items.pop(dragged_id, None)
        if dragged_id in b.items_order: b.items_order.remove(dragged_id)
        src.pos = (40,40)
        child.items[dragged_id] = src; child.items_order.append(dragged_id)
        self.refresh_board(); self.autosave()

    # Clipboard
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
        subtree = self._collect_subtree(n)  # solo idea tendrá children
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
                    "volume": note.payload.volume
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
        audio_asset = ""
        image_asset = ""
        if pld.get("audio_asset"):
            src = os.path.join(ASSETS_DIR, pld["audio_asset"])
            if os.path.exists(src): audio_asset = copy_into_assets(src)
        if pld.get("image_asset"):
            src = os.path.join(ASSETS_DIR, pld["image_asset"])
            if os.path.exists(src): image_asset = copy_into_assets(src)
        n = Note(
            id=nid, type=node["note"]["type"],
            pos=(pos.x(), pos.y()) if pos else (60,60),
            size=tuple(node["note"].get("size", (260,140))),
            z=int(node["note"].get("z", 0)),
            child_board_id=None,
            payload=NotePayload(
                title=pld.get("title",""), subtitle=pld.get("subtitle",""),
                body=pld.get("body",""), font_pt=int(pld.get("font_pt",12)),
                audio_asset=audio_asset, image_asset=image_asset, volume=int(pld.get("volume",100))
            )
        )
        b.items[nid]=n; b.items_order.append(nid)
        # hijos solo si es idea
        if n.type=="idea" and node.get("children"):
            child_id = new_id(); n.child_board_id = child_id
            self.project.boards[child_id] = Board(id=child_id, title=n.payload.title or "Sub-pizarra")
            for ch in node["children"]:
                self._paste_subtree(ch, child_id, None)

    # Autosave
    def autosave(self):
        try:
            save_project(self.project, AUTOSAVE_JSON)
            self.status.showMessage("Guardado automáticamente", 2000)
        except Exception as e:
            self.status.showMessage(f"Error guardando: {e}", 4000)

def main():
    app = QApplication(sys.argv)
    if QDARKSTYLE_OK:
        try: app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))
        except Exception: pass
    w = MainWindow(); w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
