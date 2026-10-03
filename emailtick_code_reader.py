import argparse
import json
import re
import sys
import time
import traceback
from html import unescape
from urllib.parse import urljoin, urlparse

import requests


BASE_URL = "https://www.emailtick.com/"
ALT_BASE_URL = "https://emailtick.com/"
LOG_FILE = "emailtick_code_reader.log"
CODE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9_-]{3,31}(?![A-Za-z0-9])")
CODE_KEYWORDS = r"验证码|驗證碼|校验码|動態碼|动态码|code|verification|verify|otp"
CODE_CONTEXT_RE = re.compile(
    rf"(?:{CODE_KEYWORDS})[^\n\r]{{0,120}}?(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9_-]{{3,31}})(?![A-Za-z0-9])"
    rf"|(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9_-]{{3,31}})(?![A-Za-z0-9])[^\n\r]{{0,120}}?(?:{CODE_KEYWORDS})",
    re.I,
)
NOISE_CODES = {"1000", "2024", "2025", "2026"}
NOISE_WORDS = {
    "account",
    "code",
    "email",
    "gmail",
    "hello",
    "here",
    "login",
    "mail",
    "message",
    "notification",
    "password",
    "please",
    "security",
    "subject",
    "that",
    "this",
    "valid",
    "verify",
    "verification",
    "welcome",
    "your",
}
MAILBOX_RE = re.compile(r'<input[^>]+name=["\']mailbox["\'][^>]+value=["\']([^"\']+)', re.I)
SALT_RE = re.compile(r'<input[^>]+name=["\']salt["\'][^>]+value=["\']([^"\']+)', re.I)
ROW_RE = re.compile(r'<tr[^>]*class=["\'][^"\']*litem[^"\']*["\'][^>]*>(.*?)</tr>', re.I | re.S)
LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']*/index/index/mailbox/code/[^"\']*)["\'][^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


