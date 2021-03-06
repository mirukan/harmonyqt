# Copyright 2018 miruka
# This file is part of harmonyqt, licensed under GPLv3.

import time
from threading import Thread
from typing import Deque, Tuple

from PyQt5.QtCore import QDateTime, Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QTextCursor, QTextLength, QTextTableFormat

from matrix_client.errors import (
    MegolmDecryptMissingKeysError, RoomEventDecryptError
)

from . import Chat
from .. import message_display
from ..message import Message


class ChatMessageDisplay(message_display.MessageDisplay):
    _add_message_request = pyqtSignal(Message)


    def __init__(self, chat: Chat) -> None:
        super().__init__()
        self.apply_style()
        self.chat: Chat = chat

        constraints = [
            QTextLength(QTextLength.FixedLength,    0),  # avatar
            QTextLength(QTextLength.VariableLength, 0),  # info/content
        ]

        self.msg_format = QTextTableFormat()
        self.msg_format.setBorder(0)
        self.msg_format.setTopMargin(self.font_height)
        self.msg_format.setColumnWidthConstraints(constraints)

        self.consecutive_msg_format = QTextTableFormat()
        self.consecutive_msg_format.setBorder(0)
        self.consecutive_msg_format.setColumnWidthConstraints(constraints)

        self.msg_after_break_format = QTextTableFormat()
        self.msg_after_break_format.setBorder(0)
        self.msg_after_break_format.setTopMargin(self.font_height * 3)
        self.msg_after_break_format.setColumnWidthConstraints(constraints)

        self.inner_info_content_format = QTextTableFormat()
        self.inner_info_content_format.setBorder(0)

        self.last_table_is_message: bool = False

        self.start_ms_since_epoch: int = \
            QDateTime.currentDateTime().toMSecsSinceEpoch()

        self.added_msgs: Deque[Message] = Deque()

        # [(msg.sender_id, msg.markdown)]
        self.received_by_local_echo: Deque[Tuple[str, str]] = Deque()

        uid, rid = self.chat.client.user_id, self.chat.room.room_id

        Message.local_echo_hooks[(type(self).__name__, uid, rid)] = \
            self.on_receive_local_echo

        Thread(target=self.autoload_history, daemon=True).start()

        self._add_message_request.connect(self._add_message)


    def on_receive_local_echo(self, msg: Message) -> None:
        if msg.room_id != self.chat.room.room_id:
            return

        msg.receiver_id = self.chat.client.user_id
        self.received_by_local_echo.append((msg.sender_id, msg.markdown))
        self._add_message_request.emit(msg)


    # Called from harmonyqt.chat.redirect_message()
    def on_receive_from_server(self, msg: Message) -> None:
        try:
            self.received_by_local_echo.remove((msg.sender_id, msg.markdown))
        except ValueError:  # not found in list/deque
            self._add_message_request.emit(msg)


    # Same as above
    def on_decrypt_error(self, err: RoomEventDecryptError) -> None:
        html = "<span class=decrypt-error>%s</span>"
        if isinstance(err.original_exception, MegolmDecryptMissingKeysError):
            html %= (
                f"Sender's device "
                f"<code>{err.event['content']['device_id']}</code> has not "
                f"sent the decryption keys to your device "
                f"<code>{self.chat.client.olm_device.device_id}</code> "
                f"for this message.<br>"
                f"Type <code>/help devices</code> for more info."
            )
        else:
            html %= str(err)

        self._add_message_request.emit(Message(
            room_id        = err.room.room_id,
            sender_id      = err.event["sender"],
            ms_since_epoch = err.event["origin_server_ts"],
            html           = html,
        ))


    @staticmethod
    def break_between(msg1: Message, msg2: Message) -> bool:
        # True if there's more than 5mn between the two messages:
        return msg1.ms_since_epoch <= msg2.ms_since_epoch - 15 * 60 * 1000


    def are_consecutive(self, msg1: Message, msg2: Message) -> bool:
        return (self.last_table_is_message and
                msg1.sender_id == msg2.sender_id and
                msg1.ms_since_epoch >= msg2.ms_since_epoch - 5 * 60 * 1000)


    def _add_message(self, msg: Message) -> None:
        distance_from_left   = self.scroller.h
        distance_from_bottom = self.scroller.vmax - self.scroller.v

        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()

        to_top       = msg.was_created_before(self.start_ms_since_epoch)
        inserted     = False
        previous_msg = next_msg = None

        if to_top:
            cursor.movePosition(QTextCursor.Start)

            i = 0
            for i, added_msg in enumerate(self.added_msgs, i):
                next_msg = self.added_msgs[i]

                if msg.was_created_before(added_msg.ms_since_epoch):
                    self.added_msgs.insert(i, msg)
                    cursor.movePosition(QTextCursor.Down, n=i)
                    inserted = True
                    break

                previous_msg = self.added_msgs[i - 1]

        if not inserted:
            if self.added_msgs:
                previous_msg = self.added_msgs[-1]
            self.added_msgs.append(msg)
            cursor.movePosition(QTextCursor.End)

        if next_msg and self.are_consecutive(msg, next_msg):
            fixer = QTextCursor(cursor)
            fixer.beginEditBlock()
            fixer.movePosition(QTextCursor.Down)

            msg_table = fixer.currentTable()
            if msg_table and msg_table.columns() > 1:
                msg_table.setFormat(self.consecutive_msg_format)
                fixer.select(QTextCursor.LineUnderCursor)
                fixer.removeSelectedText()  # remove avatar

            fixer.movePosition(QTextCursor.NextCell)
            fixer.movePosition(QTextCursor.NextBlock)

            info_msg_table = fixer.currentTable()
            if info_msg_table and info_msg_table.rows() > 1:
                info_msg_table.removeRows(0, 1)  # Remove info name/date

            fixer.endEditBlock()

        if next_msg and self.break_between(msg, next_msg):
            fixer = QTextCursor(cursor)
            fixer.beginEditBlock()
            fixer.movePosition(QTextCursor.Down)

            msg_table = fixer.currentTable()
            if msg_table:
                msg_table.setFormat(self.msg_after_break_format)

            fixer.endEditBlock()

        consecutive = previous_msg and self.are_consecutive(previous_msg, msg)
        after_break = previous_msg and self.break_between(previous_msg, msg)

        cursor.insertTable(
            1, 2,  # rows, columns
            self.msg_after_break_format if after_break else
            self.consecutive_msg_format if consecutive else
            self.msg_format
        )
        if not consecutive:
            cursor.insertHtml(msg.html_avatar)
        cursor.movePosition(QTextCursor.NextBlock)

        if consecutive:
            cursor.insertTable(1, 1, self.inner_info_content_format)
        else:
            cursor.insertTable(2, 1, self.inner_info_content_format)
            cursor.insertHtml(msg.html_info)
            cursor.movePosition(QTextCursor.NextBlock)

        cursor.insertHtml(msg.html_content)

        cursor.endEditBlock()
        self.last_table_is_message = True

        if to_top:
            self.scroller.hset(distance_from_left)\
                         .vset(self.scroller.vmax - distance_from_bottom)
        elif distance_from_bottom <= 10:
            self.scroller.go_min_left().go_bottom()


    def autoload_history(self) -> None:
        time.sleep(0.25)  # Give time for initial events/msgs to be shown
        scr          = self.scroller
        load_history = lambda l: self.chat.room.backfill_previous_messages(
            reverse=True, limit=l
        )

        while not self.chat.room.loaded_all_history:
            if self.isVisible():

                if scr.vmax <= scr.vstep_page:
                    load_history(25)

                elif scr.v <= scr.vmin:
                    load_history(100)

            time.sleep(0.1)


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() in (Qt.NoModifier, Qt.ShiftModifier):
            self.chat.send_area.box.setFocus()
            self.chat.send_area.box.keyPressEvent(event)
            return

        super().keyPressEvent(event)
