import sys
import os
import math
import json
import random

try:
    import keyboard
    import pyperclip
except ImportError as error:
    sys.exit(f"Не найдена зависимость '{error.name}'. Установите её: pip install keyboard pyperclip")

from PyQt6.QtWidgets import (
    QApplication, QWidget, QListWidget, QListWidgetItem, QLineEdit, QLabel,
    QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox, QAbstractItemView, QComboBox,
    QToolButton, QDialog, QDialogButtonBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QPoint, QObject, QTimer, pyqtSignal, QPropertyAnimation, pyqtProperty,
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetricsF, QPainterPath, QCursor, QGuiApplication,
    QBrush, QPen, QPixmap, QRadialGradient, QIcon, QDrag,
)

# Ваши любимые смайлики по умолчанию: используются, если файл настроек ещё не создан
DEFAULT_EMOJIS = ["ಠ_ಠ", "(￣ー￣ )", "(づ｡◕‿‿◕｡)づ", "(つ≧▽≦)つ", "≽^•⩊•^≼", "(^◕.◕^)", "(⁄ ⁄>⁄ ▽ ⁄<⁄ ⁄)", "(⁄ ⁄>⁄ ⁄ <⁄ ⁄)", "(⸝⸝⸝O﹏O⸝⸝⸝)", "ദ്ദി◝ ⩊ ◜.ᐟ", "(˵ ¬ᴗ¬˵)", "￣へ￣", "=￣ω￣=", "(─‿‿─)", "(=⌒‿‿⌒=)"]

# Невидимые символы, которые часто попадают в скопированные смайлики и ломают поиск.
# U+200D (ZWJ) намеренно не удаляем: он склеивает составные эмодзи.
INVISIBLE_CHARS = str.maketrans("", "", "\u200b\u200c\u2060\ufeff")

MENU_SIZE = 900             # Размер окна меню на большом экране
MIN_MENU_SIZE = 520         # Минимальный размер, чтобы меню влезло на маленьком экране
SCREEN_FILL_RATIO = 0.9     # Какую часть экрана меню может занимать максимум
BASE_FONT_RATIO = 0.112     # Кегль подписи относительно толщины кольца
BASE_LABEL_FONT = 20        # Нижняя граница базового кегля
MIN_LABEL_FONT = 8          # Ниже этого кегля не уменьшаем, а сжимаем по ширине
SLICE_FILL_RATIO = 0.85     # Какая часть сектора отводится под подпись
RING_INNER_RATIO = 0.4      # Пустая середина при одном кольце (подписи дальше от центра)
MULTI_RING_INNER_RATIO = 0.25  # Середина при нескольких кольцах: нужно место под второе
RING_GAP_RATIO = 0.06       # Зазор между кольцами относительно внешнего радиуса
RING_CAPACITY = 18          # Сколько смайликов помещается в одно кольцо
MAX_RINGS = 3               # Дальше кольца станут слишком тонкими, а секторы узкими
PASTE_DELAY_MS = 60         # Пауза перед Ctrl+V, чтобы окно успело скрыться
CLIPBOARD_RESTORE_MS = 400  # Через сколько вернуть прежнее содержимое буфера

# Формат, которым Qt передаёт строки списка при перетаскивании внутри виджета
MODEL_MIME_TYPE = "application/x-qabstractitemmodeldatalist"

def _app_dir():
    """Папка рядом с программой: у собранного .exe своя, у скрипта своя."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundle_dir():
    """Папка встроенных ресурсов: внутри onefile-сборки это временная распаковка."""
    return getattr(sys, "_MEIPASS", _app_dir())


# Данные пользователя храним рядом с программой. Внутри сборки их держать нельзя:
# временная папка onefile удаляется при выходе и смайлики пропадали бы при перезапуске
APP_DIR = _app_dir()
BUNDLE_DIR = _bundle_dir()

EMOJIS_PATH = os.path.join(APP_DIR, "emojis.json")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
BACKGROUND_PATH = os.path.join(APP_DIR, "background.png")
# Иконку ищем сначала рядом с программой (свою), затем среди встроенных ресурсов
ICON_CANDIDATES = (
    os.path.join(APP_DIR, "CursorBar.svg"),
    os.path.join(BUNDLE_DIR, "CursorBar.svg"),
)

DEFAULT_STYLE = "classic"

# Стили колеса: цвета подложки, подсветки и подписей.
# background — своя картинка пользователя (если файл background.png лежит рядом со скриптом)
STYLES = {
    "classic": {
        "name": "Классический",
        "ring": (30, 30, 30, 220),
        "highlight": (100, 150, 255, 120),
        "label": (255, 255, 255),
        "decoration": None,
    },
    "space": {
        "name": "Космос",
        "ring": (46, 22, 82, 228),
        "highlight": (168, 108, 255, 150),
        "label": (240, 226, 255),
        "decoration": "stars",
        "accent": (198, 150, 255),
    },
    "furry": {
        "name": "Мили-фурри",
        "ring": (255, 176, 214, 246),
        "highlight": (255, 96, 168, 190),
        "label": (86, 24, 58),
        "decoration": "paws",
        "accent": (255, 64, 150),
        # Белая «стикерная» обводка кольца и её толщина относительно радиуса
        "outline": ((255, 255, 255), 0.012),
    },
}


def style_names():
    """Стили в порядке показа в списке редактора."""
    return list(STYLES.keys())


def load_settings(path=SETTINGS_PATH):
    """Читает настройки. При отсутствии или поломке файла берёт значения по умолчанию."""
    settings = {"style": DEFAULT_STYLE}
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return settings
    except (json.JSONDecodeError, OSError) as error:
        print(f"Не удалось прочитать {path} ({error}). Использую настройки по умолчанию.")
        return settings

    if not isinstance(data, dict):
        print(f"Файл {path} должен содержать объект настроек. Использую значения по умолчанию.")
        return settings

    # Неизвестный стиль (например, файл правили вручную) не должен ломать меню
    style = data.get("style")
    if style in STYLES:
        settings["style"] = style
    elif style is not None:
        print(f"Неизвестный стиль {style!r} в {path}. Использую «{DEFAULT_STYLE}».")
    return settings


def save_settings(settings, path=SETTINGS_PATH):
    """Сохраняет настройки. Возвращает текст ошибки или None при успехе."""
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
        return None
    except OSError as error:
        return str(error)


def clean_emoji(text):
    """Убирает невидимые символы и лишние пробелы по краям."""
    return text.translate(INVISIBLE_CHARS).strip()


def load_emojis(path=EMOJIS_PATH):
    """Читает список смайликов из JSON. При отсутствии или поломке файла берёт стандартный набор."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return list(DEFAULT_EMOJIS)
    except (json.JSONDecodeError, OSError) as error:
        print(f"Не удалось прочитать {path} ({error}). Использую стандартный набор.")
        return list(DEFAULT_EMOJIS)

    if not isinstance(data, list):
        print(f"Файл {path} должен содержать список строк. Использую стандартный набор.")
        return list(DEFAULT_EMOJIS)

    # Оставляем только непустые строки: мусор в файле не должен ломать меню
    emojis = [clean_emoji(item) for item in data if isinstance(item, str)]
    return [emoji for emoji in emojis if emoji]


