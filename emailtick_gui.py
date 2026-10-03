import queue
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk

import requests

from emailtick_code_reader import EmailTickClient, extract_code


class EmailTickGui:
    def __init__(self, root):
        self.root = root
        self.root.title("TickMail")
        self.root.geometry("860x680")
        self.root.minsize(760, 560)

        self.client = EmailTickClient(timeout=45)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None

        self.mailbox_var = tk.StringVar(value="正在加载...")
        self.code_var = tk.StringVar(value="")
        self.subject_var = tk.StringVar(value="")
        self.interval_var = tk.IntVar(value=8)
        self.type_var = tk.IntVar(value=1)
        self.messages = []
        self.checking_mail = False

        self.build_ui()
        self.set_running(False)
        self.run_worker(self.load_mailbox_worker)
        self.root.after(100, self.process_events)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        mailbox_frame = ttk.LabelFrame(outer, text="临时邮箱", padding=10)
        mailbox_frame.pack(fill=tk.X)

        ttk.Entry(mailbox_frame, textvariable=self.mailbox_var, font=("Consolas", 12)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        ttk.Button(mailbox_frame, text="复制", command=self.copy_mailbox).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(mailbox_frame, text="刷新", command=self.refresh_mailbox).pack(side=tk.LEFT)

        control_frame = ttk.LabelFrame(outer, text="操作", padding=10)
        control_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(control_frame, text="换邮箱类型:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(control_frame, text="点号", variable=self.type_var, value=1).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(control_frame, text="加号", variable=self.type_var, value=2).grid(row=0, column=2, sticky="w")
        ttk.Radiobutton(control_frame, text="googlemail", variable=self.type_var, value=3).grid(row=0, column=3, sticky="w")
        self.change_button = ttk.Button(control_frame, text="手动换邮箱", command=self.change_mailbox)
        self.change_button.grid(row=0, column=4, padx=(16, 0), sticky="w")

        ttk.Label(control_frame, text="标题关键词:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(control_frame, textvariable=self.subject_var, width=22).grid(row=1, column=1, columnspan=2, sticky="we", pady=(10, 0))
        ttk.Label(control_frame, text="间隔秒:").grid(row=1, column=3, sticky="e", pady=(10, 0))
        ttk.Spinbox(control_frame, from_=3, to=60, textvariable=self.interval_var, width=8).grid(
            row=1, column=4, sticky="w", pady=(10, 0), padx=(16, 0)
        )

        self.start_button = ttk.Button(control_frame, text="开始获取验证码", command=self.start_polling)
        self.start_button.grid(row=2, column=0, columnspan=2, sticky="we", pady=(12, 0))
        self.stop_button = ttk.Button(control_frame, text="停止", command=self.stop_polling)
        self.stop_button.grid(row=2, column=2, sticky="we", pady=(12, 0), padx=(8, 0))
        self.check_button = ttk.Button(control_frame, text="检测邮件", command=self.check_mail_once)
        self.check_button.grid(row=2, column=3, sticky="we", pady=(12, 0), padx=(8, 0))
        self.read_button = ttk.Button(control_frame, text="读取选中邮件", command=self.read_selected_message)
        self.read_button.grid(row=2, column=4, sticky="we", pady=(12, 0), padx=(8, 0))

        for index in range(5):
            control_frame.columnconfigure(index, weight=1)

        result_frame = ttk.LabelFrame(outer, text="验证码", padding=10)
        result_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Entry(result_frame, textvariable=self.code_var, font=("Consolas", 18), justify="center").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        ttk.Button(result_frame, text="复制验证码", command=self.copy_code).pack(side=tk.LEFT)

        messages_frame = ttk.LabelFrame(outer, text="邮件列表", padding=10)
        messages_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.messages_tree = ttk.Treeview(
            messages_frame,
            columns=("subject", "url"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        self.messages_tree.heading("subject", text="标题")
        self.messages_tree.heading("url", text="链接")
        self.messages_tree.column("subject", width=360, anchor="w")
        self.messages_tree.column("url", width=420, anchor="w")
        self.messages_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        messages_scrollbar = ttk.Scrollbar(messages_frame, orient=tk.VERTICAL, command=self.messages_tree.yview)
        messages_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.messages_tree.configure(yscrollcommand=messages_scrollbar.set)
        self.messages_tree.bind("<Double-1>", lambda _event: self.read_selected_message())

        log_frame = ttk.LabelFrame(outer, text="日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        source_link = ttk.Label(
            outer,
            text="开源地址: https://github.com/8797a/TickMail",
            foreground="#2563eb",
            cursor="hand2",
        )
        source_link.pack(anchor="e", pady=(8, 0))
        source_link.bind(
            "<Button-1>",
            lambda _event: webbrowser.open("https://github.com/8797a/TickMail"),
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def run_worker(self, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()
        return thread

    def load_mailbox_worker(self):
        try:
            self.client.load_home()
            self.events.put(("mailbox", self.client.mailbox))
            self.events.put(("log", f"当前邮箱: {self.client.mailbox}"))
        except requests.RequestException as exc:
            self.events.put(("log", f"加载邮箱超时，稍后可点刷新重试: {exc}"))
        except Exception as exc:
            self.events.put(("error", f"加载邮箱失败: {exc}"))

    def refresh_mailbox(self):
        self.log("正在刷新当前邮箱...")
        self.run_worker(self.load_mailbox_worker)

    def change_mailbox(self):
        if self.worker and self.worker.is_alive():
            self.log("正在获取验证码，请先停止后再换邮箱。")
            return
        self.set_controls_enabled(False)
        self.log("正在手动换邮箱...")
        self.run_worker(self.change_mailbox_worker, self.type_var.get())

    def change_mailbox_worker(self, mail_type):
        try:
            old_mailbox = self.client.mailbox or ""
            new_mailbox = self.client.change_mailbox(mail_type)
            self.events.put(("mailbox", new_mailbox))
            self.events.put(("log", f"已换邮箱: {old_mailbox} -> {new_mailbox}"))
        except requests.RequestException as exc:
            self.events.put(("log", f"换邮箱网络超时，可稍后再点手动换邮箱: {exc}"))
        except Exception as exc:
            self.events.put(("error", f"换邮箱失败: {exc}"))
        finally:
            self.events.put(("controls", True))

    def start_polling(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.code_var.set("")
        self.set_running(True)
        self.worker = self.run_worker(self.polling_worker)

    def stop_polling(self):
        self.stop_event.set()
        self.log("正在停止...")

    def check_mail_once(self):
        if self.checking_mail:
            return
        self.checking_mail = True
        self.check_button.configure(state=tk.DISABLED, text="检测中 6")
        self.log("正在检测邮件，6 秒后刷新列表...")
        self.run_worker(self.check_mail_worker)
        self.countdown_check_button(6)

    def countdown_check_button(self, seconds_left):
        if seconds_left <= 0:
            self.check_button.configure(text="检测邮件")
            return
        self.check_button.configure(text=f"检测中 {seconds_left}")
        self.root.after(1000, lambda: self.countdown_check_button(seconds_left - 1))

    def check_mail_worker(self):
        try:
            if not self.client.mailbox:
                self.client.load_home()
                self.events.put(("mailbox", self.client.mailbox))
            self.client.check_mail()
            time.sleep(6)
            messages = self.client.list_messages()
            self.events.put(("messages", messages))
            self.events.put(("log", f"检测完成，找到 {len(messages)} 封邮件。"))
        except Exception as exc:
            self.events.put(("error", f"检测邮件失败: {exc}"))
        finally:
            self.events.put(("check_done", None))

    def read_selected_message(self):
        selection = self.messages_tree.selection()
        if not selection:
            self.log("请先在邮件列表里选中一封邮件。")
            return
        index = int(selection[0])
        if index < 0 or index >= len(self.messages):
            self.log("选中的邮件索引无效。")
            return
        self.log("正在读取选中邮件内容...")
        self.read_button.configure(state=tk.DISABLED)
        self.run_worker(self.read_message_worker, self.messages[index])

    def read_message_worker(self, message):
        try:
            content = self.client.read_message(message["url"])
            code = extract_code(content) or extract_code(message["subject"])
            self.events.put(("log", f"邮件标题: {message['subject']}"))
            if code:
                self.events.put(("code", code))
                self.events.put(("log", f"验证码: {code}"))
            else:
                preview = content[:500] if content else "空内容"
                self.events.put(("log", f"未提取到验证码，邮件内容预览: {preview}"))
        except Exception as exc:
            self.events.put(("error", f"读取邮件失败: {exc}"))
        finally:
            self.events.put(("read_done", None))

    def polling_worker(self):
        subject_keyword = self.subject_var.get().strip() or None
        interval = max(3, int(self.interval_var.get() or 8))
        attempt = 0

        try:
            if not self.client.mailbox:
                self.client.load_home()
                self.events.put(("mailbox", self.client.mailbox))

            self.events.put(("log", f"请把验证码邮件发送到: {self.client.mailbox}"))
            while not self.stop_event.is_set():
                attempt += 1
                try:
                    self.client.check_mail()
                    messages = self.client.list_messages()
                except requests.RequestException as exc:
                    self.events.put(("log", f"网络超时或连接失败，下一轮继续重试: {exc}"))
                    self.stop_event.wait(interval)
                    continue
                except RuntimeError as exc:
                    self.events.put(("log", f"会话提示: {exc}"))
                    self.stop_event.wait(interval)
                    continue

                for message in messages:
                    if subject_keyword and subject_keyword not in message["subject"]:
                        continue
                    try:
                        content = self.client.read_message(message["url"])
                    except requests.RequestException as exc:
                        self.events.put(("log", f"读取邮件正文超时，下一轮继续重试: {exc}"))
                        continue
                    code = extract_code(content) or extract_code(message["subject"])
                    if code:
                        self.events.put(("code", code))
                        self.events.put(("log", f"邮件标题: {message['subject']}"))
                        self.events.put(("log", f"验证码: {code}"))
                        self.events.put(("done", None))
                        return

                self.events.put(("log", f"第 {attempt} 次未找到验证码，{interval} 秒后重试..."))
                self.stop_event.wait(interval)
        except Exception as exc:
            self.events.put(("error", f"获取验证码失败: {exc}"))
        finally:
            self.events.put(("done", None))

    def process_events(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "mailbox":
                    self.mailbox_var.set(payload)
                elif event == "code":
                    self.code_var.set(payload)
                    self.copy_to_clipboard(payload)
                    self.log(f"验证码已自动复制到剪贴板: {payload}")
                elif event == "log":
                    self.log(payload)
                elif event == "messages":
                    self.set_messages(payload)
                elif event == "error":
                    self.log(payload)
                elif event == "done":
                    self.set_running(False)
                elif event == "controls":
                    self.set_controls_enabled(bool(payload))
                elif event == "check_done":
                    self.checking_mail = False
                    self.check_button.configure(state=tk.NORMAL, text="检测邮件")
                elif event == "read_done":
                    self.read_button.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def set_running(self, running):
        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.change_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.check_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.read_button.configure(state=tk.DISABLED if running else tk.NORMAL)

    def set_controls_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.change_button.configure(state=state)
        self.start_button.configure(state=state)
        self.check_button.configure(state=state)
        self.read_button.configure(state=state)

    def set_messages(self, messages):
        self.messages = messages
        for item in self.messages_tree.get_children():
            self.messages_tree.delete(item)
        for index, message in enumerate(messages):
            self.messages_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(message.get("subject", ""), message.get("url", "")),
            )

    def copy_mailbox(self):
        self.copy_to_clipboard(self.mailbox_var.get())
        self.log("邮箱已复制。")

    def copy_code(self):
        if self.code_var.get():
            self.copy_to_clipboard(self.code_var.get())
            self.log("验证码已复制。")

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def log(self, message):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, time.strftime("[%H:%M:%S] ") + message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main():
    root = tk.Tk()
    EmailTickGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()

