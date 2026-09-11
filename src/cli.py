"""
YASB CLI

NOTE: Avoid importing heavy libraries directly to avoid slowing down the startup time.

To check the startup time, use the following commands (from venv):
python -X importtime src/cli.py 2> import_times.log
pip install tuna
tuna import_times.log
"""

import argparse
import ctypes
import datetime
import getpass
import json
import os
import subprocess
import sys
import textwrap
import time
import winreg
from ctypes import GetLastError

from win32con import (
    GENERIC_READ,
    GENERIC_WRITE,
    OPEN_EXISTING,
)

from core.utils.process import is_process_running
from core.utils.win32.bindings import (
    CloseHandle,
    CreateFile,
    ReadFile,
    WriteFile,
)
from core.utils.win32.constants import INVALID_HANDLE_VALUE
from settings import APP_NAME, BUILD_VERSION, CLI_VERSION, DEFAULT_CONFIG_DIRECTORY, RELEASE_CHANNEL, SCRIPT_PATH

BUFSIZE = 65536
YASB_VERSION = BUILD_VERSION
YASB_CLI_VERSION = CLI_VERSION
YASB_RELEASE_CHANNEL = RELEASE_CHANNEL

EXE_PATH = os.path.join(SCRIPT_PATH, "yasb.exe")
AUTOSTART_FILE = EXE_PATH if os.path.exists(EXE_PATH) else None

CLI_SERVER_PIPE_NAME = r"\\.\pipe\yasb_pipe_cli"
LOG_SERVER_PIPE_NAME = r"\\.\pipe\yasb_pipe_log"


def write_message(handle: int, msg_dict: dict[str, str]):
    try:
        data = json.dumps(msg_dict).encode("utf-8")
    except Exception as e:
        print(f"JSON 编码错误：{e}")
        print(f"Data: {msg_dict}")
        return False
    success = WriteFile(handle, data)
    return success


def read_message(handle: int) -> dict[str, str] | None:
    success, data = ReadFile(handle, BUFSIZE)
    if not success or len(data) == 0:
        return None
    try:
        messages: list[str] = []
        # This is needed in case there are multiple json objects in one data block
        for line in data.split(b"\0"):
            if not line.strip():
                continue
            json_object = json.loads(line.decode().strip())
            if json_object.get("type") == "DATA":
                messages.append(json_object.get("data"))
            else:
                # If it's ping/pong, just return the object as is
                return json_object
        return {"type": "DATA", "data": "\n".join(messages)}
    except json.JSONDecodeError as e:
        print(f"JSON 解码错误：{e}")
        print(f"Data: {data}")
        return None


class Format:
    reset = "\033[0m"
    green = "\033[92m"
    yellow = "\033[93m"
    red = "\033[91m"
    red_bg = "\033[41m"
    gray = "\033[90m"
    blue = "\033[94m"
    cyan = "\033[96m"
    magenta = "\033[95m"
    underline = "\033[4m"


class CustomArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("suggest_on_error", True)
        super().__init__(*args, **kwargs)

    def error(self, message: str):
        print(f"\n{Format.red}错误:{Format.reset} {message}\n")
        sys.exit(2)


