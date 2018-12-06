# Copyright 2018 miruka
# This file is part of harmonyqt, licensed under GPLv3.

import os
import sys
from typing import List, Optional

from matrix_client.client import MatrixClient
from matrix_client.room import Room
# pylint: disable=no-name-in-module
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QKeyEvent
from PyQt5.QtWidgets import (QApplication, QDesktopWidget, QDockWidget, QLabel,
                             QMainWindow, QTabWidget, QWidget)

from . import (ICON_PACK, STYLESHEET, __about__, accounts, chat, events,
               homepage, toolbar, usertree)
from .caches import ROOM_DISPLAY_NAMES, USER_DISPLAY_NAMES


class DockTitleBar(QLabel):
    pass


class Dock(QDockWidget):
    def __init__(self, title: str, parent: QWidget) -> None:
        super().__init__(title, parent)
        self.title_bar       = DockTitleBar(title)
        self.title_bar_shown = True
        self.setTitleBarWidget(DockTitleBar(title))


    def show_title_bar(self, show: Optional[bool] = None) -> None:
        if show is None:
            show = not self.title_bar_shown

        self.setTitleBarWidget(self.title_bar if show else QWidget())
        self.title_bar_shown = show


class HarmonyQt(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.title_bars_shown       = True
        self.alt_title_bars_toggled = False

        self.accounts = accounts.AccountManager(self)
        self.events   = events.EventManager(self)

        self.events.signal.left_room.connect(self.remove_chat_dock)

        self.setWindowTitle("Harmony")
        screen = QDesktopWidget().screenGeometry()
        self.resize(min(screen.width(), 800), min(screen.height(), 600))
        # self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.8)
        self.setStyleSheet(STYLESHEET)

        self.setDockNestingEnabled(True)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)
        # self.setTabShape(QTabWidget.Triangular)

        self.tree_dock = Dock("Accounts", self)
        self.tree_dock.setWidget(usertree.UserTree(self))
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tree_dock)

        self.home_dock = Dock("Home", self)
        self.home_dock.setWidget(homepage.HomePage())
        self.home_dock.setFeatures(
            # Make it unclosable so we can always rely on it to append tabs
            Dock.DockWidgetMovable | Dock.DockWidgetFloatable
        )
        self.addDockWidget(Qt.RightDockWidgetArea, self.home_dock)

        self.chat_docks = []

        self.actions_dock = Dock("Actions", self)
        self.actions_dock.setWidget(toolbar.ActionsBar(self))
        self.addDockWidget(
            Qt.LeftDockWidgetArea, self.actions_dock, Qt.Vertical
        )

        self.show()
        try:
            self.accounts.login_using_config()
        except FileNotFoundError:
            pass


    def show_dock_title_bars(self, show: Optional[bool] = None) -> None:
        if show is None:
            show = not self.title_bars_shown

        docks = (self.tree_dock, self.actions_dock, self.home_dock,
                 *self.chat_docks)

        for dock in docks:
            dock.show_title_bar(show)

        self.title_bars_shown = show


    def go_to_chat_dock(self, client: MatrixClient, room: Room) -> None:
        def go(dock: Dock) -> None:
            dock.show()
            dock.raise_()
            dock.widget().sendbox.setFocus()

        for dock in self.chat_docks:
            if dock.widget().room == room and dock.widget().client == client:
                go(dock)
                return

        chat_ = chat.Chat(window=self, client=client, room=room)
        dock  = Dock(f"{USER_DISPLAY_NAMES.get(client)}/"
                     f"{ROOM_DISPLAY_NAMES.get(room)}",
                     self)
        dock.setWidget(chat_)
        self.tabifyDockWidget(self.home_dock, dock)
        go(dock)
        self.chat_docks.append(dock)


    def remove_chat_dock(self, client: MatrixClient, room_id: str) -> None:
        for i, dock in enumerate(self.chat_docks):
            if dock.widget().room.room_id   == room_id and \
               dock.widget().client.user_id == client.user_id:
                dock.hide()
                del self.chat_docks[i]


    # pylint: disable=invalid-name
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.title_bars_shown and not self.alt_title_bars_toggled and \
           event.key() == Qt.Key_Alt:
            self.show_dock_title_bars(True)
            self.alt_title_bars_toggled = True


    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self.alt_title_bars_toggled and event.key() == Qt.Key_Alt:
            self.show_dock_title_bars(False)
            self.alt_title_bars_toggled = False


def run(argv: Optional[List[str]] = None) -> None:
    app = QApplication(argv or sys.argv)
    _   = HarmonyQt()

    # Make CTRL-C work
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    sys.exit(app.exec_())
