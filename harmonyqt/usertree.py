# Copyright 2018 miruka
# This file is part of harmonyqt, licensed under GPLv3.

from typing import Dict, List

from matrix_client.room import Room
# pylint: disable=no-name-in-module
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QIcon, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import (
    QAction, QHeaderView, QSizePolicy, QTreeWidget, QTreeWidgetItem
)

from . import __about__, actions, app, main_window
from .dialogs import AcceptRoomInvite
from .matrix import HMatrixClient
from .menu import Menu

# pylint: disable=invalid-name


class UserTree(QTreeWidget):
    def __init__(self) -> None:
        super().__init__()
        self.accounts:   Dict[str, "AccountRow"] = {}
        self.blank_rows: List["BlankRow"]        = []

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
        self.setColumnCount(2)  # avatar/name; unread msg num/invite indicator
        self.setUniformRowHeights(True)
        self.setAnimated(True)
        self.setAutoExpandDelay(500)
        self.setHeaderHidden(True)  # TODO: customizable cols
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setExpandsOnDoubleClick(False)  # Handled by signals/events

        self.header().setMinimumSectionSize(1)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_context_menu_request)

        ev_sig = main_window().events.signal
        ev_sig.new_account.connect(self.add_account)
        ev_sig.account_gone.connect(self.del_account)
        ev_sig.new_room.connect(self.on_add_room)
        ev_sig.new_invite.connect(self.on_add_room)
        ev_sig.room_rename.connect(self.on_rename_room)
        ev_sig.left_room.connect(self.on_left_room)
        ev_sig.account_change.connect(self.on_account_change)

        self.actions: List[QAction] = []
        self.init_actions()


    def init_actions(self) -> None:
        win = main_window()
        self.actions = [
            actions.AddAccount(win),
            actions.NewChat(win),
            actions.SetStatus(win),
        ]


    def get_context_menu_actions(self) -> List[QAction]:
        return self.actions


    def add_account(self, user_id: str) -> None:
        if user_id in self.accounts:
            return

        self.accounts[user_id] = AccountRow(self, user_id)

        root = self.invisibleRootItem()
        root.sortChildren(0, Qt.AscendingOrder)

        for row in self.blank_rows:
            root.removeChild(row)

        for row in self.accounts.values():
            index = root.indexOfChild(row)
            if index > 0:
                blank = BlankRow()
                root.insertChild(index, blank)
                self.blank_rows.append(blank)


    def del_account(self, user_id: str) -> None:
        if user_id not in self.accounts:
            return

        to_del: AccountRow = self.accounts[user_id]
        root               = self.invisibleRootItem()

        for row in self.blank_rows:
            if root.indexOfChild(row) == root.indexOfChild(to_del) - 1:
                root.removeChild(row)

        root.removeChild(to_del)
        del self.accounts[user_id]

        first = root.child(0)
        if isinstance(first, BlankRow):
            root.removeChild(first)


    def on_context_menu_request(self, position: QPoint) -> None:
        selected = [self.itemFromIndex(s) for s in self.selectedIndexes()
                    if s.column() == 0 and not isinstance(s, BlankRow)]

        acts: List[QAction] = []
        for row in selected:
            if hasattr(row, "get_context_menu_actions"):
                acts += row.get_context_menu_actions()

        if not selected:
            acts += self.get_context_menu_actions()

        menu = Menu(self, acts)
        menu.exec_if_not_empty(self.mapToGlobal(position))


    def on_add_room(self, user_id: str, room_id: str,
                    invite_by: str = "", display_name: str = "",
                    name:      str = "", alias:        str = "") -> None:
        print("add", locals())
        self.accounts[user_id].add_room(room_id,
                                        invite_by, display_name, name, alias)


    def on_rename_room(self, user_id: str, room_id: str) -> None:
        print("rename", locals())
        rooms = self.accounts[user_id].rooms
        if room_id in rooms:
            rooms[room_id].update_ui()


    def on_left_room(self, user_id: str, room_id: str) -> None:
        self.accounts[user_id].del_room(room_id)


    def on_account_change(self, user_id: str, _: str,
                          new_display_name: str, new_avatar_url: str) -> None:
        print("accchange", locals())
        self.accounts[user_id].update_ui(new_display_name, new_avatar_url)


    def really_clear_selection(self) -> None:
        self.clearSelection()
        self.setCurrentItem(None)


    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):  # Enter = keypad
            self.activate_row(self.currentItem(), event.modifiers())

        elif event.key() == Qt.Key_Escape:
            self.really_clear_selection()


    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)

        btn  = event.button()
        mods = app().keyboardModifiers()

        if btn == Qt.RightButton or \
           btn == Qt.LeftButton and mods != Qt.NoModifier:
            return

        clicked_row = self.itemAt(event.pos())
        self.activate_row(clicked_row, mods, btn == Qt.MiddleButton)

        if not clicked_row:
            self.really_clear_selection()


    def activate_row(self,
                     row:             QTreeWidgetItem,
                     kb_modifiers:    Qt.KeyboardModifiers,
                     middle_click: bool = False) -> None:
        if hasattr(row, "on_activation"):
            row.on_activation(kb_modifiers, middle_click)
            self.really_clear_selection()


