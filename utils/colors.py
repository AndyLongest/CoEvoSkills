from __future__ import annotations


class C:
    """ANSI color codes for terminal output."""
    CYAN = '\033[36m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    @classmethod
    def color(cls, text: str, *codes: str) -> str:
        return ''.join(codes) + text + cls.RESET

    @classmethod
    def cyan(cls, text: str) -> str:
        return cls.CYAN + text + cls.RESET

    @classmethod
    def green(cls, text: str) -> str:
        return cls.GREEN + text + cls.RESET

    @classmethod
    def yellow(cls, text: str) -> str:
        return cls.YELLOW + text + cls.RESET

    @classmethod
    def red(cls, text: str) -> str:
        return cls.RED + text + cls.RESET

    @classmethod
    def blue(cls, text: str) -> str:
        return cls.BLUE + text + cls.RESET

    @classmethod
    def bold(cls, text: str) -> str:
        return cls.BOLD + text + cls.RESET

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.DIM + text + cls.RESET

    @classmethod
    def header(cls, text: str) -> str:
        return cls.BOLD + cls.CYAN + text + cls.RESET

    @classmethod
    def success(cls, text: str) -> str:
        return cls.BOLD + cls.GREEN + text + cls.RESET

    @classmethod
    def warn(cls, text: str) -> str:
        return cls.YELLOW + text + cls.RESET

    @classmethod
    def fail(cls, text: str) -> str:
        return cls.RED + text + cls.RESET