class CLIHandler:
    """Handles the command-line interface for the application."""

    def __init__(self):
        self.task_handler = CLITaskHandler()
        self.update_handler = CLIUpdateHandler()
        self.channel_handler = CLIChannelHandler()
        self.crash_dump_handler = CLICrashDumpHandler()

    def send_command_to_application(self, command: str):
        """
        Send a command to the running YASB application through the pipe.

        Commands can be:
        - "stop" - Stop the application
        - "reload" - Reload the application
        - "show-bar [screen]" - Show the bar on a specific screen
        - "hide-bar [screen]" - Hide the bar on a specific screen
        - "toggle-bar [screen]" - Toggle the bar on a specific screen

        Args:
            command: The command to send
        """
        try:
            pipe_handle = CreateFile(
                CLI_SERVER_PIPE_NAME,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if pipe_handle == INVALID_HANDLE_VALUE:
                print("无法连接到 YASB。未找到管道，程序可能未在运行。")
                return

            # Send the command as bytes
            command_bytes = command.encode("utf-8")
            success = WriteFile(pipe_handle, command_bytes)
            if not success:
                print(f"写入命令失败。错误码：{GetLastError()}")
                CloseHandle(pipe_handle)
                return

            success, response = ReadFile(pipe_handle, 64 * 1024)
            if not success or len(response) == 0:
                print(f"读取响应失败。错误码：{GetLastError()}")
                CloseHandle(pipe_handle)
                return

            response_text = response.decode("utf-8").strip()
            if response_text != "ACK":
                print(f"收到意外响应：{response_text}")

            CloseHandle(pipe_handle)
        except Exception as e:
            print(f"错误：{e}")

    def _open_startup_registry(self, access_flag: int):
        """Helper function to open the startup registry key."""
        registry_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, access_flag)

    def is_autostart_enabled(self, app_name: str) -> bool:
        """Check if application is in Windows startup."""
        try:
            with self._open_startup_registry(winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"检查 {app_name} 的开机自启状态失败：{e}")
            return False

    def enable_startup(self):
        if self.is_autostart_enabled(APP_NAME):
            print(f"{APP_NAME} 已设置为开机自启。")
            return
        try:
            with self._open_startup_registry(winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f"{AUTOSTART_FILE}")
            print(f"{APP_NAME} 已添加到开机自启。")
        except Exception as e:
            print(f"添加 {APP_NAME} 到开机自启失败：{e}")

    def disable_startup(self):
        try:
            with self._open_startup_registry(winreg.KEY_ALL_ACCESS) as key:
                winreg.DeleteValue(key, APP_NAME)
            print(f"{APP_NAME} 已从开机自启中移除。")
        except FileNotFoundError:
            print(f"未找到 {APP_NAME} 的开机自启项。")
        except Exception as e:
            print(f"移除 {APP_NAME} 的开机自启失败：{e}")

    def parse_arguments(self):
        parser = CustomArgumentParser(
            description="YASB Reborn 的命令行界面。",
            add_help=False,
            prog="yasbc",
        )
        subparsers = parser.add_subparsers(
            dest="command",
            help="命令",
        )

        start_parser = subparsers.add_parser(
            "start",
            help="启动应用",
            prog="yasbc start",
        )
        start_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="静默输出消息",
        )

        stop_parser = subparsers.add_parser(
            "stop",
            help="停止应用",
            prog="yasbc stop",
        )
        stop_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="静默输出消息",
        )
        stop_parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="强制停止应用",
        )

        reload_parser = subparsers.add_parser(
            "reload",
            help="重载应用",
            prog="yasbc reload",
        )
        reload_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="静默输出消息",
        )

        subparsers.add_parser(
            "update",
            help="更新应用",
            add_help=False,
        )

        enable_autostart_parser = subparsers.add_parser(
            "enable-autostart",
            help="启用开机自启",
            prog="yasbc enable-autostart",
        )
        enable_autostart_parser.add_argument(
            "--task",
            action="store_true",
            help="启用计划任务自启",
        )

        disable_autostart_parser = subparsers.add_parser(
            "disable-autostart",
            help="禁用开机自启",
            prog="yasbc disable-autostart",
        )
        disable_autostart_parser.add_argument(
            "--task",
            action="store_true",
            help="禁用计划任务自启",
        )

        subparsers.add_parser(
            "enable-crash-dumps",
            help="启用崩溃转储以排查问题",
            add_help=False,
        )

        subparsers.add_parser(
            "disable-crash-dumps",
            help="禁用崩溃转储",
            add_help=False,
        )

        subparsers.add_parser(
            "monitor-information",
            help="显示已连接显示器的信息",
            add_help=False,
        )

        show_bar_parser = subparsers.add_parser(
            "show-bar",
            help="在指定屏幕显示状态栏",
            prog="yasbc show-bar",
        )
        show_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="屏幕名称（可选）",
        )

        hide_bar_parser = subparsers.add_parser(
            "hide-bar",
            help="在指定屏幕隐藏状态栏",
            prog="yasbc hide-bar",
        )
        hide_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="屏幕名称（可选）",
        )

        toggle_bar_parser = subparsers.add_parser(
            "toggle-bar",
            help="切换指定屏幕上的状态栏",
            prog="yasbc toggle-bar",
        )
        toggle_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="屏幕名称（可选）",
        )

        # Channel management
        set_channel_parser = subparsers.add_parser(
            "set-channel",
            help="切换发布渠道",
            prog="yasbc set-channel",
        )
        set_channel_parser.add_argument(
            "target_channel",
            type=str,
            choices=["stable", "preview"],
            help="要切换到的渠道：'stable' 为稳定版，'preview' 为最新更新",
        )

        subparsers.add_parser(
            "reset",
            help="恢复默认配置文件并清除缓存",
            add_help=False,
        )

        subparsers.add_parser(
            "config-dir",
            help="在文件资源管理器中打开配置目录",
            add_help=False,
        )

        subparsers.add_parser(
            "help",
            help="显示帮助信息",
            add_help=False,
        )
        subparsers.add_parser(
            "log",
            help="跟踪 yasb 进程日志（按 Ctrl-C 取消）",
            add_help=False,
        )
        subparsers.add_parser(
            "migrate-config",
            help="查找并修复配置中的已弃用选项",
            add_help=False,
        )
        # No arguments and no -h of its own, everything after `cloud` falls through as
        # unrecognised and is handed to core.cloud.cli, which has its own parser.
        subparsers.add_parser(
            "cloud",
            help="使用 YASB Cloud 备份和恢复配置",
            prog="yasbc cloud",
            add_help=False,
        )
        parser.add_argument(
            "-v",
            "--version",
            action="store_true",
            help="显示程序版本号并退出。",
        )
        parser.add_argument(
            "-c",
            "--config",
            action="store_true",
            help="打印配置目录路径",
        )
        parser.add_argument(
            "-h",
            "--help",
            action="store_true",
            help="显示帮助信息",
        )
        args, passthrough = parser.parse_known_args()
        # Only `cloud` is allowed leftovers, every other command stays strict.
        if passthrough and args.command != "cloud":
            parser.error(f"无法识别的参数：{' '.join(passthrough)}")
        if args.command == "start":
            if not args.silent:
                print(
                    textwrap.dedent(f"""\
                    在后台启动 YASB Reborn v{YASB_VERSION}。

                    # 社区
                    * 加入 Discord https://discord.gg/qkeunvBFgX - 聊天、提问、分享你的桌面等...
                    * GitHub 讨论 https://github.com/amnweb/yasb/discussions - 提问、分享你的想法等...

                    # 文档
                    * 阅读文档 https://github.com/amnweb/yasb/wiki - 了解如何配置和使用 YASB
                    * 阅读常见问题（FAQ）https://github.com/amnweb/yasb/wiki/FAQ
                    
                    # 支持项目
                    * 可以考虑在 GitHub Sponsors 或 Buy Me a Coffee 上赞助本项目
                    * 感谢你使用 YASB！
                """)
                )
            subprocess.Popen(["yasb.exe"])
            sys.exit(0)

        elif args.command == "stop":
            if args.force:
                for proc in ["yasb.exe", "yasb_themes.exe"]:
                    if is_process_running(proc):
                        subprocess.run(["taskkill", "/f", "/im", proc], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self.send_command_to_application("stop")
            sys.exit(0)
        elif args.command == "cloud":
            from core.cloud.cli import run as run_cloud

            sys.exit(run_cloud(passthrough))
        elif args.command == "reload":
            if is_process_running("yasb.exe"):
                if not args.silent:
                    print("正在重载 YASB...")
                self.send_command_to_application("reload")
            else:
                print("YASB 未在运行，已中止重载。")
            sys.exit(0)

        elif args.command == "show-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"show-bar{screen_arg}")
            sys.exit(0)

        # For hide-bar command
        elif args.command == "hide-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"hide-bar{screen_arg}")
            sys.exit(0)

        # For toggle-bar command
        elif args.command == "toggle-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"toggle-bar{screen_arg}")
            sys.exit(0)

        elif args.command == "set-channel":
            self.channel_handler.switch_channel(args.target_channel)
            sys.exit(0)

        elif args.command == "update":
            self.update_handler.update_yasb(YASB_VERSION)

        elif args.command == "enable-autostart":
            if args.task:
                if not self.task_handler.is_admin():
                    print("请以管理员身份运行此命令。")
                else:
                    self.task_handler.create_task()
            else:
                self.enable_startup()
            sys.exit(0)

        elif args.command == "disable-autostart":
            if args.task:
                if not self.task_handler.is_admin():
                    print("请以管理员身份运行此命令。")
                else:
                    self.task_handler.delete_task()
            else:
                self.disable_startup()
            sys.exit(0)

        elif args.command == "enable-crash-dumps":
            if not self.task_handler.is_admin():
                print("请以管理员身份运行此命令。")
            else:
                self.crash_dump_handler.enable()
            sys.exit(0)

        elif args.command == "disable-crash-dumps":
            if not self.task_handler.is_admin():
                print("请以管理员身份运行此命令。")
            else:
                self.crash_dump_handler.disable()
            sys.exit(0)

        elif args.command == "log":
            print("正在启动 YASB 日志客户端，按 Ctrl+C 退出。")
            try:
                while True:
                    # Wait for the log pipe to be created
                    while True:
                        handle = CreateFile(
                            LOG_SERVER_PIPE_NAME,
                            GENERIC_READ | GENERIC_WRITE,
                            0,
                            None,
                            OPEN_EXISTING,
                            0,
                            None,
                        )
                        if handle != INVALID_HANDLE_VALUE:
                            break
                        time.sleep(0.1)

                    # Start reading the log stream
                    while True:
                        if not write_message(handle, {"type": "PING"}):
                            print(f"写入 PING 失败。错误码：{GetLastError()}")
                            break
                        for _ in range(2):
                            msg = read_message(handle)
                            if msg is None:
                                print(f"读取消息失败。错误码：{GetLastError()}")
                                break
                            if msg.get("type") == "PONG":
                                break
                            elif msg.get("type") == "DATA":
                                print(msg.get("data"))
            except KeyboardInterrupt:
                print("\n正在退出 YASB 日志客户端。")

        elif args.command == "monitor-information":
            try:
                from PyQt6.QtGui import QGuiApplication
                from PyQt6.QtWidgets import QApplication

                app = QApplication([])

                screens = QGuiApplication.screens()
                primary_screen = QGuiApplication.primaryScreen()

                for i, screen in enumerate(screens, 1):
                    geometry = screen.geometry()
                    print(
                        textwrap.dedent(f"""\
                        {Format.underline}显示器 {i}:{Format.reset}
                          名称: {screen.name()}
                          分辨率: {geometry.width()}x{geometry.height()}
                          位置: ({geometry.left()},{geometry.top()}) 至 ({geometry.left() + geometry.width()},{geometry.top() + geometry.height()})
                          主显示器: {"是" if screen == primary_screen else "否"}
                          缩放因子: {screen.devicePixelRatio():.2f}
                          制造商: {screen.manufacturer() or "未知"}
                          型号: {screen.model() or "未知"}
                    """)
                    )
                app.quit()
            except Exception as e:
                print(f"获取显示器信息失败：{e}")

        elif args.command == "reset":
            confirm = (
                input(
                    "如果 YASB 正在运行，将被停止。\n"
                    "是否继续并恢复默认配置文件、清除缓存？(Y/n): "
                )
                .strip()
                .lower()
            )

            if confirm not in ["y", "yes", ""]:
                print("已取消重置。")
                sys.exit(0)

            import shutil
            from pathlib import Path

            # Determine config path

            config_path = Path(DEFAULT_CONFIG_DIRECTORY)

            # Stop YASB if it is running
            for proc in ["yasb.exe", "yasb_themes.exe"]:
                if is_process_running(proc):
                    subprocess.run(["taskkill", "/f", "/im", proc], creationflags=subprocess.CREATE_NO_WINDOW)

            # Delete styles.css and config.yaml if they exist
            for fname in ["styles.css", "config.yaml"]:
                fpath = config_path / fname
                if fpath.exists():
                    try:
                        fpath.unlink()
                        print(f"已删除 {fpath}")
                    except Exception as e:
                        print(f"删除 {fpath} 失败：{e}")

            # Clear all files in app_data_folder if it exists
            import tempfile

            from core.utils.system import app_data_path

            app_data_folder = app_data_path()
            if app_data_folder.exists() and app_data_folder.is_dir():
                for child in app_data_folder.iterdir():
                    try:
                        if child.is_file() or child.is_symlink():
                            child.unlink()
                            print(f"已删除 {child}")
                        elif child.is_dir():
                            shutil.rmtree(child)
                            print(f"已删除文件夹 {child}")
                    except Exception as e:
                        print(f"删除 {child} 失败：{e}")

            icons_cache = Path(tempfile.gettempdir()) / "yasb_quick_launch_icons"
            if icons_cache.exists() and icons_cache.is_dir():
                try:
                    shutil.rmtree(icons_cache)
                    print(f"已删除文件夹 {icons_cache}")
                except Exception as e:
                    print(f"删除 {icons_cache} 失败：{e}")

            print("重置完成。")
            sys.exit(0)

        elif args.command == "config-dir":
            try:
                subprocess.Popen(["explorer", DEFAULT_CONFIG_DIRECTORY])
            except Exception as e:
                print(f"打开配置目录失败：{e}")
            sys.exit(0)

        elif args.command == "migrate-config":
            from pathlib import Path

            from core.validation.deprecation import migrate_config

            config_path = Path(DEFAULT_CONFIG_DIRECTORY) / "config.yaml"
            if not config_path.exists():
                print(f"未找到配置文件：{config_path}")
                sys.exit(1)

            try:
                raw = config_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"读取配置失败：{e}")
                sys.exit(1)

            new_text, changes = migrate_config(raw)
            if not changes:
                print("未发现已弃用选项，你的配置是最新的。")
                sys.exit(0)

            print(f"\n在你的配置中发现 {len(changes)} 个已弃用选项：\n")
            for change in changes:
                if change["action"] == "remove":
                    print(f"  {Format.yellow}{change['path']}{Format.reset}")
                    print(f"    将被移除。{change['message']}")
                elif change["action"] == "rename":
                    print(
                        f"  {Format.yellow}{change['path']}{Format.reset} -> {Format.green}{change['new_name']}{Format.reset}"
                    )
                    print(f"    将被重命名。{change['message']}")
                print()

            confirm = input("是否应用更改？(Y/n): ").strip().lower()
            if confirm not in ["y", "yes", ""]:
                print("迁移已取消。")
                sys.exit(0)

            backup_path = config_path.with_suffix(".yaml.bak")
            try:
                backup_path.write_text(raw, encoding="utf-8")
                print(f"备份已保存到 {backup_path}")
            except Exception as e:
                print(f"创建备份失败：{e}")
                sys.exit(1)

            try:
                config_path.write_text(new_text, encoding="utf-8")
                print(f"配置迁移成功。已更新 {len(changes)} 个选项。")
            except Exception as e:
                print(f"写入配置失败：{e}")
                sys.exit(1)
            sys.exit(0)

        elif args.config:
            print(DEFAULT_CONFIG_DIRECTORY)
            sys.exit(0)

        elif args.command == "help" or args.help:
            print(
                textwrap.dedent(f"""\
                YASB Reborn 的命令行界面。

                {Format.underline}用法{Format.reset}: yasbc <COMMAND>

                {Format.underline}命令{Format.reset}:
                  start                     启动应用
                  stop                      停止应用
                  reload                    重载应用
                  enable-autostart          启用系统开机自启
                  disable-autostart         禁用系统开机自启
                  enable-crash-dumps        启用崩溃转储以排查问题
                  disable-crash-dumps       禁用崩溃转储
                  monitor-information       显示已连接显示器的信息
                  show-bar                  在所有或指定屏幕显示状态栏
                  hide-bar                  在所有或指定屏幕隐藏状态栏
                  toggle-bar                在所有或指定屏幕切换状态栏
                  set-channel               切换发布渠道（stable、preview）
                  update                    更新应用
                  log                       跟踪 yasb 进程日志（按 Ctrl-C 取消）
                  reset                     恢复默认配置文件并清除缓存
                  cloud                     使用 YASB Cloud 备份和恢复配置
                  config-dir                在文件资源管理器中打开配置目录
                  migrate-config            查找并修复配置中的已弃用选项
                  help                      打印此消息

                {Format.underline}选项{Format.reset}:
                -v, --version  显示版本
                -c, --config   打印配置目录路径
                -h, --help     打印此消息
            """)
            )
            sys.exit(0)

        elif args.version:
            from core.utils.system import get_architecture

            architecture = get_architecture()
            arch_suffix = f" {architecture}" if architecture else ""
            version_message = (
                f"YASB Reborn v{YASB_VERSION}{arch_suffix} ({YASB_RELEASE_CHANNEL})\nYASB-CLI v{YASB_CLI_VERSION}"
            )
            print(version_message)
        else:
            print("未知命令，使用 --help 查看可用选项。")
            sys.exit(1)


