from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from firmware_parser import FirmwareValidationError, validate_firmware
from jflash_project_parser import JFlashProjectError, parse_jflash_project


DEFAULT_PROJECT = r"D:\Program Files\SEGGER\JLink_V966\Samples\JFlash\ProjectFiles\S32K144.jflash"
DEFAULT_JFLASH_PATHS = (
    r"D:\Program Files\SEGGER\JLink_V966\JFlash.exe",
    r"C:\Program Files\SEGGER\JLink\JFlash.exe",
    r"C:\Program Files\SEGGER\JLink_V966\JFlash.exe",
)


CONFIG_FILE = Path(os.environ.get("APPDATA", Path.home())) / "JFlashProtect" / "config.json"

APP_NAME = "J-Flash 自动烧录工具"
APP_VERSION = "1.1.0"
CHANGELOG = (
    "\u5bfc\u5165 J-Flash \u5de5\u7a0b\u540e\u663e\u793a\u5f53\u524d MCU",
    "增加 F2 烧录快捷键",
    "增加关于窗口，显示程序版本和更新记录",
    "支持固件地址范围校验",
    "支持文件拖拽导入并保存最近一次成功烧录配置",
)

class JFlashApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("\u004a-Flash \u81ea\u52a8\u70e7\u5f55")
        self.root.resizable(False, False)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.success_count = 0
        self.error_count = 0

        saved_config = self.load_config()
        self.jflash_var = tk.StringVar(value=saved_config.get("jflash", self.find_jflash()))
        self.project_var = tk.StringVar(value=saved_config.get("project", DEFAULT_PROJECT))
        self.firmware_var = tk.StringVar(value=saved_config.get("firmware", ""))
        self.status_var = tk.StringVar(value="\u5c31\u7eea")
        self.counts_var = tk.StringVar(value="\u6210\u529f\u6b21\u6570: 0    \u9519\u8bef\u6b21\u6570: 0")
        self.range_var = tk.StringVar(value="\u672a\u5bfc\u5165\u6709\u6548\u56fa\u4ef6")
        self.mcu_var = tk.StringVar(value="\u672a\u5bfc\u5165 J-Flash \u5de5\u7a0b")

        self.create_menu()
        self.root.bind_all("<F2>", self.handle_f2)
        self.build_ui()
        saved_project = Path(self.project_var.get().strip())
        if saved_project.is_file():
            self.set_project(saved_project, notify=False)
        self.install_file_drop()
        self.root.after(100, self.process_messages)

    def create_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="关于", command=self.show_about)
        menu_bar.add_cascade(label="帮助", menu=help_menu)
        self.root.configure(menu=menu_bar)

    def handle_f2(self, _event=None) -> str:
        self.start_flash()
        return "break"

    def show_about(self) -> None:
        about_window = tk.Toplevel(self.root)
        about_window.title("关于")
        about_window.resizable(False, False)
        about_window.transient(self.root)

        frame = ttk.Frame(about_window, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text=APP_NAME, font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, text=f"版本：{APP_VERSION}").grid(
            row=1, column=0, sticky="w", pady=(6, 12)
        )
        ttk.Label(frame, text="更新记录：").grid(row=2, column=0, sticky="w")

        changelog = tk.Text(frame, width=52, height=len(CHANGELOG) + 1, wrap="word")
        changelog.grid(row=3, column=0, pady=(4, 12))
        changelog.insert("1.0", "\n".join(f"• {item}" for item in CHANGELOG))
        changelog.configure(state="disabled")

        ttk.Button(frame, text="关闭", command=about_window.destroy).grid(
            row=4, column=0, sticky="e"
        )
        about_window.grab_set()
        about_window.protocol("WM_DELETE_WINDOW", about_window.destroy)
        about_window.focus_set()

    @staticmethod
    def find_jflash() -> str:
        for candidate in DEFAULT_JFLASH_PATHS:
            if Path(candidate).is_file():
                return candidate
        return shutil.which("JFlash.exe") or "JFlash.exe"

    @staticmethod
    def load_config() -> dict[str, str]:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_config(self) -> None:
        data = {
            "jflash": self.jflash_var.get().strip(),
            "project": self.project_var.get().strip(),
            "firmware": self.firmware_var.get().strip(),
        }
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="J-Flash \u7a0b\u5e8f:").grid(row=0, column=0, sticky="w", pady=5)
        self.jflash_entry = ttk.Entry(
            frame, textvariable=self.jflash_var, width=64, state="readonly"
        )
        self.jflash_entry.grid(row=0, column=1, padx=8, pady=5)
        ttk.Button(frame, text="\u6d4f\u89c8...", command=self.choose_jflash).grid(row=0, column=2, pady=5)

        ttk.Label(frame, text="J-Flash \u5de5\u7a0b:").grid(row=1, column=0, sticky="w", pady=5)
        self.project_entry = ttk.Entry(
            frame, textvariable=self.project_var, width=64, state="readonly"
        )
        self.project_entry.grid(row=1, column=1, padx=8, pady=5)
        ttk.Button(frame, text="\u6d4f\u89c8...", command=self.choose_project).grid(row=1, column=2, pady=5)
        ttk.Label(frame, textvariable=self.mcu_var).grid(row=2, column=1, columnspan=2, sticky="w")

        ttk.Label(frame, text="\u56fa\u4ef6\u6587\u4ef6:").grid(row=3, column=0, sticky="w", pady=5)
        self.firmware_entry = ttk.Entry(
            frame, textvariable=self.firmware_var, width=64, state="readonly"
        )
        self.firmware_entry.grid(row=3, column=1, padx=8, pady=5)
        ttk.Button(frame, text="\u6d4f\u89c8...", command=self.choose_firmware).grid(row=3, column=2, pady=5)
        ttk.Label(frame, textvariable=self.range_var).grid(row=4, column=1, columnspan=2, sticky="w")

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=(10, 5))
        self.flash_button = ttk.Button(button_frame, text="\u5f00\u59cb\u81ea\u52a8\u70e7\u5f55", command=self.start_flash)
        self.flash_button.grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="\u6e05\u7a7a\u65e5\u5fd7", command=self.clear_log).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="\u9000\u51fa", command=self.root.destroy).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="\u70e7\u5f55\u65e5\u5fd7:").grid(row=6, column=0, sticky="nw", pady=5)
        self.log_text = tk.Text(frame, width=72, height=10, state="disabled", wrap="word")
        self.log_text.grid(row=6, column=1, columnspan=2, padx=8, pady=5)

        ttk.Label(frame, textvariable=self.status_var).grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(frame, textvariable=self.counts_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 0))

    def install_file_drop(self) -> None:
        for entry in (self.jflash_entry, self.project_entry, self.firmware_entry):
            entry.drop_target_register(DND_FILES)
            entry.dnd_bind("<<Drop>>", self.handle_drop_event)

    def handle_drop_event(self, event) -> str:
        paths = self.root.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showwarning("\u6587\u4ef6\u62d6\u653e", "\u8bf7\u4e00\u6b21\u53ea\u62d6\u5165\u4e00\u4e2a\u6587\u4ef6\u3002")
            return "break"

        path = Path(paths[0])
        if event.widget == self.jflash_entry:
            self.jflash_var.set(str(path))
        elif event.widget == self.project_entry:
            self.set_project(path)
        elif event.widget == self.firmware_entry:
            self.set_firmware(path)
        else:
            self.assign_dropped_file(path)
        return "break"

    def assign_dropped_file(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix == ".exe":
            self.jflash_var.set(str(path))
        elif suffix == ".jflash":
            self.set_project(path)
        elif suffix in {".hex", ".s19", ".srec", ".mot", ".bin"}:
            self.set_firmware(path)
        else:
            messagebox.showwarning("\u6587\u4ef6\u62d6\u653e", "\u4e0d\u652f\u6301\u8be5\u6587\u4ef6\u7c7b\u578b\u3002")
    def choose_jflash(self) -> None:
        path = filedialog.askopenfilename(
            title="\u9009\u62e9 JFlash.exe",
            filetypes=[("JFlash \u7a0b\u5e8f", "JFlash.exe"), ("\u53ef\u6267\u884c\u6587\u4ef6", "*.exe"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
        )
        if path:
            self.jflash_var.set(path)

    def choose_project(self) -> None:
        path = filedialog.askopenfilename(
            title="\u9009\u62e9 J-Flash \u5de5\u7a0b",
            filetypes=[("J-Flash \u5de5\u7a0b", "*.jflash"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
        )
        if path:
            self.set_project(Path(path))
    def set_project(self, path: Path, notify: bool = True) -> None:
        self.project_var.set(str(path))
        try:
            mcu_name = parse_jflash_project(path)
        except (OSError, UnicodeError, JFlashProjectError) as exc:
            self.mcu_var.set("\u5f53\u524d MCU: \u672a\u8bc6\u522b")
            self.status_var.set("J-Flash \u5de5\u7a0b MCU \u8bc6\u522b\u5931\u8d25")
            if notify:
                messagebox.showwarning(
                    "J-Flash \u5de5\u7a0b",
                    f"\u65e0\u6cd5\u8bc6\u522b\u5f53\u524d\u5de5\u7a0b\u7684 MCU\uff1a\n{exc}",
                )
            return

        self.mcu_var.set(f"\u5f53\u524d MCU: {mcu_name}")
        self.status_var.set(f"\u5df2\u5bfc\u5165\u5de5\u7a0b\uff0c\u5f53\u524d MCU: {mcu_name}")
        if notify:
            messagebox.showinfo(
                "J-Flash \u5de5\u7a0b",
                f"\u5f53\u524d\u9009\u7528\u7684 MCU\uff1a{mcu_name}",
            )
    def choose_firmware(self) -> None:
        path = filedialog.askopenfilename(
            title="\u9009\u62e9\u56fa\u4ef6\u6587\u4ef6",
            filetypes=[
                ("\u56fa\u4ef6\u6587\u4ef6", "*.hex *.s19 *.srec *.mot *.bin"),
                ("\u6240\u6709\u6587\u4ef6", "*.*"),
            ],
        )
        if path:
            self.set_firmware(Path(path))
    def set_firmware(self, path: Path) -> None:
        try:
            start_address, end_address = validate_firmware(path)
        except (OSError, UnicodeError, FirmwareValidationError) as exc:
            self.firmware_var.set("")
            self.range_var.set("\u672a\u5bfc\u5165\u6709\u6548\u56fa\u4ef6")
            self.status_var.set("\u56fa\u4ef6\u5730\u5740\u68c0\u67e5\u5931\u8d25")
            messagebox.showerror("\u56fa\u4ef6\u9519\u8bef", f"\u8fd9\u4e0d\u662f\u6b63\u5e38\u70e7\u5199\u6587\u4ef6\uff0c\u4e0d\u80fd\u70e7\u5f55\u3002\n\n{exc}")
            return
        self.firmware_var.set(str(path))
        self.range_var.set(f"\u5730\u5740\u8303\u56f4: 0x{start_address:08X} - 0x{end_address:08X}")
        self.status_var.set("\u56fa\u4ef6\u5730\u5740\u68c0\u67e5\u901a\u8fc7")

    def build_command(self) -> list[str]:
        return [
            self.jflash_var.get().strip(),
            f"-openprj{self.project_var.get().strip()}",
            f"-open{self.firmware_var.get().strip()}",
            "-auto",
            "-exit",
        ]

    def validate_inputs(self) -> bool:
        jflash_text = self.jflash_var.get().strip()
        jflash = Path(jflash_text)
        project = Path(self.project_var.get().strip())
        firmware = Path(self.firmware_var.get().strip())

        if not jflash_text:
            messagebox.showerror("\u53c2\u6570\u9519\u8bef", "\u8bf7\u9009\u62e9 JFlash.exe\u3002")
        elif not jflash.is_file() and not shutil.which(jflash_text):
            messagebox.showerror("\u53c2\u6570\u9519\u8bef", f"\u627e\u4e0d\u5230 J-Flash \u7a0b\u5e8f:\n{jflash_text}")
        elif not project.is_file():
            messagebox.showerror("\u53c2\u6570\u9519\u8bef", f"\u627e\u4e0d\u5230 J-Flash \u5de5\u7a0b:\n{project}")
        elif not firmware.is_file():
            messagebox.showerror("\u53c2\u6570\u9519\u8bef", f"\u627e\u4e0d\u5230\u56fa\u4ef6\u6587\u4ef6:\n{firmware}")
        else:
            try:
                start_address, end_address = validate_firmware(firmware)
            except (OSError, UnicodeError, FirmwareValidationError) as exc:
                messagebox.showerror("\u56fa\u4ef6\u9519\u8bef", f"\u8fd9\u4e0d\u662f\u6b63\u5e38\u70e7\u5199\u6587\u4ef6\uff0c\u4e0d\u80fd\u70e7\u5f55\u3002\n\n{exc}")
                return False
            self.range_var.set(f"\u5730\u5740\u8303\u56f4: 0x{start_address:08X} - 0x{end_address:08X}")
            return True
        return False

    def start_flash(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.validate_inputs():
            return
        self.status_var.set("\u6b63\u5728\u70e7\u5f55...")
        self.flash_button.configure(state="disabled")
        self.worker = threading.Thread(target=self.run_flash, args=(self.build_command(),), daemon=True)
        self.worker.start()

    def run_flash(self, command: list[str]) -> None:
        try:
            executable = Path(command[0])
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(executable.parent) if executable.parent != Path(".") else None,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.messages.put(("done", str(process.wait())))
        except FileNotFoundError:
            self.messages.put(("error", "\u627e\u4e0d\u5230 JFlash.exe\uff0c\u8bf7\u68c0\u67e5\u7a0b\u5e8f\u8def\u5f84\u3002"))
        except OSError as exc:
            self.messages.put(("error", f"\u542f\u52a8 J-Flash \u5931\u8d25: {exc}"))
        except Exception as exc:
            self.messages.put(("error", f"\u70e7\u5f55\u8fc7\u7a0b\u5f02\u5e38: {exc}"))

    def process_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "done":
                    if int(value) == 0:
                        self.success_count += 1
                        self.status_var.set("\u70e7\u5f55\u6210\u529f")
                        self.save_config()
                    else:
                        self.error_count += 1
                        self.status_var.set("\u70e7\u5f55\u5931\u8d25")
                    self.append_summary()
                    self.flash_button.configure(state="normal")
                elif kind == "error":
                    self.error_count += 1
                    self.status_var.set("\u70e7\u5f55\u5931\u8d25")
                    self.append_summary()
                    self.flash_button.configure(state="normal")
                    messagebox.showerror("\u70e7\u5f55\u5931\u8d25", value)
        except queue.Empty:
            pass
        self.root.after(100, self.process_messages)

    def append_summary(self) -> None:
        summary = (
            f"{self.status_var.get()} | "
            f"\u6210\u529f\u6b21\u6570: {self.success_count} | "
            f"\u9519\u8bef\u6b21\u6570: {self.error_count}"
        )
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, summary + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")
        self.counts_var.set(f"\u6210\u529f\u6b21\u6570: {self.success_count}    \u9519\u8bef\u6b21\u6570: {self.error_count}")

    def clear_log(self) -> None:
        self.success_count = 0
        self.error_count = 0
        self.status_var.set("\u5c31\u7eea")
        self.counts_var.set("\u6210\u529f\u6b21\u6570: 0    \u9519\u8bef\u6b21\u6570: 0")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")


if __name__ == "__main__":
    app_root = TkinterDnD.Tk()
    app = JFlashApp(app_root)
    app_root.mainloop()