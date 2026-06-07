"""
bal.gui.qt.calendar
===================

iCalendar (.ics) generation and "open with default calendar app" helper.

When a will is built, the plugin can create a calendar event reminding the user
to "check in" before the locktime expires.  This module turns the event data
into an RFC-5545 .ics file and opens it with the OS default application.
"""

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"

class BalCalendar:
    @staticmethod
    def write_temp_ics(content):
        fd, path = tempfile.mkstemp(prefix="event_", suffix=".ics")
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
        return path

    @staticmethod
    def open_with_default_app(calendar_app, path):
        _logger.debug("opening calendar app")
        try:
            subprocess.check_call([calendar_app, path])
            return True
        except Exception as e:
            _logger.error(f"starting calendar app {e}")
            return False


    @staticmethod
    def format_time(time):
        return time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        #return time.astimezone(timezone.utc).strftime("%Y%m%d")

    @staticmethod
    def ical_escape(text: str) -> str:
        # escape per RFC5545: backslash, ; , newlines
        text = text.encode("utf-8")
        text = (
            text.replace(b"\\", b"\\\\")
            .replace(b";", b"\\;")
            .replace(b",", b"\\,")
        )
        out =""
        temp=text.split(b"\r\n")
        for s in temp:
            encoded= s
            cut =0
            while len(encoded) >75:
                cut+=5
                encoded=f"{s[:len(s)-cut]}"
                if encoded[-1]==b"\\" and encoded[-2]!=b"\\\\":
                    cut += 1
                encoded=f"{s[:len(s)-cut]}"
                encoded=f"{encoded}...\r\n".encode("utf-8")
            if cut>0:
                out+=str(f"{s[:len(s)-cut].decode()}...\r\n")
            else:
                out+=str(f"{s.decode()}\r\n")

        return out[:-2]

    @staticmethod
    def fold_ical_line(line: str, limit: int = 75) -> str:
        # ritorna linee separate da CRLF e folding con spazio iniziale sulle righe successive
        encoded = line.encode("utf-8")
        parts = []
        while len(encoded) > limit:
            # taglia senza spezzare byte UTF-8
            cut = limit
            while (encoded[cut] & 0xC0) == 0x80:  # byte di continuazione UTF-8
                cut -= 1
            parts.append(encoded[:cut].decode("utf-8"))
            encoded = encoded[cut:]
        parts.append(encoded.decode("utf-8"))
        return "\r\n ".join(parts)
