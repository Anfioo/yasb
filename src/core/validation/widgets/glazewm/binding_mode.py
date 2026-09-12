from core.validation.widgets.base_model import (
    CallbacksConfig,
    CustomBaseModel,
    KeybindingConfig,
)


class GlazewmBindingModeCallbacksConfig(CallbacksConfig):
    on_left: str = "next_binding_mode"
    on_middle: str = "toggle_label"
    on_right: str = "disable_binding_mode"


class GlazewmBindingModeConfig(CustomBaseModel):
    label: str = "<span>{icon}</span> {binding_mode}"
    label_alt: str = "<span>{icon}</span> 当前模式：{binding_mode}"
    glazewm_server_uri: str = "ws://localhost:6123"
    hide_if_no_active: bool = True
    label_if_no_active: str = "无活动绑定模式"
    default_icon: str = "\uf071"
    icons: dict[str, str] = {
        "none": "",
        "resize": "\uf071",
        "pause": "\uf28c",
    }
    binding_modes_to_cycle_through: list[str] = [
        "none",
        "resize",
        "pause",
    ]
    keybindings: list[KeybindingConfig] = []
    callbacks: GlazewmBindingModeCallbacksConfig = GlazewmBindingModeCallbacksConfig()
