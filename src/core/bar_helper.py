import ctypes
import logging
import os
import subprocess
import winreg
from datetime import datetime
from functools import partial
from typing import Any

import win32gui
import win32process
from PyQt6.QtCore import (
    QAbstractNativeEventFilter,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QWidget,
    QWidgetAction,
)
from win32con import HWND_BOTTOM, HWND_NOTOPMOST, HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE

from core.utils.controller import exit_application, reload_application
from core.utils.utilities import refresh_widget_style
from core.utils.win32.app_bar import APPBAR_CALLBACK_MESSAGE, AppBarNotify
from core.utils.win32.bindings import SetWindowPos
from core.utils.win32.bindings.user32 import KillTimer, RegisterWindowMessage, SetTimer, user32
from core.utils.win32.structs import MSG
from core.utils.win32.utils import apply_qmenu_style

# Register TaskbarCreated message to detect Explorer restarts
WM_TASKBARCREATED = RegisterWindowMessage("TaskbarCreated")


class GlobalState:
    """Centralized global state for detached widgets and application-wide configurations."""

    _is_dark = False
    _stylesheet = None
    _tooltip_options = None

    @classmethod
    def is_dark(cls) -> bool:
        return cls._is_dark

    @classmethod
    def set_dark(cls, value: bool):
        cls._is_dark = value

    @classmethod
    def stylesheet(cls) -> str:
        return cls._stylesheet or ""

    @classmethod
    def set_stylesheet(cls, value: str):
        cls._stylesheet = value

    @classmethod
    def tooltip_options(cls) -> Any:
        return cls._tooltip_options

    @classmethod
    def set_tooltip_options(cls, value: Any):
        cls._tooltip_options = value


class BarAnimationManager(QObject):
    """Handles bar show/hide animations."""

    def __init__(self, bar_widget: QWidget, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget
        self._animation = None
        self._target_geo = None
        self._pending_action = None

    def show_bar(self):
        if not self.bar_widget._animation.get("enabled"):
            self.bar_widget.show()
            return
        if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
            self._pending_action = "show"
            return
        self._pending_action = None
        if self.bar_widget._animation.get("type") == "fade":
            self._start_fade(True)
        else:
            self._start_slide(True)

    def hide_bar(self):
        if not self.bar_widget._animation.get("enabled"):
            self.bar_widget._skip_animation = True
            self.bar_widget.hide()
            self.bar_widget._skip_animation = False
            return
        if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
            self._pending_action = "hide"
            return
        self._pending_action = None
        if self.bar_widget._animation.get("type") == "fade":
            self._start_fade(False)
        else:
            self._start_slide(False)

    def _stop_animation(self):
        if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        self._animation = None

    def _start_fade(self, show: bool):
        self._stop_animation()
        duration = self.bar_widget._animation.get("duration", 300)
        self._animation = QPropertyAnimation(self.bar_widget, b"windowOpacity")
        self._animation.setDuration(duration)
        self._animation.setStartValue(0.0 if show else 1.0)
        self._animation.setEndValue(1.0 if show else 0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad if show else QEasingCurve.Type.InQuad)
        self._animation.finished.connect(self._on_show_finished if show else self._on_hide_finished)
        if show:
            self.bar_widget.setWindowOpacity(0.0)
            self.bar_widget.show()
        self._animation.start()

    def _slide_is_blocked(self, hidden: QRect) -> bool:
        """Is another screen sitting where the bar would slide out of view?

        The bar leaves its own screen while it slides, so on stacked monitors it would show up on
        the one next to it. Keeping it clipped means resizing the window on every frame, and DWM
        redraws the blur and the window shadow a step behind that, which is what smears. Nothing
        can clip a blurred window without resizing it, so those bars fade instead.
        """
        return any(screen.geometry().intersects(hidden) for screen in QApplication.screens())

    def _start_slide(self, show: bool):
        self._stop_animation()
        bar = self.bar_widget

        bar.position_bar()
        geo = bar.geometry()
        self._target_geo = (geo.x(), geo.y(), geo.width(), geo.height())

        screen_geo = bar.screen().geometry()
        if bar._alignment["position"] == "top":
            hidden_y = screen_geo.y() - geo.height()
        else:
            hidden_y = screen_geo.y() + screen_geo.height()
        hidden = QRect(geo.x(), hidden_y, geo.width(), geo.height())

        if self._slide_is_blocked(hidden):
            self._start_fade(show)
            return

        resting_pos = geo.topLeft()
        hidden_pos = hidden.topLeft()
        if show:
            bar.move(hidden_pos)

        self._animation = QPropertyAnimation(bar, b"pos", bar)
        self._animation.setDuration(bar._animation.get("duration", 300))
        self._animation.setStartValue(hidden_pos if show else resting_pos)
        self._animation.setEndValue(resting_pos if show else hidden_pos)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad if show else QEasingCurve.Type.InQuad)
        self._animation.finished.connect(self._on_show_finished if show else self._on_hide_finished)
        self._animation.start()

        if show and not bar.isVisible():
            bar.show()

    def _on_show_finished(self):
        if self._target_geo:
            self.bar_widget.setGeometry(*self._target_geo)
        self._animation = None
        self._process_pending()

        # Check if mouse left during the animation
        if (
            hasattr(self.bar_widget, "_autohide_manager")
            and self.bar_widget._autohide_manager is not None
            and self.bar_widget._autohide_manager._is_enabled
        ):
            cursor_pos = QCursor.pos()
            bar_geometry = self.bar_widget.geometry()
            autohide_mgr = self.bar_widget._autohide_manager

            # If not in the bar, and not in the safe zone (padding gap), start the timer
            if not bar_geometry.contains(cursor_pos) and not autohide_mgr._is_mouse_in_safe_zone(
                cursor_pos, bar_geometry
            ):
                if isinstance(autohide_mgr, SmartAutoHideManager):
                    if autohide_mgr._hide_timer:
                        autohide_mgr._hide_timer.start(autohide_mgr._autohide_delay)
                elif hasattr(autohide_mgr, "_hide_timer") and autohide_mgr._hide_timer:
                    autohide_mgr._hide_timer.start(autohide_mgr._autohide_delay)

    def _on_hide_finished(self):
        self.bar_widget._skip_animation = True
        self.bar_widget.hide()
        self.bar_widget._skip_animation = False
        self.bar_widget.setWindowOpacity(1.0)
        self._animation = None
        self._process_pending()

    def _process_pending(self):
        action = self._pending_action
        self._pending_action = None
        if action == "show" and not self.bar_widget.isVisible():
            self.show_bar()
        elif action == "hide" and self.bar_widget.isVisible():
            self.hide_bar()

    def cleanup(self):
        self._pending_action = None
        self._stop_animation()