class CLICrashDumpHandler:
    """Turn Windows crash dumps for yasb.exe on or off.

    Windows logs crashes to the Event Viewer but doesn't save a dump file unless
    you ask it to, so there is usually nothing left to debug after a native crash.

    https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps
    """

    PARENT_KEY_PATH = "SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting\\LocalDumps"
    KEY_PATH = PARENT_KEY_PATH + "\\yasb.exe"
    DUMP_FOLDER = os.path.join(DEFAULT_CONFIG_DIRECTORY, "dumps")
    # Minidump missing some information, so we use a custom dump type with the following flags.
    # See https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps#custom-dump-flags
    _WITH_DATA_SEGS = 0x0001  # module globals                        (WER default)
    _WITH_HANDLE_DATA = 0x0004  # handle table, so !handle works
    _WITH_UNLOADED_MODULES = 0x0020  # catches DLL-unload races        (WER default)
    _WITH_INDIRECT_MEMORY = 0x0040  # heap reachable from registers/stack
    _WITH_PROCESS_THREAD_DATA = 0x0100  # PEB/TEB                      (WER default)
    _WITH_FULL_MEMORY_INFO = 0x0800  # VA layout, so !address works
    _WITH_THREAD_INFO = 0x1000  # thread times and state

    DUMP_TYPE = 0  # 0 = custom (CUSTOM_DUMP_FLAGS), 1 = mini dump, 2 = full dump
    CUSTOM_DUMP_FLAGS = (
        _WITH_DATA_SEGS
        | _WITH_HANDLE_DATA
        | _WITH_UNLOADED_MODULES
        | _WITH_INDIRECT_MEMORY
        | _WITH_PROCESS_THREAD_DATA
        | _WITH_FULL_MEMORY_INFO
        | _WITH_THREAD_INFO
    )
    DUMP_COUNT = 5
    OWNS_PARENT_VALUE = "YasbCreatedLocalDumps"

    def _parent_key_exists(self) -> bool:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.PARENT_KEY_PATH))
            return True
        except OSError:
            return False

    def enable(self):
        # An empty LocalDumps key is itself a switch that makes Windows dump every
        # application, and creating our key creates it too. Remember whether it was
        # already there so disable() only removes one we made.
        parent_existed = self._parent_key_exists()

        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ, self.DUMP_FOLDER)
                winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, self.DUMP_TYPE)
                winreg.SetValueEx(key, "CustomDumpFlags", 0, winreg.REG_DWORD, self.CUSTOM_DUMP_FLAGS)
                winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, self.DUMP_COUNT)
                if not parent_existed:
                    winreg.SetValueEx(key, self.OWNS_PARENT_VALUE, 0, winreg.REG_DWORD, 1)
        except OSError as e:
            print(f"启用崩溃转储失败：{e}")
            return

        try:
            os.makedirs(self.DUMP_FOLDER, exist_ok=True)
        except OSError as e:
            print(f"警告：无法创建转储目录：{e}")

        print("已启用崩溃转储。")
        print(f"转储文件将保存到 {self.DUMP_FOLDER}")
        print(f"保留最近 {self.DUMP_COUNT} 个。报告崩溃时请附上最新的一个。")
        print("转储是内存快照，可能包含你配置中的数据。")

    def disable(self):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH) as key:
                created_parent = bool(winreg.QueryValueEx(key, self.OWNS_PARENT_VALUE)[0])
        except OSError:
            created_parent = False

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH)
        except FileNotFoundError:
            print("未启用崩溃转储。")
            return
        except OSError as e:
            print(f"禁用崩溃转储失败：{e}")
            return

        # Only tear down LocalDumps if we were the ones who created it, and only while
        # nothing else has moved in since.
        if created_parent:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.PARENT_KEY_PATH) as key:
                    subkeys, values, _ = winreg.QueryInfoKey(key)
                if not subkeys and not values:
                    winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, self.PARENT_KEY_PATH)
            except OSError:
                pass

        print("已禁用崩溃转储，现有转储文件保留。")


