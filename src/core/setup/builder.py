from yaml import dump as yaml_dump

from core.setup.bar_config import CONFIG_HEADER, ROOT_BAR, ROOT_CONFIG, ROOT_STYLE
from core.setup.widgets_config import WIDGETS_CONFIG
from core.setup.widgets_styles import WIDGET_STYLES

WINDOW_MANAGER_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("komorebi", "Komorebi", "工作区切换器，支持每个工作区的应用图标与滚动切换"),
    ("glazewm", "GlazeWM", "工作区切换器——点击切换，滚动循环工作区"),
    ("windows_desktops", "虚拟桌面", "Windows 原生桌面——切换、重命名、新建和删除"),
)
OPTIONAL_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("cpu", "CPU", "实时 CPU 占用，带直方图与弹出图表"),
    ("memory", "内存", "RAM 占用百分比与可用内存显示"),
    ("quick_launch", "快速启动", "Spotlight 式搜索，可查找应用、文件等"),
    ("active_window", "活动窗口", "当前焦点窗口的标题与图标"),
    ("systray", "系统托盘", "直接固定在状态栏上的系统托盘图标"),
    ("weather", "天气", "通过 Open-Meteo 获取 7 天预报，无需 API 密钥"),
    ("github", "GitHub", "未读数量，弹窗按仓库和类型分组"),
    ("microphone", "麦克风", "麦克风静音与输入电平，滚动调节音量"),
    ("media", "媒体", "正在播放的曲目，带弹出式播放控制"),
)
FEATURE_GROUPS: tuple[tuple[str, str, str], ...] = (*OPTIONAL_GROUPS,)

# Groups written when the user skips the wizard
DEFAULT_GROUPS = ["base", "active_window"]


def build_config(selected_groups: list[str] | None = None, bar_overrides: dict | None = None) -> str:
    if selected_groups is None:
        selected_groups = DEFAULT_GROUPS
    if "base" not in selected_groups:
        selected_groups = ["base", *selected_groups]

    all_widgets: dict = {}
    all_placements: dict = {}

    for group_name in selected_groups:
        preset = WIDGETS_CONFIG[group_name]
        all_widgets.update(preset["config"])
        all_placements.update(preset["placement"])

    left: list[str] = []
    center: list[str] = []
    right: list[str] = []
    section_map = {"left": left, "center": center, "right": right}

    for widget_name, (section, _) in sorted(all_placements.items(), key=lambda x: x[1][1]):
        section_map.get(section, left).append(widget_name)

    config: dict = {**ROOT_CONFIG}

    bar: dict = {
        **ROOT_BAR,
        "alignment": dict(ROOT_BAR["alignment"]),
        "padding": dict(ROOT_BAR["padding"]),
        "animation": dict(ROOT_BAR["animation"]),
        "blur_effect": dict(ROOT_BAR["blur_effect"]),
    }
    if bar_overrides:
        if "screens" in bar_overrides:
            bar["screens"] = bar_overrides["screens"]
        if "bar_style" in bar_overrides:
            if bar_overrides["bar_style"] == "floating":
                bar["padding"] = {"top": 4, "left": 4, "bottom": 0, "right": 4}
                bar["blur_effect"]["round_corners"] = True
                bar["blur_effect"]["round_corners_type"] = "normal"
                bar["blur_effect"]["border_color"] = "system"
            else:
                bar["padding"] = {"top": 0, "left": 0, "bottom": 0, "right": 0}
                bar["blur_effect"]["round_corners"] = False
        if "blur_enabled" in bar_overrides:
            bar["blur_effect"]["enabled"] = bar_overrides["blur_enabled"]

    config["bars"] = {
        "primary-bar": {
            **bar,
            "widgets": {"left": left, "center": center, "right": right},
        },
    }

    config["widgets"] = all_widgets

    yaml_body = yaml_dump(config, default_flow_style=False, sort_keys=False, allow_unicode=False)

    return CONFIG_HEADER + yaml_body


def build_styles(
    selected_groups: list[str] | None = None,
    bar_opacity: int = 100,
    bar_style: str = "taskbar",
) -> str:
    if selected_groups is None:
        selected_groups = DEFAULT_GROUPS
    if "base" not in selected_groups:
        selected_groups = ["base", *selected_groups]

    alpha = max(0.01, max(0, min(100, bar_opacity)) / 100)
    bg = f"rgba(36, 36, 36, {alpha:.2f})"
    root_style = ROOT_STYLE.replace("--yasb-bar-bg: rgba(36, 36, 36, 0.60);", f"--yasb-bar-bg: {bg};")
    root_style = root_style.replace("--yasb-popup-bg: rgba(36, 36, 36, 0.60);", f"--yasb-popup-bg: {bg};")
    if bar_style == "taskbar":
        root_style = root_style.replace(
            "    background-color: var(--yasb-bar-bg);\n",
            "    background-color: var(--yasb-bar-bg);\n    border-bottom: 1px solid var(--yasb-bar-border);\n",
        )

    parts = [root_style]

    for group_name in selected_groups:
        style = WIDGET_STYLES.get(group_name, "")
        if style:
            parts.append(style)

    return "\n".join(parts)