class AutoHideZone(QFrame):
    """A transparent zone at the edge of the screen to detect when to show the bar"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowOpacity(0.01)

    def enterEvent(self, event):
        # Show the parent bar when mouse enters detection zone
        if self.parent() and hasattr(self.parent(), "_autohide_manager"):
            self.parent()._autohide_manager.show_bar()


class AutoHideManager(QObject):
    """Manages autohide functionality for bars"""

    def __init__(self, bar_widget, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget
        self._autohide_delay = 600
        self._detection_zone_height = None
        self._detection_zone = None
        self._hide_timer = None
        self._is_enabled = False

    def setup_autohide(self):
        """Initialize autohide functionality"""
        self._is_enabled = True
        # Set fixed 1px detection zone height
        self._detection_zone_height = 1

        # Create detection zone
        self._detection_zone = AutoHideZone(self.bar_widget)

        # Create hide timer
        self._hide_timer = QTimer(self.bar_widget)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_bar)

        # Install event filter on the bar
        self.bar_widget.installEventFilter(self)

        # Remove reserved screen space when autohide is enabled
        if hasattr(self.bar_widget, "app_bar_manager") and self.bar_widget.app_bar_manager:
            try:
                SystrayAppBarHelper.execute_without_systray_interference(
                    lambda: self.bar_widget.app_bar_manager.remove_appbar()
                )
            except Exception as e:
                logging.error("Failed to remove AppBar reservation: %s", e)

        # Set up detection zone after a short delay
        QTimer.singleShot(self._autohide_delay, self.setup_detection_zone)

    def setup_detection_zone(self):
        """Position and configure the autohide detection zone"""
        if not self._is_enabled or not self._detection_zone:
            return

        screen_geometry = self.bar_widget.screen().geometry()
        alignment = self.bar_widget._alignment

        if alignment["position"] == "top":
            self._detection_zone.setGeometry(
                screen_geometry.x(), screen_geometry.y(), screen_geometry.width(), self._detection_zone_height
            )
        else:
            self._detection_zone.setGeometry(
                screen_geometry.x(),
                screen_geometry.y() + screen_geometry.height() - self._detection_zone_height,
                screen_geometry.width(),
                self._detection_zone_height,
            )

        self._hide_timer.start(self._autohide_delay)

    def show_bar(self):
        """Show the bar when mouse hovers over detection zone"""
        if not self.bar_widget.isVisible() and self._is_enabled:
            self.bar_widget.show()

    def _is_child_of_bar(self, widget):
        """Walk parent chain to check if widget belongs to this bar."""
        p = widget.parent() if widget else None
        while p:
            if p is self.bar_widget:
                return True
            p = p.parent()
        return False

    def _should_stay_visible(self):
        """Check if bar should stay visible because a child popup/menu is open."""
        # Qt::Popup windows (QMenu, PopupWidget)
        if QApplication.activePopupWidget():
            return True
        # Qt::Tool windows that called activateWindow() (SystrayPopup)
        active = QApplication.activeWindow()
        if active and active is not self.bar_widget and self._is_child_of_bar(active):
            return True
        # Check all visible top-level widgets
        cursor_pos = QCursor.pos()
        for w in QApplication.topLevelWidgets():
            if w is self.bar_widget or w is self._detection_zone or not w.isVisible():
                continue
            # Child of bar (parent chain intact) - e.g. SystrayPopup after losing focus
            if self._is_child_of_bar(w):
                return True
            # Cursor is over it (parent chain severed) - e.g. ThumbnailHost
            if w.geometry().contains(cursor_pos):
                return True
        return False

    def hide_bar(self):
        """Hide the bar and show detection zone"""
        if self._is_enabled and self.bar_widget.isVisible():
            if self._should_stay_visible():
                self._hide_timer.start(self._autohide_delay)
                return
            self.bar_widget.hide()
            if self._detection_zone:
                self._detection_zone.show()
                self._detection_zone.raise_()

    def eventFilter(self, watched, event):
        """Filter bar Enter/Leave events for hide timer"""
        if watched is self.bar_widget and self._is_enabled:
            if event.type() == QEvent.Type.Enter:
                if self._hide_timer:
                    self._hide_timer.stop()
            elif event.type() == QEvent.Type.Leave:
                cursor_pos = QCursor.pos()
                bar_geometry = self.bar_widget.geometry()

                if self._is_mouse_in_safe_zone(cursor_pos, bar_geometry):
                    return False

                if self._hide_timer:
                    self._hide_timer.start(self._autohide_delay)
        return False

    def _is_mouse_in_safe_zone(self, cursor_pos, bar_geometry):
        """Check if mouse is in the gap between bar and detection zone"""
        screen_geometry = self.bar_widget.screen().geometry()
        alignment = self.bar_widget._alignment

        # Calculate mouse position relative to screen
        screen_x = cursor_pos.x() - screen_geometry.x()
        screen_y = cursor_pos.y() - screen_geometry.y()

        # Check if mouse is within screen bounds horizontally
        if screen_x < 0 or screen_x > screen_geometry.width():
            return False

        if alignment["position"] == "top":
            bar_top = bar_geometry.y() - screen_geometry.y()
            return 0 <= screen_y <= bar_top
        else:
            bar_bottom = (bar_geometry.y() + bar_geometry.height()) - screen_geometry.y()
            return bar_bottom <= screen_y <= screen_geometry.height()

    def is_enabled(self):
        """Check if autohide is enabled"""
        return self._is_enabled

    def cleanup(self):
        """Clean up resources"""
        if self._hide_timer:
            self._hide_timer.stop()
        if self._detection_zone:
            self._detection_zone.hide()
            self._detection_zone.deleteLater()
        self._is_enabled = False

        # Restore reserved screen space when autohide is disabled and only if windows_app_bar was enabled
        if hasattr(self.bar_widget, "update_app_bar") and self.bar_widget._window_flags["windows_app_bar"]:
            try:
                SystrayAppBarHelper.execute_without_systray_interference(lambda: self.bar_widget.update_app_bar())
            except Exception as e:
                logging.error("Failed to restore AppBar reservation: %s", e)


class LockIndicatorWidget(QWidget):
    """智能自动隐藏模式下的锁图标指示器，带环形解锁进度条。

    窗口本身覆盖整个栏的宽度（透明），仅在中心绘制锁图标和进度环，
    这样鼠标在栏的任意位置悬停都能触发解锁。
    注意：不使用 setWindowOpacity，否则全透明时 Windows 会穿透鼠标事件。
    透明度通过绘制颜色的 alpha 通道控制。
    """

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._progress = 0.0  # 0.0 ~ 1.0
        self._unlocking = False
        self._hover_visible = False  # 鼠标悬停时才显示锁图标

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 不设置 setWindowOpacity，保持窗口可接收鼠标事件

    def _apply_opacity(self, color_str: str) -> QColor:
        """将配置的不透明度应用到颜色上。"""
        c = QColor(color_str)
        c.setAlphaF(c.alphaF() * self._config.get("indicator_opacity", 0.6))
        return c

    def set_hover_visible(self, visible: bool):
        """设置鼠标悬停时是否显示锁图标。"""
        if self._hover_visible != visible:
            self._hover_visible = visible
            self.update()

    def set_progress(self, value: float):
        """设置解锁进度 (0.0~1.0)，触发重绘。"""
        self._progress = max(0.0, min(1.0, value))
        self._unlocking = self._progress > 0
        self.update()

    def reset_progress(self):
        """重置进度为 0。"""
        self._progress = 0.0
        self._unlocking = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 未悬停且无进度时：绘制一个极低透明度的背景，
        # 确保窗口有非零 alpha 像素以接收鼠标事件（Windows 分层窗口特性）
        if not self._hover_visible and self._progress == 0:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
            painter.end()
            return

        size = self._config.get("indicator_size", 28)
        cx = self.width() // 2
        cy = self.height() // 2
        half = size // 2
        rect = QRectF(cx - half, cy - half, size, size)

        # 绘制进度环背景
        thickness = self._config.get("progress_thickness", 3)
        bg_color = self._apply_opacity(self._config.get("progress_background_color", "#555555"))
        pen_bg = QPen(bg_color, thickness)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)

        # 绘制解锁进度环
        if self._progress > 0:
            fg_color = self._apply_opacity(self._config.get("progress_color", "#ffffff"))
            pen_fg = QPen(fg_color, thickness)
            pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_fg)
            span_angle = int(-360 * 16 * self._progress)
            painter.drawArc(rect, 90 * 16, span_angle)

        # 绘制锁图标
        icon_color = self._apply_opacity(self._config.get("progress_color", "#ffffff"))
        painter.setPen(icon_color)
        font = QFont()
        font.setPointSize(max(8, size // 3))
        font.setFamily("Segoe MDL2 Assets")
        painter.setFont(font)
        icon = self._config.get("lock_icon", "\uf023")
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, icon)

        painter.end()


class SmartAutoHideManager(QObject):
    """智能自动隐藏管理器。

    三态行为：
    - 锁定：栏隐藏，仅显示锁图标指示器；鼠标悬停栏区域，进度环满后解锁。
    - 解锁可见：完整栏显示，行为与普通自动隐藏一致；鼠标离开 600ms 后隐藏栏。
    - 解锁隐藏：栏隐藏，顶部 1px 检测区生效；鼠标移到顶部即显示栏；
      经过 lock_timeout 无交互后重新锁定。
    """

    def __init__(self, bar_widget, config: dict, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget
        self._config = config
        self._is_enabled = False
        self._is_locked = True
        self._indicator = None
        self._detection_zone = None
        self._unlock_timer = None
        self._unlock_elapsed = 0
        self._unlock_interval = 30  # 进度更新间隔 ms
        self._hide_timer = None     # 解锁后鼠标离开的短延迟隐藏（与普通自动隐藏一致 600ms）
        self._autohide_delay = 600
        self._lock_timer = None     # 解锁隐藏后重新锁定的倒计时
        self._lock_progress_timer = None  # 解锁可见态悬停空白处锁定的进度计时器
        self._lock_progress_elapsed = 0

    def setup(self):
        """初始化智能自动隐藏。"""
        self._is_enabled = True
        self._is_locked = True

        # 创建锁图标指示器（锁定态）
        self._indicator = LockIndicatorWidget(self._config, self.bar_widget)
        self._indicator.installEventFilter(self)

        # 创建顶部检测区（解锁隐藏态，与普通自动隐藏一致）
        self._detection_zone = AutoHideZone(self.bar_widget)
        self._detection_zone.setMouseTracking(True)

        # 解锁进度计时器
        self._unlock_timer = QTimer(self.bar_widget)
        self._unlock_timer.setInterval(self._unlock_interval)
        self._unlock_timer.timeout.connect(self._on_unlock_tick)

        # 短延迟隐藏计时器（解锁可见 → 解锁隐藏）
        self._hide_timer = QTimer(self.bar_widget)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timer)

        # 锁定倒计时计时器（解锁隐藏 → 锁定）
        self._lock_timer = QTimer(self.bar_widget)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._lock)

        # 悬停锁定进度计时器（解锁可见 → 悬停空白处直接锁定）
        self._lock_progress_timer = QTimer(self.bar_widget)
        self._lock_progress_timer.setInterval(self._unlock_interval)
        self._lock_progress_timer.timeout.connect(self._on_lock_progress_tick)

        # 安装栏和栏框架的事件过滤器（框架覆盖栏的全部区域，用于捕获双击空白处）
        self.bar_widget.installEventFilter(self)
        if hasattr(self.bar_widget, "_bar_frame") and self.bar_widget._bar_frame:
            self.bar_widget._bar_frame.installEventFilter(self)

        # 移除 AppBar 预留空间
        if hasattr(self.bar_widget, "app_bar_manager") and self.bar_widget.app_bar_manager:
            try:
                SystrayAppBarHelper.execute_without_systray_interference(
                    lambda: self.bar_widget.app_bar_manager.remove_appbar()
                )
            except Exception as e:
                logging.error("智能自动隐藏：移除 AppBar 预留失败：%s", e)

        # 延迟定位指示器并进入锁定状态
        QTimer.singleShot(100, self._enter_locked_state)

    def _indicator_geometry(self) -> QRect:
        """计算指示器应处的几何位置（与栏同宽同高，位于栏的位置）。"""
        screen_geo = self.bar_widget.screen().geometry()
        bar_geo = self.bar_widget.geometry()
        alignment = self.bar_widget._alignment
        height = self.bar_widget._dimensions["height"]

        if alignment["position"] == "top":
            y = screen_geo.y()
        else:
            y = screen_geo.y() + screen_geo.height() - height

        return QRect(bar_geo.x(), y, bar_geo.width(), height)

    def _setup_detection_zone(self):
        """设置顶部 1px 检测区的位置和大小（与普通自动隐藏一致）。"""
        if not self._detection_zone:
            return
        screen_geo = self.bar_widget.screen().geometry()
        bar_geo = self.bar_widget.geometry()
        alignment = self.bar_widget._alignment
        zone_height = 1

        if alignment["position"] == "top":
            y = screen_geo.y()
        else:
            y = screen_geo.y() + screen_geo.height() - zone_height

        self._detection_zone.setGeometry(bar_geo.x(), y, bar_geo.width(), zone_height)

    def _enter_locked_state(self):
        """进入锁定状态：隐藏栏和检测区，显示锁图标指示器。"""
        if not self._is_enabled:
            return
        self._is_locked = True
        logging.debug("智能自动隐藏：进入锁定状态")

        # 停止所有计时器
        if self._hide_timer:
            self._hide_timer.stop()
        if self._lock_timer:
            self._lock_timer.stop()
        if self._lock_progress_timer:
            self._lock_progress_timer.stop()
        self._lock_progress_elapsed = 0

        # 隐藏检测区
        if self._detection_zone:
            self._detection_zone.hide()

        # 隐藏栏并显示指示器（指示器默认隐藏锁图标，鼠标悬停时才显示）
        self.bar_widget.hide()
        if self._indicator:
            geo = self._indicator_geometry()
            self._indicator.setGeometry(geo)
            self._indicator.reset_progress()
            if self._config.get("indicator_auto_hide", True):
                self._indicator.set_hover_visible(False)
            self._indicator.show()
            self._indicator.raise_()

    def _unlock(self):
        """解锁：隐藏指示器，显示完整栏，进入解锁可见态。"""
        if not self._is_enabled:
            return
        self._is_locked = False
        logging.debug("智能自动隐藏：解锁，显示完整栏")

        # 隐藏指示器
        if self._indicator:
            self._indicator.hide()

        # 停止解锁进度
        self._unlock_elapsed = 0
        if self._unlock_timer:
            self._unlock_timer.stop()

        # 停止锁定倒计时
        if self._lock_timer:
            self._lock_timer.stop()

        # 停止悬停锁定进度
        if self._lock_progress_timer:
            self._lock_progress_timer.stop()
        self._lock_progress_elapsed = 0

        # 显示栏（与普通自动隐藏一致的动画）
        anim_mgr = getattr(self.bar_widget, "_animation_manager", None)
        if anim_mgr and self.bar_widget._animation.get("enabled", False):
            anim_mgr.show_bar()
        else:
            self.bar_widget.show()
        self.bar_widget.raise_()

    def _on_hide_timer(self):
        """短延迟隐藏计时器回调：栏隐藏，显示检测区，开始锁定倒计时。"""
        if not self._is_enabled or self._is_locked:
            return
        logging.debug("智能自动隐藏：短延迟隐藏触发，栏隐藏，启动锁定倒计时")

        # 隐藏栏（与普通自动隐藏一致的动画）
        anim_mgr = getattr(self.bar_widget, "_animation_manager", None)
        if anim_mgr and self.bar_widget._animation.get("enabled", False):
            anim_mgr.hide_bar()
        else:
            self.bar_widget.hide()

        # 显示顶部检测区
        self._setup_detection_zone()
        if self._detection_zone:
            self._detection_zone.show()
            self._detection_zone.raise_()

        # 开始锁定倒计时
        if self._lock_timer:
            self._lock_timer.start(self._config.get("lock_timeout", 15000))

    def show_bar(self):
        """检测区鼠标进入：显示栏，停止锁定倒计时（与 AutoHideManager.show_bar 接口一致）。"""
        if not self._is_enabled or self._is_locked or self.bar_widget.isVisible():
            return
        logging.debug("智能自动隐藏：检测区触发，显示栏，停止锁定倒计时")

        # 停止锁定倒计时
        if self._lock_timer:
            self._lock_timer.stop()

        # 隐藏检测区
        if self._detection_zone:
            self._detection_zone.hide()

        # 显示栏（与普通自动隐藏一致的动画）
        anim_mgr = getattr(self.bar_widget, "_animation_manager", None)
        if anim_mgr and self.bar_widget._animation.get("enabled", False):
            anim_mgr.show_bar()
        else:
            self.bar_widget.show()
        self.bar_widget.raise_()

    def _lock(self):
        """锁定倒计时回调：重新进入锁定状态。"""
        if not self._is_enabled:
            return
        # 如果有弹出菜单打开，延迟锁定
        if self._should_stay_visible():
            logging.debug("智能自动隐藏：有弹出窗口活跃，延迟锁定")
            self._lock_timer.start(self._config.get("lock_timeout", 15000))
            return
        logging.debug("智能自动隐藏：锁定倒计时结束，进入锁定状态")
        self._enter_locked_state()

    def _should_stay_visible(self) -> bool:
        """检查是否应推迟锁定：仅当栏的弹出菜单/子窗口活跃时。"""
        # 有 Qt 弹出菜单（QMenu 等）
        if QApplication.activePopupWidget():
            return True
        # 当前活跃窗口是栏的子窗口（如组件弹出面板）
        active = QApplication.activeWindow()
        if active and active is not self.bar_widget:
            p = active.parent() if active else None
            while p:
                if p is self.bar_widget:
                    return True
                p = p.parent()
        # 遍历顶层窗口，检查是否有栏的子窗口可见且鼠标在其上方
        cursor_pos = QCursor.pos()
        for w in QApplication.topLevelWidgets():
            if w is self.bar_widget or w is self._indicator or w is self._detection_zone or not w.isVisible():
                continue
            p = w.parent() if w else None
            is_child = False
            while p:
                if p is self.bar_widget:
                    is_child = True
                    break
                p = p.parent()
            # 只有栏的子窗口（弹出面板）且鼠标在其上方才推迟锁定
            if is_child and w.geometry().contains(cursor_pos):
                return True
        return False

    def _on_unlock_tick(self):
        """解锁进度计时器回调。"""
        self._unlock_elapsed += self._unlock_interval
        duration = self._config.get("unlock_hover_duration", 500)
        progress = self._unlock_elapsed / duration
        if self._indicator:
            self._indicator.set_progress(progress)
        if progress >= 1.0:
            self._unlock_timer.stop()
            self._unlock()

    def _is_cursor_on_empty_area(self) -> bool:
        """检查鼠标是否在栏的空白区域（不在子组件上）。"""
        cursor_pos = QCursor.pos()
        widget_at = QApplication.widgetAt(cursor_pos)
        if widget_at is None:
            return False
        # 鼠标在栏本身或栏框架上（非子组件）即为空白区域
        bar_frame = getattr(self.bar_widget, "_bar_frame", None)
        return widget_at is self.bar_widget or (bar_frame is not None and widget_at is bar_frame)

    def _on_lock_progress_tick(self):
        """悬停锁定进度计时器回调（解锁可见态）。"""
        if not self._config.get("hover_to_lock", True):
            self._lock_progress_timer.stop()
            return

        if self._is_cursor_on_empty_area():
            self._lock_progress_elapsed += self._unlock_interval
        else:
            # 鼠标移到了子组件上，重置进度
            self._lock_progress_elapsed = 0

        duration = self._config.get("lock_hover_duration", 800)
        progress = self._lock_progress_elapsed / duration

        # 显示指示器作为视觉反馈（覆盖在栏上方，透明背景）
        if self._indicator and progress > 0:
            self._indicator.set_hover_visible(True)
            self._indicator.set_progress(progress)
            if not self._indicator.isVisible():
                self._indicator.setGeometry(self._indicator_geometry())
                self._indicator.show()
                self._indicator.raise_()

        if progress >= 1.0:
            self._lock_progress_timer.stop()
            self._lock_progress_elapsed = 0
            logging.debug("智能自动隐藏：悬停空白处进度满，锁定")
            self._enter_locked_state()

    def _stop_lock_progress(self):
        """停止悬停锁定进度并隐藏指示器覆盖层。"""
        if self._lock_progress_timer:
            self._lock_progress_timer.stop()
        self._lock_progress_elapsed = 0
        if self._indicator and not self._is_locked:
            self._indicator.hide()
            self._indicator.reset_progress()
            self._indicator.set_hover_visible(False)

    def eventFilter(self, watched, event):
        """事件过滤器：处理指示器和栏的鼠标进入/离开。"""
        if not self._is_enabled:
            return False

        # 指示器的鼠标事件（锁定态）
        if watched is self._indicator and self._is_locked:
            if event.type() == QEvent.Type.Enter:
                logging.debug("智能自动隐藏：鼠标进入指示器区域")
                # 鼠标进入：显示锁图标，开始解锁进度
                if self._indicator:
                    self._indicator.set_hover_visible(True)
                self._unlock_elapsed = 0
                self._unlock_timer.start()
            elif event.type() == QEvent.Type.Leave:
                logging.debug("智能自动隐藏：鼠标离开指示器区域")
                # 鼠标离开：停止进度，隐藏锁图标
                self._unlock_timer.stop()
                self._unlock_elapsed = 0
                if self._indicator:
                    self._indicator.reset_progress()
                    if self._config.get("indicator_auto_hide", True):
                        self._indicator.set_hover_visible(False)

        # 栏和栏框架的鼠标事件（解锁可见态）
        bar_frame = getattr(self.bar_widget, "_bar_frame", None)
        is_bar_target = watched is self.bar_widget or (bar_frame is not None and watched is bar_frame)

        if is_bar_target and not self._is_locked:
            # 双击空白处立即隐藏
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if self._config.get("double_click_to_hide", True):
                    self._stop_lock_progress()
                    if self._hide_timer:
                        self._hide_timer.stop()
                    logging.debug("智能自动隐藏：双击空白处，立即隐藏")
                    self._on_hide_timer()
                    return True
            # 鼠标进入栏：启动悬停锁定进度（如果启用）
            elif event.type() == QEvent.Type.Enter and watched is self.bar_widget:
                if self._hide_timer:
                    self._hide_timer.stop()
                if self._config.get("hover_to_lock", True):
                    self._lock_progress_elapsed = 0
                    self._lock_progress_timer.start()
            # 鼠标离开栏：停止悬停锁定进度，启动短延迟隐藏
            elif event.type() == QEvent.Type.Leave and watched is self.bar_widget:
                self._stop_lock_progress()
                cursor_pos = QCursor.pos()
                bar_geo = self.bar_widget.geometry()
                # 检查鼠标是否仍在栏附近的安全区域
                if not self._is_mouse_in_safe_zone(cursor_pos, bar_geo):
                    # 停止锁定倒计时（如果正在运行），启动短延迟隐藏
                    if self._lock_timer:
                        self._lock_timer.stop()
                    if self._hide_timer:
                        self._hide_timer.start(self._autohide_delay)

        return False

    def _is_mouse_in_safe_zone(self, cursor_pos, bar_geometry):
        """检查鼠标是否在栏附近的安全区域（防止动画期间误触发隐藏）。"""
        screen_geometry = self.bar_widget.screen().geometry()
        alignment = self.bar_widget._alignment
        screen_x = cursor_pos.x() - screen_geometry.x()
        screen_y = cursor_pos.y() - screen_geometry.y()

        if screen_x < 0 or screen_x > screen_geometry.width():
            return False

        if alignment["position"] == "top":
            bar_top = bar_geometry.y() - screen_geometry.y()
            return 0 <= screen_y <= bar_top + bar_geometry.height() + 5
        else:
            bar_bottom = (bar_geometry.y() + bar_geometry.height()) - screen_geometry.y()
            return bar_bottom - 5 <= screen_y <= screen_geometry.height()

    def update_indicator_position(self):
        """屏幕几何变化时更新指示器和检测区位置。"""
        if self._indicator and self._is_locked:
            self._indicator.setGeometry(self._indicator_geometry())
        if self._detection_zone and not self._is_locked and not self.bar_widget.isVisible():
            self._setup_detection_zone()

    def is_enabled(self):
        return self._is_enabled

    def is_locked(self):
        return self._is_locked

    def cleanup(self):
        """清理资源。"""
        self._is_enabled = False
        if self._unlock_timer:
            self._unlock_timer.stop()
        if self._hide_timer:
            self._hide_timer.stop()
        if self._lock_timer:
            self._lock_timer.stop()
        if self._lock_progress_timer:
            self._lock_progress_timer.stop()
        if self._indicator:
            self._indicator.hide()
            self._indicator.deleteLater()
            self._indicator = None
        if self._detection_zone:
            self._detection_zone.hide()
            self._detection_zone.deleteLater()
            self._detection_zone = None

        # 恢复 AppBar 预留空间
        if hasattr(self.bar_widget, "update_app_bar") and self.bar_widget._window_flags["windows_app_bar"]:
            try:
                SystrayAppBarHelper.execute_without_systray_interference(lambda: self.bar_widget.update_app_bar())
            except Exception as e:
                logging.error("智能自动隐藏：恢复 AppBar 预留失败：%s", e)


class SystrayAppBarHelper:
    """Helper class to manage systray window state during AppBar operations"""

    @staticmethod
    def execute_without_systray_interference(callback):
        """
        Execute a callback with systray timer temporarily killed.
        This prevents systray from continuously reasserting HWND_TOPMOST every 100ms,
        which interferes with AppBar registration by triggering work area recalculations.
        """
        systray_hwnd = SystrayAppBarHelper._get_systray_hwnd()
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE

        try:
            if systray_hwnd:
                # Kill the systray timer (ID 1) to prevent HWND_TOPMOST interference
                KillTimer(systray_hwnd, 1)
                # Demote systray to non-topmost
                SetWindowPos(systray_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)

            callback()

        finally:
            if systray_hwnd:
                # Restore systray to topmost
                SetWindowPos(systray_hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
                # Restart the timer (ID 1, 100ms interval)
                SetTimer(systray_hwnd, 1, 100, None)

    @staticmethod
    def _get_systray_hwnd():
        """Get the systray monitor window hwnd if active"""
        try:
            from core.widgets.yasb.systray import SystrayWidget

            if SystrayWidget._systray_client_instance and hasattr(SystrayWidget._systray_client_instance, "hwnd"):
                hwnd = SystrayWidget._systray_client_instance.hwnd
                if hwnd and hwnd != 0:
                    return hwnd
        except Exception:
            pass
        return None


class AppBarManager(QAbstractNativeEventFilter):
    """Central handler for AppBar-related native Windows messages."""

    _instance = None
    _installed = False

    # Default window classes to exclude from fullscreen detection
    EXCLUDED_WINDOW_CLASSES = {
        "Progman",
        "WorkerW",
        "XamlWindow",
        "Shell_TrayWnd",
        "XamlExplorerHostIslandWindow",
        "CEF-OSC-WIDGET",
        "CEFCLIENT",
    }

    # Suffixes for version-dependent window classes (e.g. Qt653QWindowIcon)
    EXCLUDED_WINDOW_CLASS_SUFFIXES = ("QWindowIcon",)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._bars = {}
            cls._instance._bar_intended_state = {}  # Track intended visibility (True=visible, False=hidden)
            cls._instance._swp_flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            cls._instance._ready = False  # Enabled after first bar registers
            cls._instance._reregister_pending = False  # Coalesces multiple WM_TASKBARCREATED into one
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            super().__init__()
            self._initialized = True

    def _ensure_installed(self):
        """Install the native event filter on first use"""
        if not AppBarManager._installed:
            app = QApplication.instance()
            if app:
                app.installNativeEventFilter(self)
                AppBarManager._installed = True

    def register_bar(self, hwnd: int, bar_widget):
        """Register a bar to receive fullscreen notifications"""
        self._ensure_installed()
        self._bars[hwnd] = bar_widget
        self._bar_intended_state[hwnd] = True  # Initially visible
        self._ready = True

    def unregister_bar(self, hwnd: int):
        """Unregister a bar from receiving fullscreen notifications"""
        self._bars.pop(hwnd, None)
        self._bar_intended_state.pop(hwnd, None)

    def suppress(self):
        """Temporarily suppress WM_TASKBARCREATED handling.
        Used when our own code broadcasts TaskbarCreated (e.g. systray init)."""
        self._ready = False

    def unsuppress(self):
        """Re-enable WM_TASKBARCREATED handling after suppress()."""
        self._ready = True

    def nativeEventFilter(self, eventType, message):
        """Filter native Windows messages for AppBar fullscreen notifications and Explorer restarts"""
        try:
            if eventType == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents

                # Handle TaskbarCreated message (Explorer restart)
                if msg.message == WM_TASKBARCREATED:
                    # Only handle if fully initialized and not already scheduled.
                    # WM_TASKBARCREATED is broadcast to all top-level windows, so we
                    # coalesce multiple messages into a single deferred re-registration.
                    if self._ready and not self._reregister_pending and self._bars:
                        self._reregister_pending = True
                        QTimer.singleShot(0, self._deferred_reregister)
                    return False, 0

                if msg.message == APPBAR_CALLBACK_MESSAGE:
                    hwnd = msg.hwnd
                    notification_code = msg.wParam

                    if hwnd in self._bars and notification_code == AppBarNotify.FullScreenApp:
                        is_fullscreen_opening = bool(msg.lParam)
                        self._handle_fullscreen(hwnd, is_fullscreen_opening)
        except Exception:
            pass

        return False, 0

    def _deferred_reregister(self):
        """Deferred handler that runs once per event loop iteration,
        coalescing all WM_TASKBARCREATED messages from the same batch."""
        self._reregister_pending = False
        if not self._ready or not self._bars:
            return

        # Collect bars that actually need re-registration
        bars_to_reregister = []
        needs_systray_workaround = False
        for bw in self._bars.values():
            flags = getattr(bw, "_window_flags", {})
            app_bar = flags.get("windows_app_bar", False)
            fullscreen = getattr(bw, "_hide_on_fullscreen", False)
            if not app_bar and not fullscreen:
                continue
            if hasattr(bw, "_autohide_manager") and bw._autohide_manager and bw._autohide_manager.is_enabled():
                continue
            if not hasattr(bw, "update_app_bar"):
                continue
            bars_to_reregister.append((bw, app_bar))
            if app_bar:
                needs_systray_workaround = True

        if not bars_to_reregister:
            return

        count = len(bars_to_reregister)
        logging.info("AppBarManager need to re-register %d %s", count, "bar" if count == 1 else "bars")

        def reregister():
            for bw, app_bar in bars_to_reregister:
                try:
                    if hasattr(bw, "app_bar_manager") and bw.app_bar_manager:
                        bw.app_bar_manager.remove_appbar()
                    bw.update_app_bar()
                    reason = "space reservation + fullscreen" if app_bar else "fullscreen detection"
                    logging.info("Re-registered AppBar for %s (%s)", getattr(bw, "bar_id", "?"), reason)
                except Exception as e:
                    logging.error("Failed to re-register bar: %s", e)

        if needs_systray_workaround:
            SystrayAppBarHelper.execute_without_systray_interference(reregister)
        else:
            reregister()

    def _is_foreground_excluded(self) -> bool:
        """Check if the foreground window should be excluded from fullscreen detection."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return False
            # Exclude our own process windows , overlays, modal dialogs and etc.
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == os.getpid():
                return True
            window_class = win32gui.GetClassName(hwnd)
            if window_class in self.EXCLUDED_WINDOW_CLASSES or window_class.endswith(
                self.EXCLUDED_WINDOW_CLASS_SUFFIXES
            ):
                return True
        except Exception:
            pass
        return False

    def _handle_fullscreen(self, hwnd: int, is_fullscreen_opening: bool):
        """Handle ABN_FULLSCREENAPP notification for a bar."""
        bar_widget = self._bars.get(hwnd)
        if not bar_widget:
            return

        # Check if the fullscreen app's window should be excluded
        if is_fullscreen_opening:
            if self._is_foreground_excluded():
                return

        intended_visible = self._bar_intended_state.get(hwnd, True)
        should_hide_bar = getattr(bar_widget, "_hide_on_fullscreen", False)

        # We only need to process if hide_on_fullscreen is enabled
        if not should_hide_bar:
            return

        if is_fullscreen_opening:
            if intended_visible:
                SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, self._swp_flags)
                self._bar_intended_state[hwnd] = False
        else:
            if not intended_visible:
                SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, self._swp_flags)
                self._bar_intended_state[hwnd] = True


