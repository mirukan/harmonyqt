# Copyright 2018 miruka
# This file is part of harmonyqt, licensed under GPLv3.

from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import (
    QApplication, QDesktopWidget, QMainWindow, QTabWidget, QWidget
)

HooksType = Dict[str, Callable[["MainWindow"], None]]

HOOKS_INIT_1_START:        HooksType = {}
HOOKS_INIT_2_BEFORE_LOGIN: HooksType = {}
HOOKS_INIT_3_END:          HooksType = {}

# pylint: disable=wrong-import-position
from . import (
    __about__, app, error_handler, homepage, theming, toolbar, usertree
)
from .chat import ChatDock
from .dock import Dock


class App(QApplication):
    def __init__(self, argv: Optional[List[str]] = None) -> None:
        super().__init__(argv or [])
        # if not self.styleSheet:  # user can load one with --stylesheet
            # self.
            # pass

        self.setApplicationName(__about__.__pkg_name__)
        self.setApplicationVersion(__about__.__version__)

        self.last_focused_dock:      Optional[Dock]     = None
        self.last_focused_chat_dock: Optional[ChatDock] = None
        self.focusChanged.connect(self.on_focus_change)


    def on_focus_change(self, _: QWidget, new: QWidget) -> None:
        while not isinstance(new, Dock):
            if new is None:
                return
            new = new.parent()

        self.last_focused_dock = new

        if isinstance(new, ChatDock):
            self.last_focused_chat_dock = new


    def get_focused(self, condition: Optional[Callable[[QWidget], bool]] = None
                   ) -> Optional[Dock]:
        widget = self.focusWidget()

        if not condition:
            return widget

        while widget is not None:
            if condition(widget):
                return widget
            widget = widget.parent()

        return None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.title_bars_shown: bool = False
        self.normal_close:     bool = False


    def construct(self) -> None:
        # pylint: disable=attribute-defined-outside-init
        # Can't define all that __init__ instead.
        # The UI elements need _MAIN_WINDOW to be set, see run() in __init__.

        # Avoid import matrix_client stuff before we can init a QApplication
        from .accounts import AccountManager
        from .event_logger import EventLogger
        from .events import EventManager
        from .shortcuts import Shortcut, ShortcutManager


        for func in HOOKS_INIT_1_START.values():
            func(self)

        # Setup error console:

        self.error_dock = Dock("Error console", self, can_hide_title_bar=False)
        self.error_dock.hide()
        self.error_dock.setWidget(error_handler.console.Console())


        # Setup appearance:

        self.setWindowTitle("Harmony")
        screen = QDesktopWidget().screenGeometry()
        self.resize(min(screen.width(), 1152), min(screen.height(), 768))

        # self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.9)

        self.theme = theming.Theme("glass")
        self.icons = theming.Icons("flat_white")
        self.setStyleSheet(self.theme.style("interface"))


        # Setup main classes and event listeners:

        self.event_logger: EventLogger     = EventLogger()
        self.accounts:     AccountManager  = AccountManager()
        self.events:       EventManager    = EventManager()
        self.shortcuts:    ShortcutManager = ShortcutManager()

        self.event_logger.start()

        self.events.signals.left_room.connect(self.remove_chat_dock)
        self.events.signals.room_rename.connect(self.update_chat_dock_name)
        # Triggered by room renames that happen when account changes
        # self.events.signal.account_change.connect(self.update_chat_dock_name)


        # Setup main UI parts:

        self.setDockNestingEnabled(True)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)

        self.tree_dock = Dock("Accounts / Rooms", self)
        self.tree_dock.setWidget(usertree.UserTree())
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tree_dock)

        self.actions_dock = Dock("Actions", self)
        self.actions_dock.setWidget(toolbar.ActionsBar())
        self.splitDockWidget(self.tree_dock, self.actions_dock, Qt.Vertical)

        self.home_dock = Dock("Home", self)
        self.home_dock.setWidget(homepage.HomePage())
        self.addDockWidget(Qt.RightDockWidgetArea, self.home_dock)

        # {(user_id, room_id): dock}
        self.visible_chat_docks: Dict[Tuple[str, str], ChatDock] = {}

        def on_activation() -> None:
            try:
                app().last_focused_chat_dock.focus()
            except AttributeError:
                pass

        self.shortcuts.add(Shortcut(
            name          = "Focus last chat",
            on_activation = on_activation,
            bindings      = ["A-c"],
            autorepeat    = False
        ))

        self.show_dock_title_bars(False)

        # Run:

        self.show()

        for func in HOOKS_INIT_2_BEFORE_LOGIN.values():
            func(self)

        try:
            self.accounts.login_using_config()
        except FileNotFoundError:
            pass

        for func in HOOKS_INIT_3_END.values():
            func(self)


    def show_dock_title_bars(self, show: Optional[bool] = None) -> None:
        if show is None:
            show = not self.title_bars_shown

        docks = (self.tree_dock, self.actions_dock, self.home_dock,
                 self.error_dock, *self.visible_chat_docks.values())

        for dock in docks:
            dock.show_title_bar(show)

        self.title_bars_shown = show


    def show_error_dock(self) -> None:
        if self.error_dock.isVisible():
            return

        self.error_dock.widget().display.apply_style()

        try:
            tab_with = app().last_focused_chat_dock
            if not tab_with or not tab_with.isVisible():
                tab_with = self.home_dock
        except AttributeError:
            self.addDockWidget(Qt.RightDockWidgetArea, self.error_dock)
        else:
            self.tabifyDockWidget(tab_with, self.error_dock)


    def new_chat_dock(self,
                      user_id:            str,
                      room_id:            str,
                      previously_focused: ChatDock,
                      in_new:             str            = "",
                      split_orientation:  Qt.Orientation = Qt.Horizontal,
                     ) -> ChatDock:
        assert in_new in (None, "", "tab", "split")

        prev_is_in_tab = bool(self.tabifiedDockWidgets(previously_focused))
        dock = ChatDock(user_id, room_id, self)

        if not previously_focused.isVisible():
            self.addDockWidget(
                previously_focused.current_area or Qt.RightDockWidgetArea,
                dock,
                split_orientation
            )

        if in_new == "split" and prev_is_in_tab:
            area = None if previously_focused.isFloating() else \
                   previously_focused.current_area
            area = area or Qt.RightDockWidgetArea

            self.addDockWidget(area, dock, split_orientation)

        elif in_new == "split":
            self.splitDockWidget(previously_focused, dock, split_orientation)

        else:
            self.tabifyDockWidget(previously_focused, dock)

        return dock


    def go_to_chat_dock(self, user_id: str, room_id: str, in_new: str = "",
                        split_orientation: Qt.Orientation = Qt.Horizontal
                       ) -> None:

        dock = self.visible_chat_docks.get((user_id, room_id))
        if dock:
            dock.focus()
            return

        dock = app().last_focused_chat_dock
        if not dock or not dock.isVisible():
            dock = self.home_dock

        if in_new:
            dock = self.new_chat_dock(user_id, room_id, dock, in_new,
                                      split_orientation)
        elif isinstance(dock, ChatDock):
            dock.change_room(user_id, room_id)
        else:
            self.home_dock.hide()
            dock = self.new_chat_dock(user_id, room_id, dock, in_new,
                                      split_orientation)

        dock.focus()


    def remove_chat_dock(self, user_id: str, room_id: str) -> None:
        dock = self.visible_chat_docks.get((user_id, room_id))
        if dock:
            dock.hide()


    def update_chat_dock_name(self, user_id: str, room_id: str) -> None:
        dock = self.visible_chat_docks.get((user_id, room_id))
        if dock:
            dock.autoset_title()


    def closeEvent(self, event: QCloseEvent) -> None:
        self.normal_close = True
        super().closeEvent(event)
