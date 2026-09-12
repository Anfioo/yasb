from typing import Literal

from pydantic import Field, field_validator

from core.validation.widgets.base_model import CustomBaseModel


class BarAlignment(CustomBaseModel):
    position: Literal["top", "bottom"] = "top"
    align: Literal["left", "center", "right"] = "center"


class BarBlurEffect(CustomBaseModel):
    enabled: bool = False
    dark_mode: bool = False
    round_corners: bool = False
    round_corners_type: Literal["normal", "small"] = "normal"
    border_color: str = "System"


class BarAnimation(CustomBaseModel):
    enabled: bool = True
    duration: int = Field(default=500, ge=0)
    type: Literal["slide", "fade"] = "slide"


class SmartAutoHideConfig(CustomBaseModel):
    """智能自动隐藏配置：锁定时仅显示锁图标，悬停进度满后解锁显示完整栏。"""

    unlock_hover_duration: int = Field(default=500, ge=100, le=5000, description="悬停解锁所需毫秒数")
    lock_timeout: int = Field(default=15000, ge=1000, le=300000, description="鼠标离开后多少毫秒重新锁定")
    lock_icon: str = Field(default="\uf023", description="锁定状态显示的图标字符")
    indicator_size: int = Field(default=28, ge=16, le=64, description="锁图标指示器尺寸（像素）")
    progress_color: str = Field(default="#ffffff", description="解锁进度环颜色")
    progress_background_color: str = Field(default="#555555", description="进度环背景颜色")
    progress_thickness: int = Field(default=3, ge=1, le=8, description="进度环粗细（像素）")
    indicator_opacity: float = Field(default=0.6, ge=0.1, le=1.0, description="锁定时指示器不透明度")


class BarWindowFlags(CustomBaseModel):
    always_on_top: bool = False
    windows_app_bar: bool = False
    hide_on_fullscreen: bool = False
    hide_on_maximized: bool = False
    auto_hide: Literal["off", "on", "smart"] = "off"
    smart_auto_hide: SmartAutoHideConfig = SmartAutoHideConfig()

    @field_validator("auto_hide", mode="before")
    @classmethod
    def _coerce_auto_hide(cls, v):
        """兼容旧配置：true/false 布尔值自动转换为 on/off。"""
        if isinstance(v, bool):
            return "on" if v else "off"
        return v


class BarDimensions(CustomBaseModel):
    width: str | int = "100%"
    height: int = Field(default=30, ge=0)

    @field_validator("width")
    @classmethod
    def validate_width(cls, v: str | int) -> str | int:
        if isinstance(v, int):
            if v < 0:
                raise ValueError("宽度不能为负数")
            return v
        if v == "auto":
            return v
        if v.endswith("%") and v[:-1].isdigit():
            return v
        raise ValueError("宽度必须是整数、'auto'，或百分比字符串（例如 '100%'）")


class BarPadding(CustomBaseModel):
    top: int = 0
    left: int = 0
    bottom: int = 0
    right: int = 0


class BarWidgets(CustomBaseModel):
    left: list[str] = []
    center: list[str] = []
    right: list[str] = []


class BarLayout(CustomBaseModel):
    alignment: Literal["left", "center", "right"] = "left"
    stretch: bool = True


class BarLayouts(CustomBaseModel):
    left: BarLayout = BarLayout(alignment="left")
    center: BarLayout = BarLayout(alignment="center")
    right: BarLayout = BarLayout(alignment="right")


class BarConfig(CustomBaseModel):
    enabled: bool = True
    screens: list[str] = ["*"]
    class_name: str = "yasb-bar"
    style: Literal["bar", "adaptive"] = "bar"
    style_adaptive_exclude: list[str] = []
    context_menu: bool = True
    alignment: BarAlignment = BarAlignment()
    blur_effect: BarBlurEffect = BarBlurEffect()
    animation: BarAnimation = BarAnimation()
    window_flags: BarWindowFlags = BarWindowFlags()
    dimensions: BarDimensions = BarDimensions()
    padding: BarPadding = BarPadding()
    widgets: BarWidgets = BarWidgets()
    layouts: BarLayouts = BarLayouts()
