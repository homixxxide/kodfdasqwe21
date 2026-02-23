#!/usr/bin/env python3
"""MetaMind QML launcher.

UI moved to QML (new language layer) while keeping Python runtime/backend side intact.
This file does not alter gameplay/CV/GSI logic; it only boots the redesigned UI shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


class MetaMindBridge(QObject):
    """Bridge for future integration with existing Python technical core."""

    statusTextChanged = Signal()
    toastRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._status_text = "Система готова"

    @Property(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._status_text

    @Slot(str)
    def setStatusText(self, text: str) -> None:
        if text == self._status_text:
            return
        self._status_text = text
        self.statusTextChanged.emit()

    @Slot(str)
    def sendToast(self, message: str) -> None:
        self.toastRequested.emit(message)

    @Slot()
    def requestAutoScan(self) -> None:
        # Hook point for existing scan logic.
        self.sendToast("Автоскан: запрос отправлен")

    @Slot()
    def requestMetaRefresh(self) -> None:
        # Hook point for existing OpenDota refresh logic.
        self.sendToast("Обновление меты: запрос отправлен")


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("MetaMind")

    engine = QQmlApplicationEngine()
    bridge = MetaMindBridge()
    engine.rootContext().setContextProperty("metaBridge", bridge)

    qml_path = Path(__file__).with_name("metamind_new_design.qml")
    engine.load(QUrl.fromLocalFile(os.fspath(qml_path)))

    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
