from core.utils.shell_utils import shell_open
from core.widgets.services.quick_launch.base_provider import (
    BaseProvider,
    ProviderMenuAction,
    ProviderMenuActionResult,
    ProviderResult,
)
from core.widgets.services.quick_launch.providers.resources.icons import ICON_EXAMPLE


class ExampleProvider(BaseProvider):
    """A tiny provider that searches a hardcoded list and opens URLs.

    Activate with the prefix (default ``#``), e.g. ``# docs`` or ``# github``.
    """

    # Required class attributes
    name = "example"  # unique key - must match the config key
    display_name = "示例"  # shown on the home page shortcut
    icon = ICON_EXAMPLE  # inline SVG shown on the home page tile

    # Optional class attributes
    input_placeholder = "搜索示例..."  # placeholder when prefix is active

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # After super().__init__() you get for free:
        #   self.config   – raw dict from the YAML config
        #   self.prefix   – prefix string, or None when set to "*"
        #   self.priority – sort weight (lower = higher in the list)

        # A simple hardcoded data source. Yours could be a file, API, DB, etc.
        self._items = [
            {
                "title": "YASB Documentation",
                "description": "官方维基与指南",
                "url": "https://github.com/amnweb/yasb/wiki",
            },
            {
                "title": "YASB GitHub Repository",
                "description": "源代码与问题反馈",
                "url": "https://github.com/amnweb/yasb",
            },
            {
                "title": "Python Documentation",
                "description": "Python 官方文档",
                "url": "https://docs.python.org/3/",
            },
        ]

    # Required: get_results
    # Runs on a BACKGROUND THREAD - never touch Qt widgets here.
    # **kwargs is required; the service passes cancel_event through it.
    def get_results(self, text: str, **kwargs) -> list[ProviderResult]:
        query = self.get_query_text(text).lower()

        # No query -> show a friendly hint
        if not query:
            return [
                ProviderResult(
                    title="示例提供程序",
                    description="输入内容进行搜索",
                    icon_char=ICON_EXAMPLE,
                    provider=self.name,
                )
            ]

        # Filter the list
        results: list[ProviderResult] = []
        for item in self._items:
            if query in item["title"].lower() or query in item["description"].lower():
                results.append(
                    ProviderResult(
                        title=item["title"],
                        description=item["description"],
                        icon_char=ICON_EXAMPLE,
                        provider=self.name,
                        action_data={"url": item["url"]},
                    )
                )
        return results

    # Required: execute
    # Called when the user selects a result (Enter or click).
    # Return True  -> close the popup
    # Return False -> keep the popup open and refresh results
    # Return None  -> do nothing (useful for inline edit forms)
    def execute(self, result: ProviderResult) -> bool | None:
        url = result.action_data.get("url", "")
        if url:
            shell_open(url)
            return True
        return False

    # Optional: context menu
    # Right-click menu on a result. Skip these two methods if you don't need one.
    def get_context_menu_actions(self, result: ProviderResult) -> list[ProviderMenuAction]:
        url = result.action_data.get("url", "")
        if not url:
            return []
        return [
            ProviderMenuAction(id="open_url", label="在浏览器中打开"),
            ProviderMenuAction(id="copy_url", label="复制链接"),
        ]

    def execute_context_menu_action(self, action_id: str, result: ProviderResult) -> ProviderMenuActionResult:
        url = result.action_data.get("url", "")
        if action_id == "open_url" and url:
            shell_open(url)
            return ProviderMenuActionResult(close_popup=True)
        if action_id == "copy_url" and url:
            from PyQt6.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(url)
            return ProviderMenuActionResult()
        return ProviderMenuActionResult()