class CLITaskHandler:
    """Handles tasks related to the command-line interface."""

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except BaseException:
            return False

    def get_current_user_sid(self):
        import win32security

        username = getpass.getuser()
        user, _, _ = win32security.LookupAccountName(None, username)
        sid = win32security.ConvertSidToStringSid(user)
        return sid

    def create_task(self):
        import win32com.client

        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = "一个高度可配置的 Windows 状态栏。"
        task_def.RegistrationInfo.Author = "AmN"
        task_def.Settings.Compatibility = 6
        trigger = task_def.Triggers.Create(9)
        trigger.Enabled = True
        trigger.StartBoundary = datetime.datetime.now().isoformat()
        principal = task_def.Principal
        principal.UserId = self.get_current_user_sid()
        principal.LogonType = 3
        principal.RunLevel = 0
        settings = task_def.Settings
        settings.Enabled = True
        settings.StartWhenAvailable = True
        settings.AllowHardTerminate = True
        settings.ExecutionTimeLimit = "PT0S"
        settings.Priority = 4
        settings.MultipleInstances = 3
        settings.DisallowStartIfOnBatteries = False
        settings.StopIfGoingOnBatteries = False
        settings.Hidden = False
        settings.RunOnlyIfIdle = False
        settings.DisallowStartOnRemoteAppSession = False
        settings.UseUnifiedSchedulingEngine = True
        settings.WakeToRun = False
        idle_settings = settings.IdleSettings
        idle_settings.StopOnIdleEnd = True
        idle_settings.RestartOnIdle = False
        action = task_def.Actions.Create(0)
        action.Path = EXE_PATH
        action.WorkingDirectory = SCRIPT_PATH
        try:
            root_folder.RegisterTaskDefinition("YASB Reborn", task_def, 6, None, None, 3, None)
            print("已成功创建任务 YASB Reborn。")
        except Exception as e:
            print(f"创建任务 YASB Reborn 失败。错误：{e}")

    def delete_task(self):
        import win32com.client

        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        try:
            root_folder.DeleteTask("YASB Reborn", 0)
            print("已成功删除任务 YASB Reborn。")
        except Exception:
            print("删除任务 YASB 失败，或任务不存在。")


