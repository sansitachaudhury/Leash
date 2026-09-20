"""
Structured logging for Leash — AI Agent Reliability Engine.
Provides consistent, colorized output with stage tracking.
"""
import time


class Logger:
    """A simple structured logger with stage tracking and colorized output."""

    def __init__(self, module: str, enabled: bool = True):
        self.module = module
        self.enabled = enabled
        self._stage_start = None

    def _emit(self, level: str, msg: str, symbol: str = ""):
        if not self.enabled:
            return
        ts = time.strftime("%H:%M:%S", time.localtime())
        colors = {
            "INFO": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "DEBUG": "\033[36m"
        }
        reset = "\033[0m"
        bold = "\033[1m"
        dim = "\033[2m"
        color = colors.get(level, "")
        sym = f" {symbol}" if symbol else ""
        try:
            print(
                f"{dim}{ts}{reset} {color}{level:>5}{reset} "
                f"{bold}{self.module}{reset}{sym} {msg}",
                flush=True,
            )
        except UnicodeEncodeError:
            # Windows cp1252 fallback: strip non-ASCII
            safe_msg = msg.encode('ascii', 'replace').decode('ascii')
            safe_sym = symbol.encode('ascii', 'replace').decode('ascii') if symbol else ''
            print(
                f"{dim}{ts}{reset} {color}{level:>5}{reset} "
                f"{bold}{self.module}{reset} {safe_sym} {safe_msg}",
                flush=True,
            )

    def info(self, msg: str, symbol: str = ""):
        self._emit("INFO", msg, symbol or "→")

    def warn(self, msg: str):
        self._emit("WARN", msg, "⚠")

    def error(self, msg: str):
        self._emit("ERROR", msg, "✗")

    def debug(self, msg: str):
        self._emit("DEBUG", msg)

    def stage(self, label: str):
        if not self.enabled:
            return
        self._stage_start = time.time()
        self._emit("INFO", label, "▶")

    def done(self, label: str = ""):
        if not self.enabled:
            return
        elapsed = ""
        if self._stage_start:
            ms = (time.time() - self._stage_start) * 1000
            elapsed = f" ({ms:.0f}ms)" if ms < 1000 else f" ({ms / 1000:.1f}s)"
            self._stage_start = None
        self._emit("INFO", f"{label}{elapsed}", "✓")


def get_logger(module: str) -> Logger:
    return Logger(module)