class EmailTickClient:
    def __init__(self, timeout=40):
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self.timeout = timeout
        self.mailbox = None
        self.salt = None

    def load_home(self):
        response = None
        for base_url in (self.base_url, ALT_BASE_URL, BASE_URL):
            try:
                response = self.session.get(base_url, timeout=self.timeout)
                if response.status_code == 403:
                    self.session.cookies.clear()
                    time.sleep(1)
                    continue
                response.raise_for_status()
                self.base_url = base_url
                break
            except requests.HTTPError:
                raise

        if response is None or response.status_code == 403:
            raise RuntimeError("EmailTick 返回 403，当前 IP/会话被临时限制，请稍后再试")

        html = response.text

        mailbox_match = MAILBOX_RE.search(html)
        salt_match = SALT_RE.search(html)
        if not mailbox_match or not salt_match:
            raise RuntimeError("无法从 EmailTick 首页解析邮箱地址或 salt")

        self.mailbox = unescape(mailbox_match.group(1)).strip()
        self.salt = unescape(salt_match.group(1)).strip()
        if not self.mailbox or not self.salt:
            raise RuntimeError("EmailTick 返回的邮箱地址或 salt 为空")

        return html

    def check_mail(self):
        if not self.mailbox or not self.salt:
            self.load_home()

        response = self.post_with_recovery(
            "/index/index/checkmail.html",
            data={"box": self.mailbox, "salt": self.salt},
            referer=self.base_url,
        )
        response.raise_for_status()
        return response.text.strip()

    def post_with_recovery(self, path, data, referer):
        try:
            response = self.session.post(
                urljoin(self.base_url, path),
                data=data,
                headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
                timeout=self.timeout,
            )
        except requests.RequestException:
            time.sleep(2)
            response = self.session.post(
                urljoin(self.base_url, path),
                data=data,
                headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
                timeout=self.timeout,
            )
        if response.status_code != 403:
            return response

        old_mailbox = self.mailbox
        self.session.cookies.clear()
        time.sleep(1)
        self.load_home()
        if old_mailbox and self.mailbox != old_mailbox:
            raise RuntimeError(
                f"EmailTick 会话已刷新，邮箱从 {old_mailbox} 变为 {self.mailbox}；请把验证码发送到新邮箱"
            )

        return self.session.post(
            urljoin(self.base_url, path),
            data=data,
            headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
            timeout=self.timeout,
        )

    def change_mailbox(self, mail_type=1):
        if not self.mailbox or not self.salt:
            self.load_home()

        old_mailbox = self.mailbox
        new_mailbox = ""
        last_response_text = ""
        payloads = (
            [("type[]", str(mail_type))],
            [("type", str(mail_type))],
        )

        for payload in payloads:
            try:
                response = self.session.post(
                    urljoin(self.base_url, "/index/index/change.html"),
                    data=payload,
                    headers={"Referer": self.base_url, "X-Requested-With": "XMLHttpRequest"},
                    timeout=self.timeout,
                )
            except requests.RequestException:
                time.sleep(2)
                response = self.session.post(
                    urljoin(self.base_url, "/index/index/change.html"),
                    data=payload,
                    headers={"Referer": self.base_url, "X-Requested-With": "XMLHttpRequest"},
                    timeout=self.timeout,
                )
            response.raise_for_status()
            last_response_text = response.text.strip()
            new_mailbox = last_response_text.strip('"')
            if new_mailbox and "@" in new_mailbox and new_mailbox != old_mailbox:
                break

        if new_mailbox == "1":
            raise RuntimeError("EmailTick 限制访问过于频繁，请稍后再换邮箱")
        if not new_mailbox or "@" not in new_mailbox or new_mailbox == old_mailbox:
            raise RuntimeError(f"换邮箱失败，接口返回: {last_response_text!r}")

        self.mailbox = new_mailbox
        self.try_activate_mailbox(new_mailbox)
        active_mailbox = self.mailbox
        self.load_home()
        if self.mailbox != active_mailbox:
            raise RuntimeError(
                "EmailTick 未接受新邮箱，会话仍然停留在旧邮箱；请稍后再试或使用 --reuse 继续当前邮箱"
            )
        return self.mailbox

    def try_activate_mailbox(self, mailbox):
        try:
            response = self.session.post(
                urljoin(self.base_url, "/index/index/goactive.html"),
                data={"mailbox": mailbox},
                headers={
                    "Origin": self.base_url.rstrip("/"),
                    "Referer": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=self.timeout,
            )
            if response.status_code == 403:
                return False
            response.raise_for_status()
            return response.text.strip().strip('"') == "1"
        except requests.RequestException:
            return False


    def list_messages(self):
        html = self.load_home()
        messages = []
        seen = set()

        for row_html in ROW_RE.findall(html):
            links = LINK_RE.findall(row_html)
            if not links:
                continue

            href = links[0][0]
            if href in seen:
                continue
            seen.add(href)

            subject_html = links[1][1] if len(links) > 1 else links[0][1]
            subject = normalize_text(subject_html)
            messages.append({"url": urljoin(self.base_url, href), "subject": subject})

        return messages

    def read_message(self, url):
        message_code = extract_message_code(url)
        if message_code:
            content = self.read_message_content(message_code, url)
            if content:
                return content

        response = self.session.get(url, headers={"Referer": BASE_URL}, timeout=self.timeout)
        response.raise_for_status()
        html = response.text
        text = normalize_text(extract_message_area(html))

        if "Loading details" in text and "[Subject]" in text:
            return ""
        return text

    def read_message_content(self, message_code, referer_url):
        response = self.post_with_recovery(
            "/index/index/mailcontent.html",
            data={"code": message_code},
            referer=referer_url,
        )
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError:
            return ""

        if data.get("status") == 0:
            return ""

        message = data.get("msg") or {}
        content = message.get("content") if isinstance(message, dict) else None
        return normalize_text(content or "")


def normalize_text(html):
    text = TAG_RE.sub(" ", html)
    return " ".join(unescape(text).split())


def extract_message_code(url):
    path = urlparse(url).path.rstrip("/")
    if "/mailbox/code/" not in path:
        return None
    return path.rsplit("/", 1)[-1]


def extract_message_area(html):
    start_markers = ("[Subject]", "Sender:", "Loading details")
    starts = [html.find(marker) for marker in start_markers if html.find(marker) != -1]
    if not starts:
        return html

    start = min(starts)
    end_candidates = [
        html.find("<div class=\"faq", start),
        html.find("<section id=\"foot\"", start),
        html.find("What is Temp Gmail?", start),
    ]
    end_candidates = [pos for pos in end_candidates if pos != -1]
    end = min(end_candidates) if end_candidates else len(html)
    return html[start:end]


def extract_code(text):
    for match in CODE_CONTEXT_RE.findall(text):
        code = next((item for item in match if item), None)
        if is_code_candidate(code):
            return code

    matches = [code for code in CODE_RE.findall(text) if is_code_candidate(code)]
    if len(matches) == 1:
        return matches[0]
    return None


def is_code_candidate(code):
    if not code:
        return False

    normalized = code.strip()
    if normalized in NOISE_CODES:
        return False
    if normalized.lower() in NOISE_WORDS:
        return False

    # Avoid treating normal words in the mail title as verification codes.
    return any(char.isdigit() for char in normalized)


def wait_for_code(client, interval, attempts, subject_keyword=None):
    attempt = 0
    while attempts <= 0 or attempt < attempts:
        attempt += 1
        client.check_mail()
        messages = client.list_messages()

        for message in messages:
            if subject_keyword and subject_keyword not in message["subject"]:
                continue

            content = client.read_message(message["url"])
            code = extract_code(content) or extract_code(message["subject"])
            if code:
                return code, message

        total = "无限" if attempts <= 0 else str(attempts)
        print(f"第 {attempt}/{total} 次未找到验证码，{interval} 秒后重试...")
        time.sleep(interval)

    return None, None


def main():
    parser = argparse.ArgumentParser(description="从 EmailTick 临时邮箱读取邮件验证码")
    parser.add_argument("--interval", type=int, default=8, help="轮询间隔秒数，默认 8")
    parser.add_argument("--attempts", type=int, default=0, help="最大轮询次数，0 表示一直等待，默认 0")
    parser.add_argument("--subject", default=None, help="只匹配包含该关键词的邮件标题，例如 DeepSeek")
    parser.add_argument("--new", action="store_true", help="启动后先尝试切换到一个新邮箱")
    parser.add_argument("--reuse", action="store_true", help="不换新邮箱，继续使用当前会话邮箱；默认就是复用")
    parser.add_argument("--type", type=int, choices=[1, 2, 3], default=1, help="换邮箱类型：1 点分隔，2 加号，3 googlemail")
    parser.add_argument("--no-pause", action="store_true", help="结束后不等待按 Enter")
    args = parser.parse_args()

    client = EmailTickClient()
    client.load_home()
    if args.new:
        old_mailbox = client.mailbox
        client.change_mailbox(args.type)
        print(f"原邮箱: {old_mailbox}")
        print("已切换新邮箱。")
    print(f"临时邮箱: {client.mailbox}")
    print("请把验证码邮件发送到上面的邮箱，脚本会自动轮询收件箱。")
    print("未收到验证码时会一直等待；按 Ctrl+C 可以停止。")

    code, message = wait_for_code(
        client,
        interval=args.interval,
        attempts=args.attempts,
        subject_keyword=args.subject,
    )
    if not code:
        raise SystemExit("未在限定时间内找到验证码")

    print(f"邮件标题: {message['subject']}")
    print(f"验证码: {code}")


def pause_before_exit():
    if sys.platform.startswith("win"):
        try:
            input("\n按 Enter 退出...")
        except EOFError:
            time.sleep(10)


def log_error(message):
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write("\n" + "=" * 60 + "\n")
        file.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        file.write(message + "\n")
        file.write(traceback.format_exc() + "\n")


if __name__ == "__main__":
    no_pause = "--no-pause" in sys.argv
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断，程序已停止。")
    except SystemExit as exc:
        if exc.code:
            print(exc)
            log_error(str(exc))
    except requests.RequestException as exc:
        print(f"网络请求失败: {exc}")
        log_error(f"网络请求失败: {exc}")
    except Exception as exc:
        print(f"程序出错: {exc}")
        log_error(f"程序出错: {exc}")
    finally:
        if not no_pause:
            pause_before_exit()
