"""
Interactive Configuration CLI

交互式配置 CLI，提供：
- Provider 配置向导
- 扩展管理向导
- 设置配置向导
- 首次运行设置

Reference: goose-rs/crates/goose-cli/src/commands/configure.rs
"""

import os
import sys
import asyncio
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("goose.config.cli")


class CLIColor:
    """CLI 颜色样式"""
    
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    @classmethod
    def style(cls, text: str, *codes: str) -> str:
        return "".join(codes) + text + cls.RESET
    
    @classmethod
    def bold(cls, text: str) -> str:
        return cls.style(text, cls.BOLD)
    
    @classmethod
    def dim(cls, text: str) -> str:
        return cls.style(text, cls.DIM)
    
    @classmethod
    def red(cls, text: str) -> str:
        return cls.style(text, cls.RED)
    
    @classmethod
    def green(cls, text: str) -> str:
        return cls.style(text, cls.GREEN)
    
    @classmethod
    def yellow(cls, text: str) -> str:
        return cls.style(text, cls.YELLOW)
    
    @classmethod
    def cyan(cls, text: str) -> str:
        return cls.style(text, cls.CYAN)
    
    @classmethod
    def on_cyan(cls, text: str) -> str:
        return cls.style(text, cls.CYAN, cls.BLACK)


class InteractiveInput:
    """交互式输入工具"""
    
    @staticmethod
    def confirm(prompt: str, default: bool = True) -> bool:
        """确认输入"""
        default_str = "y" if default else "n"
        default_hint = f" [{default_str}]"
        
        while True:
            try:
                response = input(f"{prompt}{default_hint}: ").strip().lower()
                if not response:
                    return default
                if response in ("y", "yes"):
                    return True
                if response in ("n", "no"):
                    return False
            except (EOFError, KeyboardInterrupt):
                return default
    
    @staticmethod
    def input(prompt: str, default: Optional[str] = None, validate: Optional[str] = None) -> str:
        """文本输入"""
        default_str = f" (default: {default})" if default else ""
        
        while True:
            try:
                response = input(f"{prompt}{default_str}: ").strip()
                if not response:
                    if default:
                        return default
                    continue
                if validate:
                    if validate == "non_empty" and not response:
                        print("Please enter a value")
                        continue
                return response
            except (EOFError, KeyboardInterrupt):
                return default or ""
    
    @staticmethod
    def password(prompt: str) -> str:
        """密码输入"""
        try:
            import getpass
            return getpass.getpass(f"{prompt}: ")
        except:
            return input(f"{prompt}: ")
    
    @staticmethod
    def select(prompt: str, options: List[Tuple[str, str, str]]) -> str:
        """选择输入"""
        print(f"\n{prompt}")
        print("-" * 50)
        
        for i, (key, label, desc) in enumerate(options, 1):
            print(f"  {i}. {label}")
            if desc:
                print(f"     {CLIColor.dim(desc)}")
        
        print("-" * 50)
        
        while True:
            try:
                response = input("Select: ").strip()
                if not response:
                    continue
                try:
                    idx = int(response) - 1
                    if 0 <= idx < len(options):
                        return options[idx][0]
                except ValueError:
                    pass
                if response in [opt[0] for opt in options]:
                    return response
            except (EOFError, KeyboardInterrupt):
                return options[0][0]
    
    @staticmethod
    def multiselect(prompt: str, options: List[Tuple[str, str, str]], defaults: List[str] = None) -> List[str]:
        """多选输入"""
        print(f"\n{prompt}")
        print(CLIColor.dim("(use 'space' to toggle and 'enter' to submit)"))
        print("-" * 50)
        
        selected = set(defaults or [])
        
        for i, (key, label, _) in enumerate(options):
            marker = "[x]" if key in selected else "[ ]"
            print(f"  {marker} {label}")
        
        print("-" * 50)
        
        return list(selected)


