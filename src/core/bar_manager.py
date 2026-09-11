import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QScreen, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication

from core.bar import Bar
from core.config import AppConfig
from core.utils.controller import reload_application
from core.utils.watcher import ConfigWatcher
from core.widgets.base import WidgetBase


class BarManager(QObject):
    bar_ready_signal = pyqtSignal(object)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.bars = []
        self.widget_event_listeners = []
        self.logger = logging.getLogger(__name__)
        self._reload_lock = threading.Lock()
        self._watch_config = None
        self._watch_stylesheet = None
        self._screen_change_timer = None
        self._init_config_watchers()

    @property
    def config_watchers(self):
        return self._watch_config, self._watch_stylesheet

    def _init_config_watchers(self):
        watch_config = self.config.watch_config
        watch_stylesheet = self.config.watch_stylesheet
        if watch_config:
            self._watch_config = ConfigWatcher(self.config.config_path, self._on_config_changed, delay=300)
        if watch_stylesheet:
            self._watch_stylesheet = ConfigWatcher(
                self.config.stylesheet_path, self._on_stylesheet_changed, delay=300
            )

    def _disconnect_reload_signals(self):
        if self._watch_config:
            self._watch_config.stop()
            self._watch_config = None
        if self._watch_stylesheet:
            self._watch_stylesheet.stop()
            self._watch_stylesheet = None

    def _on_stylesheet_changed(self):
        self.logger.info("Stylesheet changed. Reapplying styles.")
        for bar in self.bars:
            bar.reload_styles()

    def _on_config_changed(self):
        config_path = self.config.config_path
        try:
            config = AppConfig.load(config_path)
        except Exception as e:
            self.logger.error("Error loading config: %s", e)
            return
        if config and (config != self.config):
            # Fields that don't trigger a full application reload
            exclude = {"watch_config", "watch_stylesheet"}

            if config.model_dump(exclude=exclude) != self.config.model_dump(exclude=exclude):
                self.config = config
                self._disconnect_reload_signals()
                reload_application("配置变更，正在重载应用...")
            else:
                self.config = config
                logging.info("Configuration updated (no reload required).")
            logging.info("Successfully loaded updated config and re-initialised all bars.")

    @pyqtSlot(QScreen)
    def on_screens_update(self, _screen: QScreen) -> None:
        logging.info("Screens updated. Re-initialising all bars.")
        self._disconnect_reload_signals()
        reload_application("屏幕更新，正在重载应用...")

    def run_listeners_in_threads(self):
        for listener in self.widget_event_listeners:
            logging.info("Starting %s...", listener.__name__)
            thread = listener()
            thread.start()

    def add_bar(self, bar: Bar):
        self.bars.append(bar)
        self.logger.debug("Bar added: %s", bar)

    def remove_bar(self, bar: Bar):
        if bar in self.bars:
            self.bars.remove(bar)
            self.logger.debug("Bar removed: %s", bar)

    def create_bars(self):
        for bar_config in self.config.bars:
            bar = Bar(bar_config, self)
            self.bars.append(bar)
            self.bar_ready_signal.emit(bar)

    def stop(self):
        self._disconnect_reload_signals()
        for bar in self.bars:
            bar.stop()

    def run(self):
        self.create_bars()
        self.run_listeners_in_threads()
