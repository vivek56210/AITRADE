"""Telegram Bot API notifier. Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; never prints the token."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request
from collections.abc import Callable

API = "https://api.telegram.org"
MAX_LEN = 4000


class TelegramError(RuntimeError):
    pass


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, post: Callable[[str, dict], dict] = _post_json,
                 retries: int = 3):
        self._token, self.chat_id, self._post, self._retries = token, chat_id, post, retries

    def send(self, text: str) -> bool:
        """Send an HTML-formatted message. Failures are reported on stderr, never raised."""
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN - 20] + "\n…(truncated)"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        for attempt in range(self._retries):
            try:
                res = self._post(f"{API}/bot{self._token}/sendMessage", payload)
                if res.get("ok"):
                    return True
                raise TelegramError(res.get("description", "unknown error"))
            except Exception as exc:
                err = str(exc).replace(self._token, "<token>")
                if attempt == self._retries - 1:
                    print(f"telegram: send failed: {err}", file=sys.stderr)
                    return False
                time.sleep(2 ** attempt)
        return False


class ConsoleNotifier:
    """Prints messages instead of sending them (--dry-run)."""

    def __init__(self, stream=sys.stdout):
        self.stream = stream
        self.sent: list[str] = []

    def send(self, text: str) -> bool:
        self.sent.append(text)
        plain = html.unescape(re.sub(r"</?[a-z]+>", "", text))
        print(f"\n----- message -----\n{plain}", file=self.stream, flush=True)
        return True


def credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (see src/README.md, Live alerts)")
    return token, chat


def notifier_from_env(dry_run: bool = False):
    if dry_run:
        return ConsoleNotifier()
    return TelegramNotifier(*credentials())


def find_chat_ids(token: str, post: Callable[[str, dict], dict] = _post_json) -> list[tuple[str, str]]:
    """Chats that recently messaged the bot: send any message to it first, then call this."""
    res = post(f"{API}/bot{token}/getUpdates", {})
    if not res.get("ok"):
        raise TelegramError(res.get("description", "getUpdates failed"))
    seen: dict[str, str] = {}
    for upd in res.get("result", []):
        chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat")
        if chat:
            name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
            seen[str(chat["id"])] = name or chat.get("username", "")
    return list(seen.items())