class BlankRow(QTreeWidgetItem):
    def __init__(self) -> None:
        # Don't take a parent or sorting won't work correctly`
        super().__init__()
        self.setFlags(Qt.NoItemFlags | Qt.ItemNeverHasChildren)


class AccountRow(QTreeWidgetItem):
    def __init__(self, parent: UserTree, user_id: str) -> None:
        super().__init__(parent)
        self.user_tree: UserTree         = parent
        self.client:    HMatrixClient    = main_window().accounts[user_id]
        self.rooms:     Dict[str, RoomRow] = {}

        self.auto_expanded_once: bool = False
        self.update_ui()

        self.actions: List[QAction] = []
        self.init_actions()


    def init_actions(self) -> None:
        self.actions = [
            actions.NewChat(self.user_tree, self.client.user_id),
            actions.DelAccount(self.user_tree, self.client.user_id),
        ]


    def get_context_menu_actions(self) -> List[QAction]:
        return self.actions


    def update_ui(self, new_display_name: str = "", _: str = "") -> None:
        self.setText(0,
                     new_display_name or self.client.h_user.get_display_name())
        self.setToolTip(0, self.client.user_id)


    def on_activation(self, *_) -> None:
        expanded = self.isExpanded()
        self.setExpanded(not expanded)


    def add_room(self, room_id: str,
                 invite_by: str = "", display_name: str = "",
                 name:      str = "", alias:        str = "") -> None:
        if room_id in self.rooms:
            self.rooms[room_id].update_ui()
            return

        self.rooms[room_id] = RoomRow(self, room_id,
                                      invite_by, display_name, name, alias)
        self.sortChildren(0, Qt.AscendingOrder)

        if not self.auto_expanded_once:
            self.setExpanded(True)  # TODO: unless user collapsed manually
            self.auto_expanded_once = True


    def del_room(self, room_id: str) -> None:
        if room_id in self.rooms:
            self.removeChild(self.rooms[room_id])
            del self.rooms[room_id]


class RoomRow(QTreeWidgetItem):
    def __init__(self, parent: AccountRow, room_id: str,
                 invite_by: str = "", display_name: str = "",
                 name:      str = "", alias:        str = "") -> None:
        super().__init__(parent)
        self.setFlags(self.flags() | Qt.ItemNeverHasChildren)

        self.account_row: AccountRow = parent
        self.invite_by:   str        = invite_by

        if invite_by:
            self.room: Room           = Room(parent.client, room_id)
            self.room.name            = self.room.name            or name
            self.room.canonical_alias = self.room.canonical_alias or alias
        else:
            self.room: Room = parent.client.rooms[room_id]

        self.setTextAlignment(1, Qt.AlignRight)  # msg unread/invite indicator
        self.update_ui(display_name)

        self.actions_invite: List[QAction] = []
        self.actions_normal: List[QAction] = []
        self.init_actions()


    def init_actions(self) -> None:
        tree    = self.account_row.user_tree
        user_id = self.account_row.client.user_id

        self.actions_invite = [
            actions.AcceptInvite(tree, self.room, self.on_invite_accept),
            actions.DeclineInvite(tree, self.room, self.on_leave),
        ]
        self.actions_normal = [
            actions.InviteToRoom(tree, self.room, user_id),
            actions.LeaveRoom(tree, self.room, self.on_leave),
        ]


    def get_context_menu_actions(self) -> List[QAction]:
        return self.actions_invite if self.invite_by else self.actions_normal


    def update_ui(self, invite_display_name: str = "") -> None:
        # The later crashes for rooms we're invited to but not joined
        dispname = invite_display_name or self.room.display_name
        self.setText(0, dispname)

        tooltips = self.room.aliases + [self.room.room_id]

        if self.invite_by:
            self.setIcon(1, main_window().icons.icon("indicator_invite"))
            tooltips.insert(0, f"Pending invitation from {self.invite_by}")
        else:
            self.setIcon(1, QIcon())

        tooltips.append(
            "\nMiddle click to open in a new tab\n"
            "Shift + Middle click to open in a horizontal split\n"
            "Ctrl + Middle click to open in a vertical split"
        )

        tooltips = "\n".join(tooltips)
        for col in range(self.columnCount()):
            self.setToolTip(col, tooltips)


    def on_activation(self,
                      kb_modifiers:    Qt.KeyboardModifiers,
                      middle_click: bool = False) -> None:
        user_id = self.account_row.client.user_id
        room_id = self.room.room_id

        if self.invite_by:
            dialog = AcceptRoomInvite(
                main_window(), self.room, self.text(0), self.invite_by,
            )
            dialog.exec()

            if dialog.clickedButton() is dialog.yes:
                self.on_invite_accept()
            elif dialog.clickedButton() is dialog.no:
                self.on_leave()
                return
            else:
                return

        in_new = ""
        orient = Qt.Horizontal
        if middle_click and kb_modifiers == Qt.ShiftModifier:
            in_new = "split"
        elif middle_click and kb_modifiers == Qt.ControlModifier:
            in_new = "split"
            orient = Qt.Vertical
        elif middle_click:
            in_new = "tab"

        main_window().go_to_chat_dock(user_id, room_id,
                                      in_new=in_new, split_orientation=orient)


    def on_invite_accept(self) -> None:
        self.invite_by = ""
        self.update_ui()


    def on_leave(self) -> None:
        self.account_row.del_room(self.room.room_id)