class MaximizedWindowWatcher(QObject):
    """Watches for any maximized window on the bar's monitor and toggles autohide accordingly."""

    def __init__(self, bar_widget, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget
        self._is_autohide_active = False
        self._had_autohide_before = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._check_maximized_windows)
        self._poll_timer.start()

    def _check_maximized_windows(self):
        """Check if any top-level window is maximized on the bar's monitor."""
        try:
            from core.utils.win32.utils import get_monitor_hwnd, is_window_maximized

            bar_monitor = getattr(self.bar_widget, "monitor_hwnd", None)
            if not bar_monitor:
                return

            has_maximized = False

            def enum_callback(hwnd, _):
                nonlocal has_maximized
                if has_maximized:
                    return False
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    if not win32gui.GetWindowText(hwnd):
                        return True
                    cls_name = win32gui.GetClassName(hwnd)
                    if cls_name in AppBarManager.EXCLUDED_WINDOW_CLASSES:
                        return True
                    if cls_name.endswith(AppBarManager.EXCLUDED_WINDOW_CLASS_SUFFIXES):
                        return True
                    window_monitor = get_monitor_hwnd(hwnd)
                    if window_monitor != bar_monitor:
                        return True
                    if is_window_maximized(hwnd):
                        has_maximized = True
                        return False
                except Exception:
                    pass
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_long))
            callback = WNDENUMPROC(enum_callback)
            user32.EnumWindows(callback, 0)

            if has_maximized and not self._is_autohide_active:
                self._enable_autohide()
            elif not has_maximized and self._is_autohide_active:
                self._disable_autohide()

        except Exception:
            logging.exception("Failed to check maximized windows")

    def _enable_autohide(self):
        """Enable autohide because a maximized window was detected."""
        self._is_autohide_active = True
        # Remember if autohide was already active before we touched it
        self._had_autohide_before = (
            hasattr(self.bar_widget, "_autohide_manager")
            and self.bar_widget._autohide_manager is not None
            and self.bar_widget._autohide_manager.is_enabled()
        )
        if self._had_autohide_before:
            return
        if not self.bar_widget._autohide_manager:
            self.bar_widget._autohide_manager = AutoHideManager(self.bar_widget, self.bar_widget)
        if not self.bar_widget._autohide_manager.is_enabled():
            self.bar_widget._autohide_manager.setup_autohide()

    def _disable_autohide(self):
        """Disable autohide because no maximized windows remain."""
        self._is_autohide_active = False
        # If user already had autohide enabled before, don't disable it
        if self._had_autohide_before:
            self._had_autohide_before = False
            return
        if hasattr(self.bar_widget, "_autohide_manager") and self.bar_widget._autohide_manager:
            self.bar_widget._autohide_manager.cleanup()
            self.bar_widget._autohide_manager = None
        # Ensure bar is visible
        if not self.bar_widget.isVisible():
            self.bar_widget.show()

    def cleanup(self):
        """Clean up resources."""
        self._poll_timer.stop()
        if self._is_autohide_active:
            self._disable_autohide()


