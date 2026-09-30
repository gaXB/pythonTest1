import tkinter as tk
from tkinter import messagebox


def add(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b


def calculate() -> None:
    try:
        first = float(first_entry.get())
        second = float(second_entry.get())
    except ValueError:
        messagebox.showerror("\u8f93\u5165\u9519\u8bef", "\u8bf7\u8f93\u5165\u6709\u6548\u7684\u6570\u5b57\u3002")
        return

    result1_var.set(str(add(first, second)))
    result2_var.set(str(first + second))


def clear() -> None:
    first_entry.delete(0, tk.END)
    second_entry.delete(0, tk.END)
    result1_var.set("")
    result2_var.set("")
    first_entry.focus_set()


root = tk.Tk()
root.title("\u52a0\u6cd5\u8ba1\u7b97\u5668")
root.resizable(False, False)

main_frame = tk.Frame(root, padx=20, pady=20)
main_frame.grid()

tk.Label(main_frame, text="\u52a0\u6570 A:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
first_entry = tk.Entry(main_frame, width=24)
first_entry.grid(row=0, column=1, padx=5, pady=5)

tk.Label(main_frame, text="\u52a0\u6570 B:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
second_entry = tk.Entry(main_frame, width=24)
second_entry.grid(row=1, column=1, padx=5, pady=5)

result1_var = tk.StringVar()
result2_var = tk.StringVar()

tk.Label(main_frame, text="\u7ed3\u679c 1:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
tk.Entry(main_frame, textvariable=result1_var, width=24, state="readonly").grid(row=2, column=1, padx=5, pady=5)

tk.Label(main_frame, text="\u7ed3\u679c 2:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
tk.Entry(main_frame, textvariable=result2_var, width=24, state="readonly").grid(row=3, column=1, padx=5, pady=5)

button_frame = tk.Frame(main_frame)
button_frame.grid(row=4, column=0, columnspan=2, pady=(12, 0))
tk.Button(button_frame, text="\u8ba1\u7b97", width=8, command=calculate).grid(row=0, column=0, padx=4)
tk.Button(button_frame, text="\u6e05\u7a7a", width=8, command=clear).grid(row=0, column=1, padx=4)
tk.Button(button_frame, text="\u9000\u51fa", width=8, command=root.destroy).grid(row=0, column=2, padx=4)

first_entry.focus_set()
root.mainloop()