class CLIChannelHandler:
    """Handles channel management operations."""

    def switch_channel(self, target_channel: str):
        """Switch to a different release channel.

        Args:
            target_channel: Target channel ('stable' or 'preview')
        """
        import tempfile

        from core.utils.system import get_architecture
        from core.utils.update_service import get_update_service

        update_service = get_update_service()
        current_channel = update_service._current_channel
        architecture = get_architecture()

        # Check if already on target channel
        if current_channel == target_channel:
            print(f"\n你当前已经在 {target_channel} 渠道。")
            sys.exit(0)

        # Check if updates are supported
        if not architecture:
            print("\n错误：无法切换渠道 - 不支持的架构。")
            sys.exit(1)

        # Show warning message
        print(f"\n{Format.yellow}警告：正在切换发布渠道{Format.reset}\n")
        print(
            f"你将把渠道从 {Format.yellow}{current_channel}{Format.reset} 切换到 {Format.yellow}{target_channel}{Format.reset}。\n"
        )
        print("注意事项：")
        print("  * 配置文件在不同版本之间可能不兼容")
        print("  * 切换后你可能需要重新配置部分设置")
        print("  * 切换渠道将下载并安装新版本的 YASB")

        if target_channel == "preview":
            print("  * preview 渠道可能存在错误和不稳定情况")
            print("  * 阅读更新日志：https://github.com/amnweb/yasb/releases/tag/preview")
        else:
            print("  * 阅读更新日志：https://github.com/amnweb/yasb/releases")

        print()

        # Ask for confirmation
        try:
            user_input = input("是否继续？[y/N]: ").strip().lower()
            if user_input not in ["y", "yes"]:
                print("\n渠道切换已取消。")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\n\n渠道切换已取消。")
            sys.exit(0)

        print(f"\n正在获取 {Format.magenta}{target_channel}{Format.reset} 渠道的发布版本...")

        try:
            release_info = update_service.check_for_updates(channel=target_channel, skip_version_check=True, timeout=15)
            if target_channel == "preview":
                version_display = f"build {release_info.version.replace('preview-', '')}"
            else:
                version_display = f"version {release_info.version}"
            print(f"找到 {Format.magenta}{target_channel}{Format.reset} {version_display}")
            print(f"安装包 {release_info.asset_name}")
            if release_info.asset_size:
                print(f"大小 {release_info.asset_size / 1024 / 1024:.1f} MB")
            # Download the MSI
            temp_dir = tempfile.gettempdir()
            msi_path = os.path.join(temp_dir, release_info.asset_name)

            # Use CLIUpdateHandler's download method
            update_handler = CLIUpdateHandler()
            update_handler.download_yasb(release_info.download_url, msi_path)

            # Kill running processes
            for proc in ["yasb.exe", "yasb_themes.exe"]:
                if is_process_running(proc):
                    subprocess.run(["taskkill", "/f", "/im", proc], creationflags=subprocess.CREATE_NO_WINDOW)

            # Install and restart
            install_command = f'msiexec /i "{os.path.abspath(msi_path)}" /passive /norestart'
            run_after_command = f'"{EXE_PATH}"'
            combined_command = f"{install_command} && {run_after_command}"

            print("正在启动安装程序...")
            subprocess.Popen(combined_command, shell=True)
            sys.exit(0)

        except Exception as e:
            print(f"\n切换渠道失败：{e}")
            sys.exit(1)


