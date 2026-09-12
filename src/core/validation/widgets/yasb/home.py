from core.validation.widgets.base_model import (
    CallbacksConfig,
    CustomBaseModel,
    KeybindingConfig,
)


class MenuItemConfig(CustomBaseModel):
    title: str | None = None
    path: str | None = None
    uri: str | None = None
    command: str | None = None
    separator: bool | None = None
    args: list[str] | None = None
    shell: bool | None = None
    show_window: bool | None = None


class MenuLabelsConfig(CustomBaseModel):
    shutdown: str = "关机"
    restart: str = "重启"
    hibernate: str = "休眠"
    logout: str = "注销"
    lock: str = "锁定"
    sleep: str = "睡眠"
    system: str = "系统设置"
    about: str = "关于此电脑"
    task_manager: str = "任务管理器"


class CallbacksHomeConfig(CallbacksConfig):
    on_left: str = "toggle_menu"


class HomeConfig(CustomBaseModel):
    label: str = "\ue71a"
    menu_list: list[MenuItemConfig] | None = None
    power_menu: bool = True
    system_menu: bool = True
    blur: bool = False
    round_corners: bool = True
    round_corners_type: str = "normal"
    border_color: str = "System"
    alignment: str = "left"
    direction: str = "down"
    offset_top: int = 6
    offset_left: int = 0
    menu_labels: MenuLabelsConfig = MenuLabelsConfig()
    keybindings: list[KeybindingConfig] = []
    callbacks: CallbacksHomeConfig = CallbacksHomeConfig()