def save_emojis(emojis, path=EMOJIS_PATH):
    """Сохраняет список смайликов в JSON. Возвращает текст ошибки или None при успехе."""
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(emojis, file, ensure_ascii=False, indent=2)
        return None
    except OSError as error:
        return str(error)


# Иконку держим в глобальной переменной: на части систем окно теряет значок,
# если объект QIcon удалён сборщиком мусора сразу после setWindowIcon
APP_ICON = None


def load_app_icon(path=None):
    """Иконка приложения из SVG. Возвращает None, если файла нет или он повреждён."""
    global APP_ICON
    if APP_ICON is not None:
        return APP_ICON
    # Путь не задан — ищем среди известных мест: рядом с программой, затем во вложениях
    candidates = ICON_CANDIDATES if path is None else (path,)
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        icon = QIcon(candidate)
        if icon.isNull():
            print(f"Не удалось прочитать иконку {candidate}. Работаю без неё.")
            continue
        APP_ICON = icon
        return APP_ICON
    return None


class HotkeyListener(QObject):
    # Сигналы нужны, чтобы безопасно трогать окна из потока библиотеки keyboard
    triggered = pyqtSignal()
    dismissed = pyqtSignal()
    edit_requested = pyqtSignal()


def _star_path(radius):
    """Пятиконечная звезда с центром в (0,0) — для космического стиля."""
    path = QPainterPath()
    inner = radius * 0.42
    for i in range(10):
        r = radius if i % 2 == 0 else inner
        angle = math.radians(-90 + i * 36)
        x, y = math.cos(angle) * r, math.sin(angle) * r
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _sparkle_path(radius):
    """Четырёхлучевая искорка с центром в (0,0)."""
    path = QPainterPath()
    inner = radius * 0.24
    for i in range(8):
        r = radius if i % 2 == 0 else inner
        angle = math.radians(-90 + i * 45)
        x, y = math.cos(angle) * r, math.sin(angle) * r
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _heart_path(scale):
    """Сердечко с остриём внизу, центр в (0,0)."""
    path = QPainterPath()
    path.moveTo(0, 0.92 * scale)
    path.cubicTo(-1.32 * scale, -0.04 * scale, -0.66 * scale, -1.10 * scale, 0, -0.40 * scale)
    path.cubicTo(0.66 * scale, -1.10 * scale, 1.32 * scale, -0.04 * scale, 0, 0.92 * scale)
    path.closeSubpath()
    return path


def _paw_path(scale):
    """Отпечаток лапки: подушечка и четыре пальчика, центр в (0,0)."""
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0.52 * scale), 0.68 * scale, 0.58 * scale)
    for dx, dy, r in ((-1.08, -0.56, 0.32), (-0.40, -1.00, 0.33), (0.40, -1.00, 0.33), (1.08, -0.56, 0.32)):
        path.addEllipse(QPointF(dx * scale, dy * scale), r * scale, r * scale)
    return path





def ring_bounds_for(radius, rings, ring):
    """Границы кольца: (внутренний, внешний радиус). Кольцо 0 — самое внешнее.

    Отдельная функция без окна: те же расчёты нужны подсказке в редакторе,
    и дублировать формулы нельзя — подсказка разошлась бы с колесом.
    """
    inner_ratio = RING_INNER_RATIO if rings == 1 else MULTI_RING_INNER_RATIO
    inner = radius * inner_ratio
    gap = radius * RING_GAP_RATIO
    band = (radius - inner - gap * (rings - 1)) / rings
    outer = radius - ring * (band + gap)
    return outer - band, outer


def label_slot_for(radius, rings, ring, in_ring):
    """Слот подписи: (радиус текста, ширина, высота, толщина кольца)."""
    inner_radius, outer_radius = ring_bounds_for(radius, rings, ring)
    text_radius = (inner_radius + outer_radius) / 2
    thickness = outer_radius - inner_radius
    arc = 2 * math.pi * text_radius / in_ring if in_ring > 1 else thickness
    return text_radius, arc * SLICE_FILL_RATIO, thickness * SLICE_FILL_RATIO, thickness


def fit_label_font(text, max_width, base_size):
    """Подбирает кегль, чтобы подпись влезла в слот по ширине.

    Возвращает (кегль, сжатие по горизонтали): если даже минимальный кегль шире
    слота, подпись дополнительно сжимается.
    """
    # Кегль растёт вместе с толщиной кольца, чтобы подписи не мельчали
    base = max(BASE_LABEL_FONT, int(base_size * BASE_FONT_RATIO))
    floor = max(MIN_LABEL_FONT, int(base * 0.4))

    font = QFont("Arial", base, QFont.Weight.Bold)
    for size in range(base, floor - 1, -1):
        font.setPointSize(size)
        if QFontMetricsF(font).horizontalAdvance(text) <= max_width:
            return size, 1.0

    advance = QFontMetricsF(font).horizontalAdvance(text)
    return floor, max_width / advance if advance > max_width else 1.0


