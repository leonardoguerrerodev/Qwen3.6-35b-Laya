"""Terminal en bruto: /dev/tty, tamaño y lectura de teclas."""
import os
import select
import termios
import tty


class Tty:
    def __init__(self):
        self.fd = os.open("/dev/tty", os.O_RDWR)
        self.old = termios.tcgetattr(self.fd)

    def __enter__(self):
        tty.setcbreak(self.fd)
        self.write("\x1b[?1049h\x1b[?25l")
        return self

    def __exit__(self, *exc):
        self.write("\x1b[?25h\x1b[?1049l")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        os.close(self.fd)

    def write(self, s):
        os.write(self.fd, s.encode("utf-8"))

    def size(self):
        try:
            c, r = os.get_terminal_size(self.fd)
            return c, r
        except OSError:
            return 80, 24

    def key(self, timeout=1.0):
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        data = os.read(self.fd, 1)
        if data == b"\x1b":
            if select.select([self.fd], [], [], 0.03)[0]:
                data += os.read(self.fd, 8)
            else:
                return "ESC"
            return {b"\x1b[A": "UP", b"\x1b[B": "DOWN", b"\x1bOA": "UP",
                    b"\x1bOB": "DOWN",
                    b"\x1b[5~": "PgUp", b"\x1b[6~": "PgDn",
                    b"\x1b[H": "Home", b"\x1b[1~": "Home",
                    b"\x1b[F": "End", b"\x1b[4~": "End"}.get(data, "")
        if data in (b"\r", b"\n"):
            return "ENTER"
        if data == b"\t":
            return "TAB"
        if data == b"\x7f" or data == b"\x08":
            return "BACKSPACE"
        if data == b"\x03":
            return "CTRL_C"
        if data == b"\x15":
            return "CTRL_U"
        # carácter UTF-8 multibyte
        try:
            b0 = data[0]
            extra = 3 if b0 >= 0xF0 else 2 if b0 >= 0xE0 else 1 if b0 >= 0xC0 else 0
            if extra:
                data += os.read(self.fd, extra)
            return data.decode("utf-8", "ignore")
        except Exception:
            return ""