class OsThemeManager(QObject):
    """Manages OS theme detection and applies theme classes to widgets"""

    def __init__(self, target_widget: QWidget, parent=None):
        super().__init__(parent)
        self.target_widget = target_widget
        self._is_dark_theme = None

    def detect_os_theme(self) -> bool:
        """Detect if OS is using dark theme"""
        try:
            with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as registry:
                with winreg.OpenKey(registry, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return value == 0
        except Exception as e:
            logging.error("Failed to determine Windows theme: %s", e)
            return False

    def update_theme_class(self):
        """Update the theme class on the target widget"""
        if not self.target_widget:
            return

        is_dark_theme = self.detect_os_theme()
        if is_dark_theme != self._is_dark_theme:
            class_property = self.target_widget.property("class")
            if is_dark_theme:
                class_property += " dark"
            else:
                class_property = class_property.replace(" dark", "")
            self.target_widget.setProperty("class", class_property)
            self._update_styles(self.target_widget)
            self._is_dark_theme = is_dark_theme
            GlobalState.set_dark(is_dark_theme)

    def _update_styles(self, widget):
        """Update styles for widget and its children by unpolishing and re-polishing"""
        refresh_widget_style(widget)
        for child in widget.findChildren(QWidget):
            refresh_widget_style(child)


class BarContextMenu:
    """A class to handle the context menu for a bar."""

    def __init__(self, parent, bar_name, widgets, widget_config_map, autohide_bar):
        self.parent = parent
        self._bar_name = bar_name
        self._widgets = widgets
        self._widget_config_map = widget_config_map
        self._autohide_bar = autohide_bar

    def show(self, position):
        self._menu = QMenu(self.parent)
        self._menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        apply_qmenu_style(self._menu)
        self._menu.setProperty("class", "context-menu dark" if GlobalState.is_dark() else "context-menu")
        self._menu.aboutToHide.connect(self._on_menu_about_to_hide)

        # Bar info
        bar_info = self._menu.addAction(f"栏: {self._bar_name}")
        bar_info.setEnabled(False)

        # Widgets menu
        widgets_menu = self._menu.addMenu("活动组件")
        apply_qmenu_style(widgets_menu)
        widgets_menu.setProperty(
            "class", "context-menu submenu dark" if GlobalState.is_dark() else "context-menu submenu"
        )
        self._populate_widgets_menu(widgets_menu)

        self._menu.addSeparator()

        # System actions
        task_manager = self._menu.addAction("任务管理器")
        task_manager.triggered.connect(self._open_task_manager)

        # Screenshot action
        screenshot_action = self._menu.addAction("截图")
        screenshot_action.triggered.connect(self._take_screenshot)

        self._menu.addSeparator()

        # Bar actions - 自动隐藏三态子菜单
        autohide_menu = self._menu.addMenu("自动隐藏")
        apply_qmenu_style(autohide_menu)
        autohide_menu.setProperty(
            "class", "context-menu submenu dark" if GlobalState.is_dark() else "context-menu submenu"
        )

        current_mode = self._get_current_autohide_mode()

        action_off = autohide_menu.addAction("关闭")
        action_off.setCheckable(True)
        action_off.setChecked(current_mode == "off")
        action_off.triggered.connect(self._disable_autohide)

        action_on = autohide_menu.addAction("开启")
        action_on.setCheckable(True)
        action_on.setChecked(current_mode == "on")
        action_on.triggered.connect(self._enable_autohide)

        action_smart = autohide_menu.addAction("智能")
        action_smart.setCheckable(True)
        action_smart.setChecked(current_mode == "smart")
        action_smart.triggered.connect(self._enable_smart_autohide)

        reload_action = self._menu.addAction("重载栏")
        reload_action.triggered.connect(partial(reload_application, "正在从右键菜单重载栏..."))

        exit_action = self._menu.addAction("退出")
        exit_action.triggered.connect(partial(exit_application, "正在从右键菜单退出应用..."))

        self._menu.popup(self.parent.mapToGlobal(position))
        self._menu.activateWindow()

    def _on_menu_about_to_hide(self):
        """Called when the context menu is about to hide - restart autohide timer if enabled"""
        try:
            if (
                hasattr(self.parent, "_autohide_manager")
                and self.parent._autohide_manager
                and self.parent._autohide_manager.is_enabled()
            ):
                manager = self.parent._autohide_manager
                # 普通自动隐藏模式：重启隐藏计时器
                if isinstance(manager, AutoHideManager) and manager._hide_timer:
                    manager._hide_timer.start(manager._autohide_delay)
                # 智能模式：根据当前状态重启对应计时器
                elif isinstance(manager, SmartAutoHideManager) and not manager.is_locked():
                    if self.parent.isVisible():
                        # 栏可见：启动短延迟隐藏
                        if manager._hide_timer:
                            manager._hide_timer.start(manager._autohide_delay)
                    else:
                        # 栏已隐藏：重启锁定倒计时
                        if manager._lock_timer:
                            manager._lock_timer.start(manager._config.get("lock_timeout", 15000))

        except Exception as e:
            logging.error("Failed to restart autohide timer: %s", e)

    def _get_current_autohide_mode(self) -> str:
        """获取当前自动隐藏模式：off / on / smart"""
        if (
            hasattr(self.parent, "_autohide_manager")
            and self.parent._autohide_manager
            and self.parent._autohide_manager.is_enabled()
        ):
            if isinstance(self.parent._autohide_manager, SmartAutoHideManager):
                return "smart"
            return "on"
        return "off"

    def _populate_widgets_menu(self, widgets_menu):
        if not any(self._widgets.get(layout) for layout in ["left", "center", "right"]):
            no_widgets = widgets_menu.addAction("没有活动的组件")
            no_widgets.setEnabled(False)
            return

        for i, layout_type in enumerate(["left", "center", "right"]):
            # Layout header
            layout_names = {"left": "左侧", "center": "中间", "right": "右侧"}
            layout_header = widgets_menu.addAction(f"{layout_names.get(layout_type, layout_type.title())} 布局")
            layout_header.setEnabled(False)

            # Add widgets or empty message
            if self._widgets.get(layout_type):
                for widget in self._widgets[layout_type]:
                    self._add_widget_checkbox(widgets_menu, widget)
            else:
                no_widgets = widgets_menu.addAction("  没有活动的组件")
                no_widgets.setEnabled(False)
            # Add separator after each layout except the last one
            if i < 2:
                widgets_menu.addSeparator()

    def _add_widget_checkbox(self, menu, widget):
        checkbox = QCheckBox(self._get_widget_display_name(widget))
        checkbox.setChecked(widget.isVisible())
        checkbox.setProperty("class", "checkbox")
        checkbox.stateChanged.connect(partial(self._toggle_widget, widget))

        # Container with hover effects
        container = QWidget()
        container.setProperty("class", "menu-checkbox")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(checkbox)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Event filter for hover and click
        def event_filter(obj, event):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                checkbox.toggle()
                return True
            return False

        container.installEventFilter(container)
        container.eventFilter = event_filter

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)

    def _toggle_widget(self, widget, enabled):
        try:
            # Add a flag to track manual visibility override
            widget._manual_visibility_override = not enabled
            widget.setVisible(bool(enabled))

            # Store the original show/hide methods if not already stored
            if not hasattr(widget, "_original_show"):
                widget._original_show = widget.show
                widget._original_hide = widget.hide

            # Override show method to respect manual override
            def controlled_show():
                if not getattr(widget, "_manual_visibility_override", False):
                    widget._original_show()

            def controlled_hide():
                widget._original_hide()

            widget.show = controlled_show
            widget.hide = controlled_hide

        except Exception as e:
            logging.error("Failed to toggle widget %s: %s", self._get_widget_display_name(widget), e)

    def _get_widget_display_name(self, widget):
        for layout_type, widget_list in self._widgets.items():
            try:
                index = widget_list.index(widget)
                if (
                    self._widget_config_map
                    and layout_type in self._widget_config_map
                    and index < len(self._widget_config_map[layout_type])
                ):
                    return self._widget_config_map[layout_type][index].replace("_", " ").title()
            except ValueError:
                continue
        return str(widget)

    def _open_task_manager(self):
        try:
            subprocess.Popen("taskmgr", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            logging.error("Failed to open Task Manager: %s", e)

    def _take_screenshot(self):
        """Take a screenshot of the bar with proper padding"""
        try:
            # Get bar and screen geometries
            bar_geometry = self.parent.geometry()
            screen = self.parent.screen()
            screen_geometry = screen.geometry()

            # Get bar padding information
            bar_padding = getattr(self.parent, "_padding", {"top": 0, "bottom": 0, "left": 0, "right": 0})
            bar_alignment = getattr(self.parent, "_alignment", {"position": "top"})

            # Calculate screenshot area with padding
            padding_top = bar_padding.get("top", 0)
            padding_area = 10

            if bar_alignment["position"] == "top":
                # For top bar: start from screen top (y=0) and extend to bar bottom + padding
                screenshot_x = screen_geometry.x()
                screenshot_y = screen_geometry.y()
                screenshot_width = screen_geometry.width()
                screenshot_height = (bar_geometry.y() - screen_geometry.y()) + bar_geometry.height() + padding_area
            else:
                # For bottom bar: start from bar top - padding and extend to screen bottom
                screenshot_x = screen_geometry.x()
                screenshot_y = bar_geometry.y() - padding_top
                screenshot_width = screen_geometry.width()
                screenshot_height = (screen_geometry.y() + screen_geometry.height()) - screenshot_y

            # Take screenshot of the calculated area
            screenshot = screen.grabWindow(
                0,  # Desktop window
                screenshot_x,
                screenshot_y,
                screenshot_width,
                screenshot_height,
            )

            # Create screenshots directory if it doesn't exist
            screenshots_dir = os.path.join(os.path.expanduser("~"), "Pictures", "YASB_Screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"yasb_bar_{self._bar_name}_{timestamp}.png"
            filepath = os.path.join(screenshots_dir, filename)

            # Save the screenshot
            if not screenshot.save(filepath, "PNG"):
                logging.error("Failed to save screenshot")

            self._screenshot_flash()

        except Exception as e:
            logging.error("Failed to take screenshot: %s", e)

    def _screenshot_flash(self):
        """Create a flashing effect on the bar when taking screenshot"""
        try:
            opacity_effect = QGraphicsOpacityEffect()
            self.parent.setGraphicsEffect(opacity_effect)

            self.flash_animation = QPropertyAnimation(opacity_effect, b"opacity")
            self.flash_animation.setDuration(200)
            self.flash_animation.setStartValue(0.2)
            self.flash_animation.setKeyValueAt(0.25, 1.0)
            self.flash_animation.setKeyValueAt(0.5, 0.2)
            self.flash_animation.setEndValue(1.0)

            self.flash_animation.finished.connect(lambda: self.parent.setGraphicsEffect(None))
            self.flash_animation.start()

        except Exception as e:
            logging.error("Failed to create flash effect: %s", e)

    def _enable_autohide(self):
        """启用普通自动隐藏功能"""
        try:
            # 如果当前是智能模式，先清理
            if (
                hasattr(self.parent, "_autohide_manager")
                and self.parent._autohide_manager
                and isinstance(self.parent._autohide_manager, SmartAutoHideManager)
            ):
                self.parent._autohide_manager.cleanup()
                self.parent._autohide_manager = None

            if not hasattr(self.parent, "_autohide_manager") or not self.parent._autohide_manager:
                self.parent._autohide_manager = AutoHideManager(self.parent, self.parent)

            if not self.parent._autohide_manager.is_enabled():
                self.parent._autohide_manager.setup_autohide()

        except Exception as e:
            logging.error("Failed to enable autohide: %s", e)

    def _enable_smart_autohide(self):
        """启用智能自动隐藏功能"""
        try:
            # 如果当前是普通模式，先清理
            if (
                hasattr(self.parent, "_autohide_manager")
                and self.parent._autohide_manager
                and isinstance(self.parent._autohide_manager, AutoHideManager)
            ):
                self.parent._autohide_manager.cleanup()
                self.parent._autohide_manager = None

            if not hasattr(self.parent, "_autohide_manager") or not self.parent._autohide_manager:
                smart_config = (
                    self.parent.config.window_flags.smart_auto_hide.model_dump()
                    if hasattr(self.parent, "config")
                    else {}
                )
                self.parent._autohide_manager = SmartAutoHideManager(self.parent, smart_config, self.parent)

            if not self.parent._autohide_manager.is_enabled():
                self.parent._autohide_manager.setup()

        except Exception as e:
            logging.error("Failed to enable smart autohide: %s", e)

    def _disable_autohide(self):
        """禁用自动隐藏功能（普通和智能模式）"""
        try:
            if hasattr(self.parent, "_autohide_manager") and self.parent._autohide_manager:
                self.parent._autohide_manager.cleanup()
                self.parent._autohide_manager = None

            # Ensure bar is visible after disabling autohide
            if not self.parent.isVisible():
                self.parent.show()

        except Exception as e:
            logging.error("Failed to disable autohide: %s", e)


class AutoWidthManager(QObject):
    """Manages auto-width calculation and resize/reposition for bars with width='auto'."""

    def __init__(self, bar_widget: QWidget, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget
        self._current_auto_width = 0

    def update(self) -> int:
        """Calculate current auto width from the layout size hint. Returns the new width."""
        layout = self.bar_widget._bar_frame.layout()
        if layout:
            layout.activate()

        requested = max(self.bar_widget._bar_frame.sizeHint().width(), 0)
        available = (
            self.bar_widget._target_screen.geometry().width()
            - self.bar_widget._padding["left"]
            - self.bar_widget._padding["right"]
        )
        new_width = min(requested, available)
        self._current_auto_width = new_width
        return new_width

    def apply(self, new_width: int) -> None:
        """Resize and reposition the bar using the supplied auto width."""
        if new_width < 0:
            return

        bar_height = self.bar_widget._dimensions["height"]
        screen_geometry = self.bar_widget._target_screen.geometry()
        bar_x, bar_y = self.bar_widget.bar_pos(
            new_width,
            bar_height,
            screen_geometry.width(),
            screen_geometry.height(),
        )

        self.bar_widget.setGeometry(bar_x, bar_y, new_width, bar_height)
        self.bar_widget._bar_frame.setGeometry(0, 0, new_width, bar_height)

    def sync(self) -> None:
        """Ensure auto width matches the layout after a DPI/geometry change."""
        previous_width = self._current_auto_width
        new_width = self.update()

        if new_width != previous_width or self.bar_widget.width() != new_width:
            self.apply(new_width)


class BarCliManager(QObject):
    """Handles CLI show/hide/toggle commands for a bar, including app bar reservation management."""

    def __init__(self, bar_widget: QWidget, parent=None):
        super().__init__(parent)
        self.bar_widget = bar_widget

    def handle(self, action: str, screen_name: str) -> None:
        current_screen_matches = not screen_name or self.bar_widget._target_screen.name() == screen_name
        if not current_screen_matches:
            return

        autohide_active = self.bar_widget._autohide_manager and self.bar_widget._autohide_manager.is_enabled()
        manages_app_bar = self.bar_widget._window_flags["windows_app_bar"] and not autohide_active

        if action == "show":
            self.bar_widget.show()
            if manages_app_bar:
                SystrayAppBarHelper.execute_without_systray_interference(self.bar_widget.update_app_bar)
        elif action == "hide":
            if manages_app_bar:
                SystrayAppBarHelper.execute_without_systray_interference(self.bar_widget.try_remove_app_bar)
            self.bar_widget.hide()
        elif action == "toggle":
            if self.bar_widget.isVisible():
                if manages_app_bar:
                    SystrayAppBarHelper.execute_without_systray_interference(self.bar_widget.try_remove_app_bar)
                self.bar_widget.hide()
            else:
                self.bar_widget.show()
                if manages_app_bar:
                    SystrayAppBarHelper.execute_without_systray_interference(self.bar_widget.update_app_bar)