def wheel_overview(emojis, size=MENU_SIZE):
    """Что выйдет из списка: (число колец, смайликов в кольце, худший кегль подписи).

    Повторяет расчёты колеса, не создавая окно, — только для подсказки в редакторе.
    """
    count = len(emojis)
    if count <= 0:
        return 0, 0, 0

    radius = size / 2
    rings = min(math.ceil(count / RING_CAPACITY), MAX_RINGS)
    per_ring = math.ceil(count / rings)

    worst = None
    for index, emoji in enumerate(emojis):
        ring = min(index // per_ring, rings - 1)
        in_ring = max(0, min(per_ring, count - ring * per_ring))
        _, slot_width, _, thickness = label_slot_for(radius, rings, ring, in_ring)
        font_size, _ = fit_label_font(emoji, slot_width, thickness)
        worst = font_size if worst is None else min(worst, font_size)
    return rings, per_ring, worst


class EmojiList(QListWidget):
    """Список смайликов: перетаскивание меняет порядок строк, а не удаляет их.

    Перемещение ведём целиком сами. Штатный QAbstractItemView.startDrag после
    успешного MoveAction вызывает clearOrRemove() и удаляет строки, оставшиеся
    выделенными, — а перенесённые строки выделены, чтобы блок можно было тащить
    дальше или сразу удалить. Именно поэтому смайлик исчезал вместо переезда.
    """

    order_changed = pyqtSignal()
    delete_requested = pyqtSignal()
    duplicate_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDropIndicatorShown(True)
        # Куда уронили строки: заполняет dropEvent, читает startDrag
        self._drop_row = None
        # Где нажали мышью: нужно для правильной точки захвата картинки
        self._press_pos = None

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # Пока идёт правка строки, клавиши обрабатывает сам редактор поля
        editing = self.state() == QAbstractItemView.State.EditingState
        if not editing and event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        if not editing and event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_requested.emit()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event):
        """Запоминает место сброса. Сам перенос делает startDrag после перетаскивания.

        Здесь нельзя менять строки: Qt выполнит свой clearOrRemove() сразу после
        возврата из drag.exec() и удалит те строки, которые окажутся выделенными.
        """
        # Своё перетаскивание узнаём по источнику или по формату строк списка.
        # Одного event.source() мало: у синтетических событий он пуст, поэтому
        # дополнительно смотрим формат данных
        own = (event.source() is self
               or event.mimeData().hasFormat(MODEL_MIME_TYPE))
        if not own:
            event.ignore()
            return

        row = self.indexAt(event.position().toPoint()).row()
        # Ниже последней строки indexAt даёт -1 — это значит «в конец»
        self._drop_row = self.count() if row < 0 else row
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def startDrag(self, supported_actions):
        rows = sorted({index.row() for index in self.selectedIndexes()})
        if not rows:
            return

        items = [self.item(row) for row in rows]
        mime = self.model().mimeData([self.model().index(row, 0) for row in rows])
        if mime is None:
            return

        drag = QDrag(self)
        drag.setMimeData(mime)
        # Тянем картинку со всеми выделенными строками, а не только с одной
        rect = self.visualItemRect(items[0])
        for item in items[1:]:
            rect = rect.united(self.visualItemRect(item))
        drag.setPixmap(self.viewport().grab(rect))
        # Захват — там, где нажали кнопку, иначе картинка «прыгает» под курсор
        if self._press_pos is not None and rect.contains(self._press_pos):
            drag.setHotSpot(self._press_pos - rect.topLeft())
        else:
            drag.setHotSpot(rect.center() - rect.topLeft())

        self._drop_row = None
        if drag.exec(Qt.DropAction.MoveAction,
                     Qt.DropAction.MoveAction) != Qt.DropAction.MoveAction:
            return
        if self._drop_row is None:
            return

        self._apply_move(rows, self._drop_row)
        self._drop_row = None

    def _apply_move(self, rows, drop_row):
        """Переносит строки rows на место drop_row."""
        # Перетаскивание на себя или сразу под собой ничего не меняет
        if len(rows) == 1 and drop_row in (rows[0], rows[0] + 1):
            return

        # Строки выше места сброса после изъятия поднимутся — целимся с поправкой
        target = drop_row - sum(1 for row in rows if row < drop_row)
        items = [self.item(row) for row in rows]

        for item in items:
            self.takeItem(self.row(item))
        for offset, item in enumerate(items):
            self.insertItem(target + offset, item)

        # Возвращаем выделение перенесённому блоку, чтобы его можно было
        # тащить дальше или сразу удалить
        self.clearSelection()
        self.setCurrentRow(self.row(items[0]))
        for item in items:
            item.setSelected(True)
        self.order_changed.emit()