class CLIUpdateHandler:
    """Handles the update functionality for the command-line interface."""

    def get_installed_product_code(self):
        ERROR_NO_MORE_ITEMS = 259
        MAX_GUID_CHARS = 39
        msi = ctypes.windll.msi
        product_code = ctypes.create_unicode_buffer(MAX_GUID_CHARS + 1)
        index = 0
        while True:
            result = msi.MsiEnumRelatedProductsW("{3f620cf5-07b5-47fd-8e37-9ca8ad14b608}", 0, index, product_code)
            if result == ERROR_NO_MORE_ITEMS:
                break
            elif result == 0:
                return product_code.value
            index += 1
        return None

    def update_yasb(self, yasb_version: str):
        """Check for updates and install if available using centralized update service."""
        import tempfile

        from core.utils.system import get_architecture
        from core.utils.update_service import get_update_service

        architecture = get_architecture()
        update_service = get_update_service()

        # Check if updates are supported
        if not update_service.is_update_supported():
            if YASB_RELEASE_CHANNEL.startswith("pr-"):
                print("\nPR 版本已禁用自动更新。")
            else:
                print("\n此系统不支持自动更新。")
            if not architecture:
                print("原因：不支持的架构")
            sys.exit(1)

        print("正在检查更新...")
        arch_suffix = f" ({architecture})" if architecture else ""
        print(f"当前版本 {yasb_version}{arch_suffix} ({YASB_RELEASE_CHANNEL})")

        try:
            release_info = update_service.check_for_updates(timeout=15)

            if release_info is None:
                print(f"YASB Reborn 已是最新版本（v{yasb_version}）。\n")
                sys.exit(0)

            # Update available
            if update_service._current_channel == "preview":
                print(
                    f"找到 {Format.cyan}YASB Reborn{Format.reset} 预览版 {release_info.version.replace('preview-', '')}"
                )
                print("更新日志 https://github.com/amnweb/yasb/releases/tag/preview")
            else:
                print(f"找到 {Format.cyan}YASB Reborn{Format.reset} 版本 {release_info.version}")
                print("更新日志 https://github.com/amnweb/yasb/releases/latest")
            # Ask the user if they want to continue with the update
            try:
                user_input = input("\n是否继续更新？(Y/n): ").strip().lower()
                if user_input not in ["y", "yes", ""]:
                    print("\n更新已取消。")
                    sys.exit(0)
            except KeyboardInterrupt:
                print("\n\n更新已取消。")
                sys.exit(0)

            # Download the MSI
            temp_dir = tempfile.gettempdir()
            msi_path = os.path.join(temp_dir, release_info.asset_name)
            self.download_yasb(release_info.download_url, msi_path)

            # Kill running processes
            for proc in ["yasb.exe", "yasb_themes.exe"]:
                if is_process_running(proc):
                    subprocess.run(["taskkill", "/f", "/im", proc], creationflags=subprocess.CREATE_NO_WINDOW)

            # Install and restart
            install_command = f'msiexec /i "{os.path.abspath(msi_path)}" /passive /norestart'
            run_after_command = f'"{EXE_PATH}"'
            combined_command = f"{install_command} && {run_after_command}"

            print("正在启动安装程序...")
            subprocess.Popen(combined_command, shell=True)
            sys.exit(0)

        except Exception as e:
            print(f"\n检查更新失败：{e}")
            sys.exit(1)

    def download_yasb(self, msi_url: str, msi_path: str) -> None:
        """Download a file with progress bar.

        Args:
            msi_url: Download URL
            msi_path: Local file path
        """
        import urllib.error
        from urllib.request import urlopen

        try:
            with urlopen(msi_url) as response:
                content_length = response.getheader("Content-Length")
                if content_length is None:
                    print("错误：缺少 Content-Length 响应头。")
                    sys.exit(1)

                try:
                    total_length = int(content_length)
                except ValueError:
                    print(f"错误：无效的 Content-Length 值：{content_length}")
                    sys.exit(1)

                downloaded = 0
                chunk_size = 4096
                print(f"正在下载 {Format.magenta}{msi_url}{Format.reset}")
                with open(msi_path, "wb") as file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        file.write(chunk)
                        downloaded += len(chunk)
                        percent = downloaded / total_length * 100
                        bar_length = 30
                        filled = int(bar_length * downloaded / total_length)
                        bar = "\u2588" * filled + "\u2591" * (bar_length - filled)
                        print(f"\r{bar} {percent:.1f}%", end="", flush=True)

                print("\r" + " " * (bar_length + 10) + "\r下载完成。")

        except KeyboardInterrupt:
            print("\n下载被用户中断。")
            sys.exit(0)

        except urllib.error.URLError as e:
            print(f"下载失败：{e}")
            sys.exit(1)

        # Verify the downloaded file size
        downloaded_size = os.path.getsize(msi_path)
        if downloaded_size != total_length:
            print("错误：下载文件大小与预期不符。")
            sys.exit(1)


if __name__ == "__main__":
    cli_handler = CLIHandler()
    cli_handler.parse_arguments()
    sys.exit(0)