class ConfigCLI:
    """配置 CLI"""
    
    def __init__(self):
        from . import (
            Config, get_config, SecretStorage,
            ExtensionManager, get_all_extensions,
            PermissionManager, PermissionLevel,
            GooseMode,
            ProviderRegistry, ProviderTester, fetch_provider_models,
        )
        self.config = get_config()
        self.extension_manager = ExtensionManager.get_instance()
        self.permission_manager = PermissionManager.get_instance()
        self.provider_registry = ProviderRegistry.get_instance()
        self.tester = ProviderTester
        self.fetch_models = fetch_provider_models
        self.PermissionLevel = PermissionLevel
        self.GooseMode = GooseMode
    
    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, title: str):
        """打印标题"""
        self.clear_screen()
        print()
        print(CLIColor.on_cyan(" " + title + " "))
        print()
    
    def print_success(self, message: str):
        """打印成功消息"""
        print(f"{CLIColor.green('[OK]')} {message}")
    
    def print_error(self, message: str):
        """打印错误消息"""
        print(f"{CLIColor.red('[ERROR]')} {message}")
    
    def print_info(self, message: str):
        """打印信息"""
        print(f"{CLIColor.dim('[INFO]')} {message}")
    
    def print_warning(self, message: str):
        """打印警告"""
        print(f"{CLIColor.yellow('[WARNING]')} {message}")
    
    async def run_first_time_setup(self) -> bool:
        """首次运行设置"""
        self.print_header("Welcome to Goose!")
        
        print(CLIColor.dim("Let's get you set up."))
        print()
        
        if InteractiveInput.confirm("Help improve goose by sharing anonymous usage data?"):
            self.config.set("GOOSE_TELEMETRY_ENABLED", True)
            self.print_success("Thank you for helping improve goose!")
        else:
            self.config.set("GOOSE_TELEMETRY_ENABLED", False)
            self.print_info("Telemetry disabled")
        
        return await self.run_provider_setup()
    
    async def run_provider_setup(self) -> bool:
        """Provider 设置向导"""
        self.print_header("Configure Provider")
        
        providers = self.provider_registry.list_providers()
        options = [
            (p.name, p.display_name, p.description)
            for p in providers
        ]
        
        provider_name = InteractiveInput.select("Which model provider would you like to use?", options)
        provider = self.provider_registry.get_provider(provider_name)
        
        print(f"\nConfiguring {provider.display_name}...")
        print()
        
        config_values = {}
        for key in provider.config_keys:
            if key.oauth_flow:
                self.print_info(f"{key.name} requires OAuth authentication")
                continue
            
            if key.secret:
                value = InteractiveInput.password(f"Enter {key.name}")
                if value:
                    self.config.set(key.name, value, secret=True)
                    config_values[key.name] = value
            else:
                value = InteractiveInput.input(
                    f"Enter {key.name}",
                    default=key.default,
                    validate="non_empty" if key.required else None
                )
                if value or not key.required:
                    self.config.set(key.name, value)
                    config_values[key.name] = value
        
        print("\nFetching available models...")
        
        api_key = config_values.get("api_key")
        if api_key:
            models = await self.fetch_models(provider_name, api_key)
        else:
            models = provider.known_models
        
        if models:
            print(f"\nAvailable models ({len(models)}):")
            for m in models[:10]:
                print(f"  - {m}")
            if len(models) > 10:
                print(f"  ... and {len(models) - 10} more")
            
            model = InteractiveInput.input("Select a model", default=provider.default_model)
        else:
            model = InteractiveInput.input("Enter model name", default=provider.default_model)
        
        self.config.set_goose_provider(provider_name)
        self.config.set_goose_model(model)
        
        print("\nTesting configuration...")
        success, message = await self.tester.test_provider_config(
            provider_name, model, api_key
        )
        
        if success:
            self.print_success(message)
            return True
        else:
            self.print_error(message)
            return InteractiveInput.confirm("Configuration failed. Try again?")
    
    def run_extension_setup(self) -> None:
        """扩展设置向导"""
        self.print_header("Manage Extensions")
        
        extensions = self.extension_manager.get_all_extensions()
        
        if not extensions:
            self.print_info("No extensions configured yet.")
            print()
            
            if InteractiveInput.confirm("Add an extension?"):
                self._add_extension()
        else:
            print("Current extensions:")
            for ext in extensions:
                status = CLIColor.green("enabled") if ext.enabled else CLIColor.yellow("disabled")
                print(f"  - {ext.config.name()}: {status}")
            
            print()
            action = InteractiveInput.select(
                "What would you like to do?",
                [
                    ("add", "Add Extension", "Connect a new extension"),
                    ("toggle", "Toggle Extensions", "Enable or disable extensions"),
                    ("remove", "Remove Extension", "Remove an extension"),
                    ("done", "Done", "Return to main menu"),
                ]
            )
            
            if action == "add":
                self._add_extension()
            elif action == "toggle":
                self._toggle_extensions(extensions)
            elif action == "remove":
                self._remove_extension(extensions)
    
    def _add_extension(self) -> None:
        """添加扩展"""
        from . import ExtensionConfig, ExtensionEntry
        
        ext_type = InteractiveInput.select(
            "What type of extension would you like to add?",
            [
                ("builtin", "Built-in Extension", "Use an extension that comes with goose"),
                ("stdio", "Command-line Extension", "Run a local command or script"),
                ("http", "Remote Extension", "Connect to a remote extension via HTTP"),
            ]
        )
        
        if ext_type == "builtin":
            builtin_exts = [
                ("autovisualiser", "Auto Visualiser", "Data visualisation and UI generation"),
                ("computercontroller", "Computer Controller", "Web scraping and automation"),
                ("developer", "Developer Tools", "Code editing and shell access"),
                ("memory", "Memory", "Save and retrieve durable memories"),
                ("tutorial", "Tutorial", "Interactive tutorials and guides"),
            ]
            
            name = InteractiveInput.select("Which built-in extension?", builtin_exts)
            timeout = InteractiveInput.input("Extension timeout (seconds)", default="300")
            
            ext_config = ExtensionConfig.builtin_ext(
                name=name,
                display_name=name.replace("_", " ").title(),
                timeout=int(timeout)
            )
            self.extension_manager.set_extension(ExtensionEntry(enabled=True, config=ext_config))
            
            self.print_success(f"Enabled {name} extension")
        
        elif ext_type == "stdio":
            name = InteractiveInput.input("Extension name", validate="non_empty")
            cmd = InteractiveInput.input("Command to run", validate="non_empty")
            desc = InteractiveInput.input("Description")
            timeout = InteractiveInput.input("Timeout (seconds)", default="300")
            
            ext_config = ExtensionConfig.stdio_ext(
                name=name,
                cmd=cmd,
                description=desc,
                timeout=int(timeout)
            )
            self.extension_manager.set_extension(ExtensionEntry(enabled=True, config=ext_config))
            
            self.print_success(f"Added {name} extension")
        
        elif ext_type == "http":
            name = InteractiveInput.input("Extension name", validate="non_empty")
            uri = InteractiveInput.input("HTTP endpoint URI", validate="non_empty")
            desc = InteractiveInput.input("Description")
            timeout = InteractiveInput.input("Timeout (seconds)", default="300")
            
            ext_config = ExtensionConfig.streamable_http_ext(
                name=name,
                uri=uri,
                description=desc,
                timeout=int(timeout)
            )
            self.extension_manager.set_extension(ExtensionEntry(enabled=True, config=ext_config))
            
            self.print_success(f"Added {name} extension")
    
    def _toggle_extensions(self, extensions: List) -> None:
        """切换扩展启用状态"""
        options = [
            (ext.config.name(), ext.config.name(), CLIColor.green("enabled") if ext.enabled else CLIColor.yellow("disabled"))
            for ext in extensions
        ]
        
        selected = InteractiveInput.multiselect(
            "Enable extensions:",
            options,
            [e.config.name() for e in extensions if e.enabled]
        )
        
        for ext in extensions:
            enabled = ext.config.name() in selected
            self.extension_manager.set_extension_enabled(ext.config.name(), enabled)
        
        self.print_success("Extension settings saved")
    
    def _remove_extension(self, extensions: List) -> None:
        """删除扩展"""
        options = [
            (ext.config.name(), ext.config.name(), "")
            for ext in extensions if not ext.enabled
        ]
        
        if not options:
            self.print_warning("No extensions available to remove")
            return
        
        selected = InteractiveInput.multiselect(
            "Select extensions to remove:",
            options
        )
        
        for name in selected:
            self.extension_manager.remove_extension(name)
            self.print_success(f"Removed {name}")
    
    def run_settings_setup(self) -> None:
        """设置向导"""
        self.print_header("Settings")
        
        action = InteractiveInput.select(
            "What setting would you like to configure?",
            [
                ("mode", "Goose Mode", "Set the goose mode (Auto/Approve/SmartApprove/Chat)"),
                ("telemetry", "Telemetry", "Enable or disable anonymous usage data"),
                ("permissions", "Tool Permissions", "Set permission for tools"),
                ("max_turns", "Max Turns", "Set maximum number of turns"),
            ]
        )
        
        if action == "mode":
            self._configure_mode()
        elif action == "telemetry":
            self._configure_telemetry()
        elif action == "permissions":
            self._configure_permissions()
        elif action == "max_turns":
            self._configure_max_turns()
    
    def _configure_mode(self) -> None:
        """配置 Goose Mode"""
        modes = [
            (self.GooseMode.AUTO, "Auto Mode", "Full file modification and tool usage"),
            (self.GooseMode.APPROVE, "Approve Mode", "All actions require human approval"),
            (self.GooseMode.SMART_APPROVE, "Smart Approve Mode", "File modifications require approval"),
            (self.GooseMode.CHAT, "Chat Mode", "No tools or file modifications"),
        ]
        
        mode = InteractiveInput.select("Which goose mode?", modes)
        self.config.set_goose_mode(mode)
        
        self.print_success(f"Set to {mode.value} mode")
    
    def _configure_telemetry(self) -> None:
        """配置遥测"""
        enabled = InteractiveInput.confirm("Share anonymous usage data?")
        self.config.set("GOOSE_TELEMETRY_ENABLED", enabled)
        
        if enabled:
            self.print_success("Telemetry enabled")
        else:
            self.print_info("Telemetry disabled")
    
    def _configure_permissions(self) -> None:
        """配置权限"""
        from . import get_all_extensions
        
        extensions = get_all_extensions()
        ext_names = [e.config.name() for e in extensions]
        ext_names.insert(0, "platform")
        
        ext_name = InteractiveInput.select(
            "Choose an extension to configure tools:",
            [(n, n, "") for n in ext_names]
        )
        
        if ext_name == "platform":
            self.print_info("Platform permissions")
            return
        
        level = InteractiveInput.select(
            "Default permission level for this extension:",
            [
                (self.PermissionLevel.ALWAYS_ALLOW.value, "Always Allow", "All tools run without asking"),
                (self.PermissionLevel.CONFIRM.value, "Confirm", "Ask before running each tool"),
                (self.PermissionLevel.DENY.value, "Deny", "Block all tools"),
            ]
        )
        
        self.permission_manager.set_extension_default_level(ext_name, self.PermissionLevel(level))
        self.print_success(f"Permission level set to {level}")
    
    def _configure_max_turns(self) -> None:
        """配置最大回合数"""
        max_turns = InteractiveInput.input("Maximum turns without user input", default="100")
        try:
            self.config.set("GOOSE_MAX_TURNS", int(max_turns))
            self.print_success(f"Max turns set to {max_turns}")
        except ValueError:
            self.print_error("Invalid value")
    
    async def run_main_menu(self) -> None:
        """主菜单"""
        while True:
            self.print_header("Goose Configuration")
            
            print("Main Menu:")
            print("  1. Configure Provider")
            print("  2. Manage Extensions")
            print("  3. Settings")
            print("  4. Exit")
            print()
            
            choice = InteractiveInput.input("Select an option", default="1")
            
            if choice == "1":
                await self.run_provider_setup()
            elif choice == "2":
                self.run_extension_setup()
            elif choice == "3":
                self.run_settings_setup()
            elif choice == "4":
                print("\nGoodbye!")
                break
            
            input("\nPress Enter to continue...")
    
    async def run(self) -> None:
        """运行配置向导"""
        if not self.config.exists():
            await self.run_first_time_setup()
        else:
            await self.run_main_menu()


async def run_configure():
    """运行配置向导"""
    cli = ConfigCLI()
    await cli.run()


def main():
    """主入口"""
    try:
        asyncio.run(run_configure())
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