class EmojiEditor(QWidget):
    """Окно редактирования списка смайликов."""

    saved = pyqtSignal(list)
    exit_requested = pyqtSignal()
    style_changed = pyqtSignal(str)

    def __init__(self, emojis, style=DEFAULT_STYLE):
        super().__init__()
        self.setWindowTitle("Смайлики меню")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        icon = load_app_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(420, 560)

        self.list_widget = EmojiList()
        # Двойной клик по строке позволяет поправить смайлик прямо в списке
        self.list_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.list_widget.delete_requested.connect(self.remove_selected)
        self.list_widget.duplicate_requested.connect(self.duplicate_selected)
        self.list_widget.order_changed.connect(self._update_capacity)
        # Правка строки на месте тоже меняет список — обновляем счётчик
        self.list_widget.itemChanged.connect(lambda _item: self._update_capacity())

        # Счётчик подсказывает, сколько смайликов и насколько крупно они лягут в колесо.
        # Создаём до наполнения списка: set_emojis() уже обновляет счётчик.
        # Подпись сжимаемая: иначе она распирает ширину всего окна
        self.capacity_label = QLabel()
        self.capacity_label.setToolTip(
            "Чем больше смайликов, тем мельче подписи в колесе.")
        self.capacity_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                          QSizePolicy.Policy.Preferred)

        self.set_emojis(emojis)
        # Снимок записанного списка: с ним сравниваем текущий, чтобы видеть несохранённые правки
        self._saved_emojis = self.current_emojis()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Новый смайлик — и Enter")
        self.input.returnPressed.connect(self.add_emoji)

        add_button = QPushButton("Добавить")
        add_button.clicked.connect(self.add_emoji)

        # Перемещение — компактными стрелками: они не спорят за место со словами
        up_button = QToolButton()
        up_button.setText("↑")
        up_button.setToolTip("Поднять выбранные (Ctrl+↑)")
        up_button.setShortcut("Ctrl+Up")
        up_button.clicked.connect(lambda: self.move_selected(-1))
        down_button = QToolButton()
        down_button.setText("↓")
        down_button.setToolTip("Опустить выбранные (Ctrl+↓)")
        down_button.setShortcut("Ctrl+Down")
        down_button.clicked.connect(lambda: self.move_selected(1))

        remove_button = QToolButton()
        remove_button.setText("✕")
        remove_button.setToolTip("Удалить выбранные (Delete)")
        remove_button.clicked.connect(self.remove_selected)

        self.style_box = QComboBox()
        for key in style_names():
            self.style_box.addItem(STYLES[key]["name"], key)
        selected = style if style in STYLES else DEFAULT_STYLE
        self.style_box.setCurrentIndex(self.style_box.findData(selected))
        self.style_box.currentIndexChanged.connect(self._on_style_selected)
        # Снимок вида: сравниваем с ним, чтобы видеть несохранённую смену стиля
        self._saved_style = self.current_style()

        list_tools = QHBoxLayout()
        list_tools.addWidget(remove_button)
        list_tools.addWidget(up_button)
        list_tools.addWidget(down_button)
        list_tools.addStretch(1)
        list_tools.addWidget(self.capacity_label)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Вид колеса:"))
        style_row.addWidget(self.style_box, 1)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(add_button)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)
        info_button = QPushButton("Справка")
        info_button.setToolTip("Подсказки по работе с редактором")
        info_button.clicked.connect(self.show_help)
        # Короткая подпись: длинная распирала бы ширину окна
        exit_button = QPushButton("Выход")
        exit_button.setToolTip("Закрыть меню смайликов полностью")
        exit_button.clicked.connect(self.request_exit)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(info_button)
        bottom_row.addWidget(exit_button)
        bottom_row.addStretch(1)
        bottom_row.addWidget(save_button)

        # Разделители отделяют список от настроек и кнопок
        self.divider_top = QFrame()
        self.divider_top.setFrameShape(QFrame.Shape.HLine)
        self.divider_top.setFrameShadow(QFrame.Shadow.Sunken)
        self.divider_bottom = QFrame()
        self.divider_bottom.setFrameShape(QFrame.Shape.HLine)
        self.divider_bottom.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(list_tools)
        layout.addWidget(self.divider_top)
        layout.addLayout(input_row)
        layout.addLayout(style_row)
        layout.addWidget(self.divider_bottom)
        layout.addLayout(bottom_row)

        # Подсказка живёт под списком и не отнимает у него место
        self.list_widget.setToolTip(
            "Двойной клик — изменить, перетаскивание — поменять порядок, "
            "Delete — удалить")
        self._update_capacity()

        self.input.setFocus()

    def set_emojis(self, emojis):
        self.list_widget.clear()
        for emoji in emojis:
            self._add_item(emoji)

    def _add_item(self, text):
        item = QListWidgetItem(text)
        # Флаг редактирования делает строку изменяемой на месте
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.list_widget.addItem(item)
        return item

    def _update_capacity(self):
        """Показывает, сколько смайликов и насколько крупно ляжет в колесо."""
        emojis = self.current_emojis()
        if not emojis:
            self.capacity_label.setText("список пуст")
            self.capacity_label.setToolTip("Добавьте хотя бы один смайлик.")
            return

        rings, per_ring, font_size = wheel_overview(emojis)
        ring_word = {1: "кольцо", 2: "кольца", 3: "кольца"}.get(rings, "колец")
        # В строке только самое важное: сколько смайликов и насколько крупны подписи.
        # Подробности уходят в подсказку — иначе текст не помещается по ширине
        self.capacity_label.setText(f"{len(emojis)} шт. · кегль ~{font_size}")
        self.capacity_label.setToolTip(
            f"{len(emojis)} смайликов: {rings} {ring_word} по {per_ring}, "
            f"подписи кеглем ~{font_size}.\n"
            "Чем больше смайликов, тем мельче подписи в колесе.")

    def duplicate_selected(self):
        """Копирует выбранные строки рядом с оригиналами."""
        rows = sorted({self.list_widget.row(item)
                       for item in self.list_widget.selectedItems()})
        if not rows:
            return
        for offset, row in enumerate(rows):
            source = self.list_widget.item(row + offset)
            copy_item = QListWidgetItem(source.text())
            copy_item.setFlags(copy_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list_widget.insertItem(row + offset + 1, copy_item)
        self._update_capacity()

    def show_help(self):
        """Окно-справка: подсказки, которые раньше занимали место в самом редакторе."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Справка")
        dialog.setMinimumWidth(440)

        text = QLabel(
            "<b>Как собрать своё меню</b>"
            "<ul>"
            "<li><b>Добавить</b> — введите смайлик и нажмите Enter.</li>"
            "<li><b>Изменить</b> — двойной клик по строке.</li>"
            "<li><b>Порядок</b> — перетащите строку мышью или нажмите Ctrl+↑ / Ctrl+↓.<br>"
            "Порядок в списке совпадает с порядком по кругу.</li>"
            "<li><b>Удалить</b> — выберите строки и нажмите Delete.</li>"
            "<li><b>Вид колеса</b> — переключается сразу, но сохраняется по кнопке "
            "«Сохранить».</li>"
            "</ul>"
            "<b>Подсказки</b>"
            "<ul>"
            "<li>Кольца появляются сами: 18 смайликов — одно кольцо, дальше "
            "добавляется второе и третье.</li>"
            "<li>Чем больше смайликов, тем мельче подписи. До 36 они остаются "
            "крупными, после 80 начинают сжиматься.</li>"
            "<li>Своя картинка вместо фона: положите файл "
            "<b>background.png</b> рядом со скриптом.</li>"
            "<li>Смайлики хранятся в <b>emojis.json</b>, вид колеса — в "
            "<b>settings.json</b> рядом со скриптом.</li>"
            "</ul>"
            "<b>Горячие клавиши</b>"
            "<ul>"
            "<li><b>Ctrl+Shift+E</b> — открыть меню.</li>"
            "<li><b>Ctrl+Shift+R</b> — открыть этот редактор.</li>"
            "<li><b>Esc</b> или правая кнопка мыши — закрыть меню.</li>"
            "</ul>"
        )
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text)
        layout.addWidget(buttons)
        dialog.exec()

    def closeEvent(self, event):
        """Крестик окна не должен молча терять несохранённые правки."""
        if not self.has_unsaved_changes():
            self.hide()
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            "Есть несохранённые изменения",
            "Вы изменили список, но не сохранили его. Сохранить перед закрытием?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            # При успешном сохранении окно скрывает сам save()
            if self.save():
                event.accept()
                return
            event.ignore()
        elif answer == QMessageBox.StandardButton.Discard:
            # Правки отбрасываем — возвращаем сохранённый список
            self.set_emojis(self._saved_emojis)
            index = self.style_box.findData(load_settings()["style"])
            if index >= 0:
                self.style_box.blockSignals(True)
                self.style_box.setCurrentIndex(index)
                self.style_box.blockSignals(False)
            self.hide()
            event.accept()
        else:
            event.ignore()

    def current_emojis(self):
        emojis = []
        for row in range(self.list_widget.count()):
            emoji = clean_emoji(self.list_widget.item(row).text())
            if emoji:
                emojis.append(emoji)
        return emojis

    def add_emoji(self):
        emoji = clean_emoji(self.input.text())
        if not emoji:
            QMessageBox.information(self, "Пустая строка", "Сначала введите смайлик.")
            return

        item = self._add_item(emoji)
        self.list_widget.setCurrentItem(item)
        self.list_widget.scrollToItem(item)
        self.input.clear()
        self._update_capacity()

    def remove_selected(self):
        # Удаляем снизу вверх, чтобы индексы выбранных строк не сдвигались
        for item in reversed(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_capacity()

    def move_selected(self, offset):
        rows = sorted({self.list_widget.row(item)
                       for item in self.list_widget.selectedItems()})
        if not rows:
            row = self.list_widget.currentRow()
            rows = [row] if row >= 0 else []
        if not rows:
            return

        # Двигаем блок выделенных строк целиком, сохраняя их взаимный порядок
        if offset < 0:
            if rows[0] == 0:
                return
            targets = [row - 1 for row in rows]
        else:
            if rows[-1] == self.list_widget.count() - 1:
                return
            targets = [row + 1 for row in rows]

        # Извлекаем забираемые строки, а затем вставляем их по новым местам.
        # takeItem сдвигает индексы, поэтому берём исходные объекты заранее.
        items = [self.list_widget.item(row) for row in rows]
        for item in items:
            self.list_widget.takeItem(self.list_widget.row(item))
        for target, item in zip(targets, items):
            self.list_widget.insertItem(target, item)

        # Восстанавливаем выделение блока целиком: одиночная текущая строка
        # не дала бы сдвинуть блок повторным нажатием
        self.list_widget.clearSelection()
        first_row = self.list_widget.row(items[0])
        self.list_widget.setCurrentRow(first_row)
        for item in items:
            item.setSelected(True)
        self.list_widget.order_changed.emit()

    def current_style(self):
        return self.style_box.currentData()

    def _on_style_selected(self, index):
        # Вид применяется сразу, но в файл попадёт только по кнопке «Сохранить»
        self.style_changed.emit(self.style_box.itemData(index))

    def save(self):
        """Сохраняет список и вид колеса. Возвращает True, если запись прошла успешно."""
        emojis = self.current_emojis()
        if not emojis:
            QMessageBox.warning(self, "Список пуст", "Нужен хотя бы один смайлик, иначе меню ничего не покажет.")
            return False

        error = save_emojis(emojis)
        if error:
            QMessageBox.critical(self, "Не удалось сохранить", error)
            return False

        error = save_settings({"style": self.current_style()})
        if error:
            QMessageBox.critical(self, "Не удалось сохранить вид", error)
            return False

        # Приводим список к тому, что реально записано (без пустых строк)
        self.set_emojis(emojis)
        self._saved_emojis = list(emojis)
        self._saved_style = self.current_style()
        self.saved.emit(emojis)
        self.hide()
        return True

    def has_unsaved_changes(self):
        """Есть ли правки относительно того, что было записано при открытии редактора.

        Сравниваем со снимком, а не с файлом: файл мог измениться извне, и тогда
        редактор жаловался бы на изменения, которых пользователь не делал.
        """
        return (self.current_emojis() != self._saved_emojis
                or self.current_style() != self._saved_style)

    def request_exit(self):
        """Спрашивает подтверждение и завершает программу."""
        # Несохранённые правки предлагаем записать, иначе они потеряются
        if self.has_unsaved_changes():
            answer = QMessageBox.question(
                self,
                "Выйти из программы?",
                "В списке есть несохранённые изменения. Сохранить их перед выходом?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Save:
                if not self.save():
                    # Сохранить не удалось — не выходим, чтобы не потерять правки
                    return
            elif answer != QMessageBox.StandardButton.Discard:
                # Отмена, закрытие диалога или любой другой ответ — остаёмся в программе
                return
        elif QMessageBox.question(
            self,
            "Выйти из программы?",
            "Закрыть меню смайликов?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.exit_requested.emit()

    def show_editor(self, emojis, style=DEFAULT_STYLE):
        self.set_emojis(emojis)
        self._saved_emojis = list(emojis)
        index = self.style_box.findData(style)
        if index >= 0:
            # Синхронизируем список со стилем меню, не порождая ложный сигнал об изменении
            self.style_box.blockSignals(True)
            self.style_box.setCurrentIndex(index)
            self.style_box.blockSignals(False)
        # Снимок вида берём после синхронизации: только реальные правки считаются изменениями
        self._saved_style = self.current_style()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, event):
        # Esc закрывает окно; изменения применяются только кнопкой "Сохранить"
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

class RadialMenu(QWidget):
    # --- БЛОК АНИМАЦИИ ---
    def get_opacity(self):
        return self.windowOpacity()

    def set_opacity(self, opacity):
        self.setWindowOpacity(opacity)

    # Свойство для плавного появления окна
    opacity_anim = pyqtProperty(float, get_opacity, set_opacity)

    def __init__(self, emojis, style=DEFAULT_STYLE):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        icon = load_app_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        self.emojis = list(emojis)
        self.style = style if style in STYLES else DEFAULT_STYLE
        # Своя картинка-фон читается один раз, при первом обращении
        self._background = None
        self._background_loaded = False
        # Размер окна подстраивается под экран в show_centered()
        self.resize(MENU_SIZE, MENU_SIZE)

        self.setMouseTracking(True)
        self.hovered_index = -1

        # Кэш геометрии и шрифтов: пересчитываем только при смене размера или списка,
        # иначе подбор шрифта на каждой перерисовке заметно тормозит подсветку
        self._paint_key = None
        self._paint_data = None
        # Готовые слои кадра (подложка и подписи): рисовать их путями каждый кадр
        # дорого, а при наведении меняется только подсветка
        self._scene_layers_cache = None

        # Настройка анимации появления (150 мс)
        self.fade_anim = QPropertyAnimation(self, b"opacity_anim")
        self.fade_anim.setDuration(150)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)

    @property
    def radius(self):
        # Радиус выводим из размера окна, чтобы он не разъезжался с ним при resize
        return min(self.width(), self.height()) / 2

    @property
    def ring_count(self):
        """Сколько концентрических колец нужно для текущего списка."""
        if not self.emojis:
            return 1
        return min(math.ceil(len(self.emojis) / RING_CAPACITY), MAX_RINGS)

    @property
    def emojis_per_ring(self):
        """Сколько смайликов ложится в одно кольцо: раскладываем по кольцам поровну."""
        if not self.emojis:
            return 0
        return math.ceil(len(self.emojis) / self.ring_count)

    @property
    def inner_radius(self):
        """Радиус пустой середины: при нескольких кольцах она уже, чтобы хватило места."""
        ratio = RING_INNER_RATIO if self.ring_count == 1 else MULTI_RING_INNER_RATIO
        return self.radius * ratio

    def ring_bounds(self, ring):
        """Возвращает (внутренний радиус, внешний радиус) кольца с номером ring (0 — внешнее)."""
        return ring_bounds_for(self.radius, self.ring_count, ring)

    def ring_angle_step(self, ring):
        count = self._ring_item_count(ring)
        return 360 / count if count else 0

    def _ring_item_count(self, ring):
        """Число смайликов в конкретном кольце (последнее может быть неполным)."""
        total = len(self.emojis)
        per_ring = self.emojis_per_ring
        start = ring * per_ring
        return max(0, min(per_ring, total - start))

    def _ring_of(self, index):
        return index // self.emojis_per_ring if self.emojis_per_ring else 0

    def set_emojis(self, emojis):
        """Применяет новый список смайликов (вызывается после сохранения в редакторе)."""
        self.emojis = list(emojis)
        self.hovered_index = -1
        if self.isVisible():
            self.show_centered()

    def set_style(self, style):
        """Переключает вид колеса."""
        if style not in STYLES:
            return
        if style == self.style:
            return
        self.style = style
        self.update()

    # --- МЕТОД ПОЯВЛЕНИЯ ПО ЦЕНТРУ ---
    def show_centered(self):
        # Экран берём под курсором, иначе на мультимониторной системе меню
        # появится на мониторе, который начинается в координатах (0, 0)
        screen = QGuiApplication.screenAt(QCursor.pos()) or self.screen()
        screen_rect = screen.geometry()

        # Меню увеличиваем, но не позволяем вылезти за пределы экрана
        size = min(
            MENU_SIZE,
            int(screen_rect.width() * SCREEN_FILL_RATIO),
            int(screen_rect.height() * SCREEN_FILL_RATIO),
        )
        size = max(size, MIN_MENU_SIZE)
        if self.width() != size:
            self.resize(size, size)

        # Центр экрана в глобальных координатах (с учётом смещения монитора)
        center_x = screen_rect.x() + screen_rect.width() / 2
        center_y = screen_rect.y() + screen_rect.height() / 2

        # Перемещаем окно (вычитаем половину окна, чтобы центр окна совпал с центром экрана)
        self.move(int(center_x - self.width() / 2), int(center_y - self.height() / 2))
        self.hovered_index = -1

        # Запуск анимации
        self.fade_anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.fade_anim.start()

    def hide_menu(self):
        self.hovered_index = -1
        self.hide()

    def get_slice_index(self, pos):
        if not self.emojis:
            return -1

        center_x, center_y = self.width() / 2, self.height() / 2
        dx = pos.x() - center_x
        dy = pos.y() - center_y

        distance = math.hypot(dx, dy)

        # Ищем кольцо, в полосу которого попал курсор
        ring = None
        for candidate in range(self.ring_count):
            inner, outer = self.ring_bounds(candidate)
            if inner <= distance <= outer:
                ring = candidate
                break

        if ring is None:
            return -1

        angle = math.degrees(math.atan2(dy, dx)) + 90
        if angle < 0:
            angle += 360

        step = self.ring_angle_step(ring)
        local = int((angle + step / 2) // step) % self._ring_item_count(ring)
        return ring * self.emojis_per_ring + local

    def mouseMoveEvent(self, event):
        index = self.get_slice_index(event.position())
        if index != self.hovered_index:
            self.hovered_index = index
            self.update()

    def _ring_brush(self, style, center_x, center_y):
        """Кисть подложки: градиент, если он задан в стиле, иначе сплошной цвет."""
        r, g, b, a = style["ring"]
        gradient_spec = style.get("ring_gradient")
        if not gradient_spec:
            return QColor(r, g, b, a)

        gradients = {
            # Космос: от насыщенного фиолетового к почти чёрному
            "space": ((0.30, 0.30, 0.95, 0.92), (r, g, b, a)),
            # Мили: от светло-розового к насыщенному розовому
            "furry": ((0.75, 0.45, 0.62, 0.78), (r, g, b, a)),
        }
        spec = gradients.get(gradient_spec)
        if spec is None:
            return QColor(r, g, b, a)

        start, end = spec
        gradient = QRadialGradient(QPointF(center_x, center_y), self.radius)
        gradient.setColorAt(0.0, QColor(*(int(v * 255) for v in start)))

        # Полупрозрачность сохраняем от базового цвета стиля
        er, eg, eb, ea = (int(v * 255) for v in end)
        gradient.setColorAt(1.0, QColor(er, eg, eb, ea if ea <= 255 else a))
        return QBrush(gradient)

    def _paint_background_image(self, painter, center_x, center_y):
        """Своя картинка пользователя: обрезана кругом и затемнена, идёт под кольцом."""
        pixmap = self._background_pixmap()
        if pixmap is None or pixmap.isNull():
            return

        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(center_x, center_y), self.radius, self.radius)
        painter.setClipPath(clip)
        painter.setOpacity(0.45)
        size = int(self.radius * 2)
        painter.drawPixmap(
            int(center_x - self.radius), int(center_y - self.radius), size, size,
            pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation),
        )
        painter.restore()
        painter.setOpacity(1.0)

    def _scene_layers(self, style):
        """Неподвижные слои кадра: подложка целиком и подписи.

        При наведении меняется только подсветка одного сектора (0.1 мс), а всё
        остальное — картинка пользователя, кольца, декорации и подписи — остаётся
        прежним. Поэтому они один раз рисуются в две картинки и дальше просто
        копируются: полная перерисовка кадра стоила 9.6 мс, копирование — 0.7 мс.
        """
        if self._scene_layers_cache is not None:
            return self._scene_layers_cache

        data = self._paint_cache()
        center_x, center_y = self.width() / 2, self.height() / 2
        size = self.width(), self.height()

        # Подложка: картинка пользователя, кольца и декорации по обе стороны от кольца
        scene = QPixmap(*size)
        scene.fill(Qt.GlobalColor.transparent)
        painter = QPainter(scene)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        self._paint_background_image(painter, center_x, center_y)
        self._draw_decorations(painter, style, on_top=False)

        painter.setBrush(self._ring_brush(style, center_x, center_y))
        # «Стикерная» рамка: толщину берём от размера окна, иначе на большом
        # экране линия получится тонкой
        if style.get("outline"):
            outer_color, width_ratio = style["outline"]
            pen = QPen(QColor(*outer_color), max(2.0, self.radius * width_ratio))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
        painter.drawPath(data["ring_path"])
        painter.setPen(Qt.PenStyle.NoPen)

        # Декорации в полосе кольца рисуем поверх подложки, иначе полупрозрачное
        # кольцо их смазывает и звёзды почти не видны
        self._draw_decorations(painter, style, on_top=True)
        painter.end()

        # Подписи отдельным слоем: подсветка рисуется между слоями и не должна
        # тонировать текст
        labels = None
        if data["labels"]:
            labels = QPixmap(*size)
            labels.fill(Qt.GlobalColor.transparent)
            painter = QPainter(labels)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor(*style["label"]))
            for i, (emoji, x, y, font, squeeze, width, height) in enumerate(data["labels"]):
                painter.setFont(font)
                # Клип по своему сектору: подпись не наедет на соседей и не вылезет из кольца
                painter.save()
                painter.setClipPath(data["sector_paths"][i])
                painter.translate(x, y)
                painter.scale(squeeze, 1.0)
                painter.drawText(QRectF(-width / 2, -height / 2, width, height),
                                 Qt.AlignmentFlag.AlignCenter, emoji)
                painter.restore()
            painter.end()

        self._scene_layers_cache = (scene, labels)
        return self._scene_layers_cache

    def _draw_decorations(self, painter, style, on_top):
        """Рисует декорации: on_top=True — только попавшие в полосу кольца."""
        inner, outer = self.inner_radius, self.radius
        center_x, center_y = self.width() / 2, self.height() / 2

        for kind, x, y, size, alpha, rotation in self._paint_cache()["decorations"]:
            distance = math.hypot(x - center_x, y - center_y)
            in_ring = inner <= distance <= outer
            # Звёзды в полосе кольца рисуем поверх подложки, остальные — под ней
            if in_ring != on_top:
                continue

            painter.save()
            painter.translate(x, y)
            # Наклон фигуры: без него повторяющиеся элементы выглядят штампом
            if rotation:
                painter.rotate(rotation)
            painter.setPen(Qt.PenStyle.NoPen)

            if kind == "star":
                painter.setBrush(QColor(255, 250, 220, alpha))
                painter.drawPath(_star_path(size))
            elif kind == "sparkle":
                painter.setBrush(QColor(255, 255, 255, alpha))
                painter.drawPath(_sparkle_path(size))
            elif kind == "heart":
                painter.setBrush(QColor(*style.get("accent", (255, 64, 150)), alpha))
                painter.drawPath(_heart_path(size / 1.2))
            elif kind == "paw":
                painter.setBrush(QColor(*style.get("accent", (255, 64, 150)), alpha))
                painter.drawPath(_paw_path(size / 2.2))

            painter.restore()

    def _background_pixmap(self):
        """Своя картинка background.png рядом со скриптом (если пользователь её положил)."""
        if self._background is None and self._background_loaded is False:
            self._background_loaded = True
            if os.path.exists(BACKGROUND_PATH):
                pixmap = QPixmap(BACKGROUND_PATH)
                self._background = pixmap if not pixmap.isNull() else None
        return self._background

    def _ellipse_path(self, center_x, center_y, radius):
        # Дробные координаты: int() сдвигал бы границу клипа относительно расчётных радиусов
        path = QPainterPath()
        path.addEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))
        return path

    def _sector_path(self, index, center_x, center_y):
        """Сектор кольца, в котором лежит смайлик index."""
        ring = self._ring_of(index)
        local = index - ring * self.emojis_per_ring
        inner_radius, outer_radius = self.ring_bounds(ring)
        count = self._ring_item_count(ring)

        # Кольцо с единственным смайликом занимает всё кольцо целиком
        if count <= 1:
            return self._ellipse_path(center_x, center_y, outer_radius).subtracted(
                self._ellipse_path(center_x, center_y, inner_radius)
            )

        step = 360 / count
        center_angle = 90 - (local * step)

        # Кусок пирога по внешнему радиусу кольца
        pie_path = QPainterPath()
        pie_path.moveTo(center_x, center_y)
        pie_path.arcTo(
            QRectF(center_x - outer_radius, center_y - outer_radius, outer_radius * 2, outer_radius * 2),
            center_angle - (step / 2),
            step
        )
        pie_path.closeSubpath()

        # Вычитаем круг внутреннего радиуса = получаем сектор кольца
        return pie_path.subtracted(self._ellipse_path(center_x, center_y, inner_radius))

    def _fitted_font(self, text, max_width, base_size):
        """Подбирает кегль так, чтобы подпись влезла в сектор по ширине."""
        font_size, squeeze = fit_label_font(text, max_width, base_size)
        return QFont("Arial", font_size, QFont.Weight.Bold), squeeze

    def _label_slot(self, ring):
        """Радиус подписей, габариты слота и толщина кольца (для расчёта кегля)."""
        return label_slot_for(self.radius, self.ring_count, ring,
                              self._ring_item_count(ring))

    def _build_paint_cache(self):
        """Считает всё, что зависит только от размера окна и списка смайликов."""
        center_x, center_y = self.width() / 2, self.height() / 2

        # Подложка: кольца с дыркой посередине и зазорами между ними.
        # Собираем одни только границы колец и полагаемся на правило чётности:
        # на пути «внутрь» число пересечённых окружностей чередует заливку, поэтому
        # кольца закрашиваются, а зазоры и середина остаются пустыми.
        # Отдельно inner_radius добавлять нельзя: он равен нижней границе последнего
        # кольца лишь приблизительно, а лишняя окружность сломала бы чередование.
        # Путь при этом остаётся «плоским» (~80 элементов вместо 1518 после subtracted()),
        # и обводка по нему в разы дешевле — на 3 кольцах 13.8 мс против 3.0 мс
        ring_path = QPainterPath()
        ring_path.setFillRule(Qt.FillRule.OddEvenFill)
        radii = set()
        for ring in range(self.ring_count):
            radii.update(self.ring_bounds(ring))
        for radius in sorted(radii):
            ring_path.addEllipse(QRectF(center_x - radius, center_y - radius,
                                        radius * 2, radius * 2))

        # Пути секторов нужны все: один как подсветка, остальные как клип для подписей
        sector_paths = [self._sector_path(i, center_x, center_y) for i in range(len(self.emojis))]

        labels = []
        for i, emoji in enumerate(self.emojis):
            ring = self._ring_of(i)
            local = i - ring * self.emojis_per_ring
            text_radius, max_width, max_height, thickness = self._label_slot(ring)

            angle = math.radians(local * self.ring_angle_step(ring) - 90)
            font, squeeze = self._fitted_font(emoji, max_width, thickness)
            labels.append((
                emoji,
                center_x + math.cos(angle) * text_radius,
                center_y + math.sin(angle) * text_radius,
                font,
                squeeze,
                max_width,
                max_height,
            ))

        return {
            "ring_path": ring_path,
            "sector_paths": sector_paths,
            "labels": labels,
            "decorations": self._build_decorations(center_x, center_y),
        }

    def _build_decorations(self, center_x, center_y):
        """Точки для декоративных элементов выбранного стиля (звёзды, лапки)."""
        style = STYLES.get(self.style, STYLES[DEFAULT_STYLE])
        kind = style.get("decoration")
        if kind is None:
            return []

        # Фиксированный seed: узор не должен прыгать при каждой перерисовке
        rng = random.Random(20260926)
        items = []
        inner = self.inner_radius

        if kind == "stars":
            # Звёзды двух видов: мелкая пыль по кольцу и несколько крупных
            for _ in range(70):
                angle = rng.uniform(0, 2 * math.pi)
                radius = rng.uniform(inner * 0.35, self.radius * 0.97)
                size = rng.uniform(2.0, 5.0)
                alpha = rng.randint(70, 190)
                items.append(("star", center_x + math.cos(angle) * radius,
                              center_y + math.sin(angle) * radius, size, alpha,
                              rng.uniform(0, 72)))
            for _ in range(6):
                angle = rng.uniform(0, 2 * math.pi)
                radius = rng.uniform(inner * 1.5, self.radius * 0.9)
                size = rng.uniform(7.0, 12.0)
                alpha = rng.randint(180, 240)
                items.append(("star", center_x + math.cos(angle) * radius,
                              center_y + math.sin(angle) * radius, size, alpha,
                              rng.uniform(0, 40)))
        elif kind == "paws":
            ring_width = self.radius - inner

            # Лапки-следы идут по кругу между секторами, как цепочка следов
            step = 360 / max(1, len(self.emojis))
            for i in range(len(self.emojis)):
                angle = math.radians(i * step + step / 2)
                radius = inner + ring_width * 0.5
                size = max(7.0, ring_width * 0.062)
                # Чередуем наклон и объём, чтобы следы не выглядели штампом
                tilt = 14 if i % 2 == 0 else -14
                items.append(("paw", center_x + math.cos(angle) * radius,
                              center_y + math.sin(angle) * radius, size, 105, tilt))

            # Сердечки и искорки рассыпаны по полосе кольца
            for _ in range(16):
                angle = rng.uniform(0, 2 * math.pi)
                radius = rng.uniform(inner * 1.02, self.radius * 0.94)
                size = rng.uniform(4.0, 9.0)
                items.append(("heart", center_x + math.cos(angle) * radius,
                              center_y + math.sin(angle) * radius, size,
                              rng.randint(70, 150), rng.uniform(-22, 22)))
            for _ in range(14):
                angle = rng.uniform(0, 2 * math.pi)
                radius = rng.uniform(inner * 1.02, self.radius * 0.95)
                size = rng.uniform(3.5, 7.0)
                items.append(("sparkle", center_x + math.cos(angle) * radius,
                              center_y + math.sin(angle) * radius, size,
                              rng.randint(110, 210), rng.uniform(-15, 15)))

            # Лапки, будто кто-то оставил следы у внутреннего края кольца
            for dx in (-0.60, 0.60):
                items.append(("paw", center_x + dx * inner, center_y - inner * 0.60,
                              max(4.5, inner * 0.11), 170, -dx * 12))
        return items

    def _paint_cache(self):
        # Ключ включает размер окна, список смайликов и стиль: при их смене кэш пересчитывается
        key = (self.width(), self.height(), tuple(self.emojis), self.style)
        if self._paint_key != key:
            self._paint_data = self._build_paint_cache()
            self._paint_key = key
            # Слои кадра зависят от того же ключа — сбрасываем и их
            self._scene_layers_cache = None
        return self._paint_data

    def paintEvent(self, event):
        data = self._paint_cache()
        style = STYLES.get(self.style, STYLES[DEFAULT_STYLE])

        # Неподвижная часть кадра берётся готовыми слоями: при наведении меняется
        # только подсветка, поэтому перерисовывать кольцо и подписи каждый раз незачем
        scene, labels = self._scene_layers(style)

        painter = QPainter(self)
        painter.drawPixmap(0, 0, scene)

        # Без смайликов подсветки и подписей нет
        if not data["labels"]:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Подсветка сектора: проверка границ обязательна, список мог стать короче,
        # а исключение внутри paintEvent уронит всё приложение
        if 0 <= self.hovered_index < len(data["sector_paths"]):
            r, g, b, a = style["highlight"]
            painter.setBrush(QColor(r, g, b, a))
            painter.drawPath(data["sector_paths"][self.hovered_index])

        if labels is not None:
            painter.drawPixmap(0, 0, labels)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.hide_menu()
        elif event.button() == Qt.MouseButton.LeftButton:
            index = self.get_slice_index(event.position())

            # Сначала прячем окно в любом случае (даже если клик мимо)
            self.hide_menu()

            # Если клик был по сектору со смайликом - вставляем его
            if index != -1:
                self.paste_emoji(self.emojis[index])

    def paste_emoji(self, text):
        previous = pyperclip.paste()
        pyperclip.copy(text)

        # Ждём таймером, а не time.sleep: пауза в GUI-потоке заморозила бы окно
        QTimer.singleShot(PASTE_DELAY_MS, lambda: keyboard.send('ctrl+v'))
        QTimer.singleShot(CLIPBOARD_RESTORE_MS, lambda: self._restore_clipboard(text, previous))

    def _restore_clipboard(self, copied, previous):
        # Возвращаем буфер обмена, только если там всё ещё наш смайлик и раньше
        # был текст: пустое значение может означать картинку, её затирать нельзя
        if not previous:
            return
        try:
            if pyperclip.paste() == copied:
                pyperclip.copy(previous)
        except pyperclip.PyperclipException:
            pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Иконка на уровне приложения: она же попадает в панель задач и в список окон
    icon = load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    emojis = load_emojis()
    settings = load_settings()
    if not os.path.exists(EMOJIS_PATH):
        # Создаём файл при первом запуске, чтобы его было видно и можно было править вручную
        error = save_emojis(emojis)
        if error:
            print(f"Не удалось создать {EMOJIS_PATH}: {error}")
    if not os.path.exists(SETTINGS_PATH):
        error = save_settings(settings)
        if error:
            print(f"Не удалось создать {SETTINGS_PATH}: {error}")

    menu = RadialMenu(emojis, style=settings["style"])
    editor = EmojiEditor(emojis, style=settings["style"])
    listener = HotkeyListener()
    hotkeys = []

    def open_editor():
        # Показываем редактор с текущим списком меню и убираем меню, чтобы не мешало
        menu.hide_menu()
        editor.show_editor(menu.emojis, menu.style)

    def quit_app():
        # Снимаем хуки до остановки цикла событий: иначе библиотека keyboard
        # останется висеть в процессе
        for hotkey in hotkeys:
            keyboard.remove_hotkey(hotkey)
        hotkeys.clear()
        app.quit()

    listener.triggered.connect(menu.show_centered)
    listener.dismissed.connect(menu.hide_menu)
    listener.edit_requested.connect(open_editor)
    editor.saved.connect(menu.set_emojis)
    editor.exit_requested.connect(quit_app)
    # Вид применяется сразу при выборе в списке
    editor.style_changed.connect(menu.set_style)

    try:
        # Назначаем глобальные горячие клавиши
        hotkeys.append(keyboard.add_hotkey('ctrl+shift+e', listener.triggered.emit))
        hotkeys.append(keyboard.add_hotkey('ctrl+shift+r', listener.edit_requested.emit))
        # Окно не берёт фокус, поэтому Esc ловим тоже глобально
        hotkeys.append(keyboard.add_hotkey('esc', listener.dismissed.emit))

        print("Программа запущена!")
        print("  Ctrl+Shift+E — открыть меню.")
        print("  Ctrl+Shift+R — редактор списка смайликов и вида колеса.")
        print("  Esc или правый клик — закрыть меню.")
        print(f"  Список хранится в {EMOJIS_PATH}")
        print(f"  Вид колеса хранится в {SETTINGS_PATH}")
        sys.exit(app.exec())
    finally:
        # Снимаем хуки, иначе библиотека keyboard останется висеть в процессе
        for hotkey in hotkeys:
            keyboard.remove_hotkey(hotkey)
