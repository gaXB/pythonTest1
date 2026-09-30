from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


DEFAULT_PROJECT = r"D:\Program Files\SEGGER\JLink_V966\Samples\JFlash\ProjectFiles\S32K144.jflash"
DEFAULT_JFLASH_PATHS = (
    r"D:\Program Files\SEGGER\JLink_V966\JFlash.exe",
    r"C:\Program Files\SEGGER\JLink\JFlash.exe",
    r"C:\Program Files\SEGGER\JLink_V966\JFlash.exe",
)


class JFlashApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("J-Flash 自动烧录")
        self.root.resizable(False, False)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.success_count = 0
        self.error_count = 0

        self.jflash_var = tk.StringVar(value=self.find_jflash())
        self.project_var = tk.StringVar(value=DEFAULT_PROJECT)
        self.firmware_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.counts_var = tk.StringVar(value="成功次数: 0    错误次数: 0")

        self.build_ui()
        self.root.after(100, self.process_messages)

    @staticmethod
    def find_jflash() -> str:
        for candidate in DEFAULT_JFLASH_PATHS:
            if Path(candidate).is_file():
                return candidate
        return shutil.which("JFlash.exe") or "JFlash.exe"

    def build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="J-Flash 程序:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.jflash_var, width=64).grid(row=0, column=1, padx=8, pady=5)
        ttk.Button(frame, text="浏览...", command=self.choose_jflash).grid(row=0, column=2, pady=5)

        ttk.Label(frame, text="J-Flash 工程:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.project_var, width=64).grid(row=1, column=1, padx=8, pady=5)
        ttk.Button(frame, text="浏览...", command=self.choose_project).grid(row=1, column=2, pady=5)

        ttk.Label(frame, text="固件文件:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.firmware_var, width=64).grid(row=2, column=1, padx=8, pady=5)
        ttk.Button(frame, text="浏览...", command=self.choose_firmware).grid(row=2, column=2, pady=5)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(10, 5))
        self.flash_button = ttk.Button(button_frame, text="开始自动烧录", command=self.start_flash)
        self.flash_button.grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="清空日志", command=self.clear_log).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="退出", command=self.root.destroy).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="烧录日志:").grid(row=4, column=0, sticky="nw", pady=5)
        self.log_text = tk.Text(frame, width=72, height=10, state="disabled", wrap="word")
        self.log_text.grid(row=4, column=1, columnspan=2, padx=8, pady=5)

        ttk.Label(frame, textvariable=self.status_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(frame, textvariable=self.counts_var).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))

    def choose_jflash(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 JFlash.exe",
            filetypes=[("JFlash 程序", "JFlash.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path:
            self.jflash_var.set(path)

    def choose_project(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 J-Flash 工程",
            filetypes=[("J-Flash 工程", "*.jflash"), ("所有文件", "*.*")],
        )
        if path:
            self.project_var.set(path)

    def choose_firmware(self) -> None:
        path = filedialog.askopenfilename(
            title="选择固件文件",
            filetypes=[
                ("固件文件", "*.hex *.s19 *.srec *.mot *.bin"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.firmware_var.set(path)

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
            messagebox.showerror("参数错误", "请选择 JFlash.exe。")
        elif not jflash.is_file() and not shutil.which(jflash_text):
            messagebox.showerror("参数错误", f"找不到 J-Flash 程序:\n{jflash_text}")
        elif not project.is_file():
            messagebox.showerror("参数错误", f"找不到 J-Flash 工程:\n{project}")
        elif not firmware.is_file():
            messagebox.showerror("参数错误", f"找不到固件文件:\n{firmware}")
        else:
            return True
        return False

    def start_flash(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.validate_inputs():
            return

        self.status_var.set("正在烧录...")
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
            self.messages.put(("error", "找不到 JFlash.exe，请检查程序路径。"))
        except OSError as exc:
            self.messages.put(("error", f"启动 J-Flash 失败: {exc}"))
        except Exception as exc:
            self.messages.put(("error", f"烧录过程异常: {exc}"))

    def process_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "done":
                    if int(value) == 0:
                        self.success_count += 1
                        self.status_var.set("烧录成功")
                    else:
                        self.error_count += 1
                        self.status_var.set("烧录失败")
                    self.append_summary()
                    self.flash_button.configure(state="normal")
                elif kind == "error":
                    self.error_count += 1
                    self.status_var.set("烧录失败")
                    self.append_summary()
                    self.flash_button.configure(state="normal")
                    messagebox.showerror("烧录失败", value)
        except queue.Empty:
            pass
        self.root.after(100, self.process_messages)

    def append_summary(self) -> None:
        summary = (
            f"{self.status_var.get()} | "
            f"成功次数: {self.success_count} | "
            f"错误次数: {self.error_count}"
        )
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, summary + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")
        self.counts_var.set(
            f"成功次数: {self.success_count}    "
            f"错误次数: {self.error_count}"
        )

    def clear_log(self) -> None:
        self.success_count = 0
        self.error_count = 0
        self.status_var.set("就绪")
        self.counts_var.set("成功次数: 0    错误次数: 0")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")


if __name__ == "__main__":
    app_root = tk.Tk()
    app = JFlashApp(app_root)
    app_root.mainloop()