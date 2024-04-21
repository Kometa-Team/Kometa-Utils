import logging, platform, psutil, requests, sys, traceback
from datetime import datetime
from functools import cached_property
from json import JSONDecodeError
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .exceptions import Failed

logger = None

class RedactingFormatter(logging.Formatter):
    _secrets = []

    def __init__(self, orig_format, secrets=None):
        self.orig_formatter = logging.Formatter(orig_format)
        if secrets:
            self._secrets.extend(secrets)
        super().__init__()

    def format(self, record):
        for secret in self._secrets:
            if secret:
                record.msg = record.msg.replace(secret, "(redacted)")
        return self.orig_formatter.format(record)

    def __getattr__(self, attr):
        return getattr(self.orig_formatter, attr)

def log_namer(default_name):
    base, ext, num = default_name.split(".")
    return f"{base}-{num}.{ext}"

class Stat:
    def __init__(self, name=None):
        self.name = name
        self.start = datetime.now()
        self.stats = {}

    def __getitem__(self, key):
        if key in self.stats:
            return self.stats[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        self.stats[key] = value

    @cached_property
    def end(self):
        return datetime.now()

    @cached_property
    def runtime(self):
        return str(self.end - self.start).split(".")[0]

    def __str__(self):
        return self.runtime

def my_except_hook(exctype, value, tb):
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tb)
    elif logger:
        logger.critical(f"Traceback (most recent call last):\n{''.join(traceback.format_tb(tb))}{exctype.__name__}: {value}", discord=True)

def fmt_filter(record):
    record.levelname = f"[{record.levelname}]"
    record.filename = f"[{record.filename}:{record.lineno}]"
    return True

class KometaLogger:
    def __init__(self, name, log_name, log_dir, log_file=None, discord_url=None, ignore_ghost=False, is_debug=True, is_trace=False, log_requests=False):
        global logger
        logger = self
        sys.excepthook = my_except_hook
        self.name = name
        self.log_name = log_name
        self.log_dir = Path(log_dir)
        self.log_file = log_file
        self.discord_url = discord_url
        self.is_debug = is_debug
        self.is_trace = is_trace
        self.log_requests = log_requests
        self.ignore_ghost = ignore_ghost
        self.current = None
        self.stats = {self.current: Stat()}
        self.warnings = {}
        self.errors = {}
        self.criticals = {}
        self.spacing = 0
        self.screen_width = 100
        self.separating_character = "="
        self.filename_spacing = 27
        self.thumbnail_url = "https://github.com/Kometa-Team/Kometa/raw/master/docs/_static/favicon.png"
        self.bot_name = "Metabot"
        self.bot_image_url = "https://github.com/Kometa-Team/Kometa/raw/master/.github/logo.png"
        if not self.log_file:
            self.log_file = f"{self.log_name}.log"
        self.log_path = self.log_dir / self.log_file
        self.log_path.parent.mkdir(exist_ok=True)
        self._logger = logging.getLogger(None if self.log_requests else self.log_name)
        self._logger.setLevel(logging.DEBUG)
        self.cmd_handler = logging.StreamHandler()
        self.cmd_handler.setLevel(logging.DEBUG if self.is_debug else logging.INFO)
        self._formatter(handler=self.cmd_handler)
        self._logger.addHandler(self.cmd_handler)
        self.main_handler = None
        self.old__log = self._logger._log
        self._logger._log = self.new__log

    def new__log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, center=False, stacklevel=2):
        trace = level == logging.NOTSET
        log_only = False
        msg = str(msg)
        if center:
            msg = self._centered(msg)
        if trace:
            level = logging.DEBUG
        if trace or msg.startswith("|"):
            self._formatter(trace=trace, border=not msg.startswith("|"))
        if self.spacing > 0:
            self.exorcise()
        if "\n" in msg:
            for i, line in enumerate(msg.split("\n")):
                self.old__log(level, line, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)
                if i == 0:
                    self._formatter(log_only=True, space=True)
            log_only = True
        else:
            self.old__log(level, msg, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)

        if trace or log_only or msg.startswith("|"):
            self._formatter()

    def add_main_handler(self, count=9):
        self.main_handler = self._add_handler(self.log_path, count=count)
        self.main_handler.addFilter(fmt_filter)
        self._logger.addHandler(self.main_handler)

    def remove_main_handler(self):
        self._logger.removeHandler(self.main_handler)

    def _add_handler(self, log_file, count=3):
        _handler = RotatingFileHandler(log_file, delay=True, mode="w", backupCount=count, encoding="utf-8")
        _handler.namer = log_namer
        self._formatter(handler=_handler)
        if Path(log_file).is_file():
            self._logger.removeHandler(_handler)
            _handler.doRollover()
            self._logger.addHandler(_handler)
        return _handler

    def _formatter(self, handler=None, border=True, trace=False, log_only=False, space=False):
        console = f"%(message)-{self.screen_width - 2}s"
        console = f"| {console} |" if border else console
        file = f"{' ' * 65}" if space else f"[%(asctime)s] %(filename)-{self.filename_spacing}s {'[TRACE]   ' if trace else '%(levelname)-10s'} "
        handlers = [handler] if handler else self._logger.handlers
        for h in handlers:
            if not log_only or isinstance(h, RotatingFileHandler):
                h.setFormatter(RedactingFormatter(f"{file if isinstance(h, RotatingFileHandler) else ''}{console}"))

    def _center(self, text, total, sep=None, left=False, right=False):
        if sep is None:
            sep = " "
        text = str(text)
        space = total - len(text)
        if space % 2 == 1:
            text = f"{sep}{text}" if right else f"{text}{sep}"
            space -= 1
        side = int(space / 2)
        if left:
            return f"{text}{sep * side}{sep * side}"
        elif right:
            return f"{sep * side}{sep * side}{text}"
        else:
            return f"{sep * side}{text}{sep * side}"

    def _centered(self, text, sep=None, side_space=True, left=False, right=False):
        text = str(text)
        if len(text) > self.screen_width - 2:
            return text
        side = " " if side_space else sep if sep else ""
        final = self._center(f"{side}{text}{side}", self.screen_width - 2, sep=sep, left=left, right=right)
        return final

    def _separator(self, text=None, space=True, border=True, enclose=False, sep=None, debug=False, trace=False, side_space=True, start=None, left=False, right=False, stacklevel=7):
        self.separator(text=text, space=space, border=border, enclose=enclose, sep=sep, debug=debug, trace=trace, side_space=side_space, start=start, left=left, right=right, stacklevel=stacklevel)

    def separator(self, text=None, space=True, border=True, enclose=False, sep=None, debug=False, trace=False, side_space=True, start=None, left=False, right=False, stacklevel=5):
        if start is not None:
            self.start(start)
        if trace and not self.is_trace:
            return None
        character = sep or self.separating_character
        sep = " " if space else character
        border_text = f"|{character * self.screen_width}|"
        text_list = text.split("\n") if text else []
        if text and enclose:
            text_width = len(max(text_list, key=len)) + (2 if side_space else 0)
            box_width = text_width + 2
            if box_width < self.screen_width - 2:
                border_text = self._center(f"{box_width * character}", self.screen_width - 2, left=left, right=right)
            text_list = [f"|{self._center(t, text_width)}|" for t in text_list]
        if border:
            self.print(border_text, debug=debug, trace=trace, stacklevel=stacklevel)
        if text:
            for t in text_list:
                msg = f"|{sep}{self._centered(t, sep=None if enclose else sep, side_space=side_space and not enclose, left=left, right=right)}{sep}|"
                self.print(msg, debug=debug, trace=trace, stacklevel=stacklevel)
            if border:
                self.print(border_text, debug=debug, trace=trace, stacklevel=stacklevel)

    def _print(self, msg="", critical=False, error=False, warning=False, debug=False, trace=False, stacklevel=6):
        self.print(msg=msg, critical=critical, error=error, warning=warning, debug=debug, trace=trace, stacklevel=stacklevel)

    def print(self, msg="", critical=False, error=False, warning=False, debug=False, trace=False, stacklevel=4):
        if critical:
            self.critical(msg, stacklevel=stacklevel)
        elif error:
            self.error(msg, stacklevel=stacklevel)
        elif warning:
            self.warning(msg, stacklevel=stacklevel)
        elif debug:
            self.debug(msg, stacklevel=stacklevel)
        elif trace:
            self.trace(msg, stacklevel=stacklevel)
        else:
            self.info(msg, stacklevel=stacklevel)

    def _trace(self, msg="", center=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.trace(msg=msg, center=center, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def trace(self, msg="", center=False, log=True, discord=False, start=None, rows=None, stacklevel=3):
        if self.is_trace:
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.NOTSET, msg, [], center=center, stacklevel=stacklevel)
            if discord:
                self.discord_request(" Trace", msg, rows=rows)
        return str(msg)

    def _debug(self, msg="", center=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.debug(msg=msg, center=center, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def debug(self, msg="", center=False, log=True, discord=False, start=None, rows=None, stacklevel=3):
        if self._logger.isEnabledFor(logging.DEBUG):
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.DEBUG, msg, [], center=center, stacklevel=stacklevel)
            if discord:
                self.discord_request(" Debug", msg, rows=rows)
        return str(msg)

    def _info(self, msg="", center=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.info(msg=msg, center=center, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def info(self, msg="", center=False, log=True, discord=False, start=None, rows=None, stacklevel=3):
        if self._logger.isEnabledFor(logging.INFO):
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.INFO, msg, [], center=center, stacklevel=stacklevel)
            if discord:
                self.discord_request("", msg, rows=rows)
        return str(msg)

    def _warning(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.warning(msg=msg, center=center, group=group, ignore=ignore, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def warning(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, start=None, rows=None, stacklevel=3):
        if self._logger.isEnabledFor(logging.WARNING):
            if not ignore:
                if group not in self.warnings:
                    self.warnings[group] = []
                self.warnings[group].append(msg)
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.WARNING, msg, [], center=center, stacklevel=stacklevel)
            if discord:
                self.discord_request(" Warning", msg, rows=rows, color=0xbc0030)
        return str(msg)

    def _error(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.error(msg=msg, center=center, group=group, ignore=ignore, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def error(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, start=None, rows=None, stacklevel=3):
        if self._logger.isEnabledFor(logging.ERROR):
            if not ignore:
                if group not in self.errors:
                    self.errors[group] = []
                self.errors[group].append(msg)
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.ERROR, msg, [], center=center, stacklevel=stacklevel)
            if discord:
                self.discord_request(" Error", msg, rows=rows, color=0xbc0030)
        return str(msg)

    def _critical(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, rows=None, stacklevel=5):
        return self.critical(msg=msg, center=center, group=group, ignore=ignore, log=log, discord=discord, rows=rows, stacklevel=stacklevel)

    def critical(self, msg="", center=False, group=None, ignore=False, log=True, discord=False, start=None, rows=None, exc_info=None, stacklevel=3):
        if self._logger.isEnabledFor(logging.CRITICAL):
            if not ignore:
                if group not in self.criticals:
                    self.criticals[group] = []
                self.criticals[group].append(msg)
            if start is not None:
                self.start(start)
            if log:
                self.new__log(logging.CRITICAL, msg, [], center=center, exc_info=exc_info, stacklevel=stacklevel)
            if discord:
                self.discord_request(" Critical Failure", msg, rows=rows, color=0xbc0030)
        return str(msg)

    def stacktrace(self, trace=False):
        self._print(traceback.format_exc(), debug=not trace, trace=trace)

    def _space(self, display_title):
        display_title = str(display_title)
        space_length = self.spacing - len(display_title)
        if space_length > 0:
            display_title += " " * space_length
        return display_title

    def ghost(self, text):
        if not self.ignore_ghost:
            try:
                final_text = f"| {text}"
            except UnicodeEncodeError:
                text = text.encode("utf-8")
                final_text = f"| {text}"
            print(self._space(final_text), end="\r")
            self.spacing = len(text) + 2

    def exorcise(self):
        if not self.ignore_ghost:
            print(self._space(" "), end="\r")
            self.spacing = 0

    def secret(self, text):
        text = text if isinstance(text, list) else [text]
        for t in text:
            if t and str(t) not in RedactingFormatter._secrets:
                RedactingFormatter._secrets.append(str(t))

    def discord_request(self, title, description=None, rows=None, color=0x00bc8c):
        if self.discord_url:
            embed = {
                "title": f"{self.name}{title}",
                "color": color,
                "timestamp": str(datetime.utcnow())
            }
            if description:
                embed["description"] = description
            if self.thumbnail_url:
                embed["thumbnail"] = {"url": self.thumbnail_url, "height": 0, "width": 0}
            if rows:
                fields = []
                for row in rows:
                    for col in row:
                        col_name = col[0] if isinstance(col, tuple) else ""
                        col_value = col[1] if isinstance(col, tuple) else col
                        if not col_value:
                            col_value = f"**{col_name}**"
                            col_name = ""
                        field = {"name": str(col_name)}
                        if col_value:
                            field["value"] = str(col_value)
                        if len(row) > 1:
                            field["inline"] = True
                        fields.append(field)
                embed["fields"] = fields
            try:
                json = {"embeds": [embed], "username": self.bot_name, "avatar_url": self.bot_image_url}
                response = requests.post(self.discord_url, json=json)
                try:
                    response_json = response.json()
                    if response.status_code >= 400:
                        self.discord_url = None
                        raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
                except JSONDecodeError:
                    if response.status_code >= 400:
                        self.discord_url = None
                        raise Failed(f"({response.status_code} [{response.reason}])")
            except requests.exceptions.RequestException:
                self.discord_url = None
                raise Failed(f"Discord URL Connection Failure")

    def start(self, name=None):
        self.current = name
        self[name] = Stat()

    def switch(self, name=None):
        self.current = name

    def end(self, name=None):
        if name is None:
            name = self.current
        return self[name].end

    def runtime(self, name=None):
        if name is None:
            name = self.current
        return self[name].runtime

    def stats(self, name=None):
        if name is None:
            name = self.current
        return self[name].stats

    def stat(self, key, value, name=None):
        if name is None:
            name = self.current
        self[name][key] = value

    def __getitem__(self, name):
        if name in self.stats:
            return self.stats[name]
        raise KeyError(name)

    def __setitem__(self, key, value):
        self.stats[key] = value

    def header(self, kometa_args, sub=False, discord_update=False, override=None, count=9):
        self.add_main_handler(count=count)
        self._separator()
        self._info(" __  ___   ______   .___  ___.  _______ .___________.    ___      ", center=True)
        self._info("|  |/  /  /  __  \\  |   \\/   | |   ____||           |   /   \\     ", center=True)
        self._info("|  '  /  |  |  |  | |  \\  /  | |  |__   `---|  |----`  /  ^  \\    ", center=True)
        self._info("|    <   |  |  |  | |  |\\/|  | |   __|      |  |      /  /_\\  \\   ", center=True)
        self._info("|  .  \\  |  `--'  | |  |  |  | |  |____     |  |     /  _____  \\  ", center=True)
        self._info("|__|\\__\\  \\______/  |__|  |__| |_______|    |__|    /__/     \\__\\ ", center=True)
        if sub:
            self._info(self.name, center=True)
            self._info()

        self._info(f"    Version: {kometa_args.local_version} {kometa_args.system_version}")
        if kometa_args.update_version:
            if discord_update and self.discord_url:
                self._warning("New Version Available!", log=False, discord=True, rows=[
                    [("Current", str(kometa_args.local_version)), ("Latest", kometa_args.update_version)],
                    [("Updates", kometa_args.update_notes)]
                ])
            self._info(f"    Newest Version: {kometa_args.update_version}")
        self._info(f"    Platform: {platform.platform()}")
        self._info(f"    Memory: {round(psutil.virtual_memory().total / (1024.0 ** 3))} GB")
        self._separator(debug=True)

        run_arg = " ".join([f'"{s}"' if " " in s else s for s in sys.argv[:]])
        self._debug(f"Run Command: {run_arg}")
        for o in kometa_args.options:
            value = override[o["key"]] if override and o["key"] in override else kometa_args.choices[o['key']]
            self._debug(f"--{o['key']} ({o['env']}): {value}")

    def report(self, title, rows, description=None, width=None, discord=False):
        self._separator(title)
        if description:
            self._info(description)
        for row in rows:
            if len(row) > 1:
                length = 0 if width is None else width
                if width is None:
                    for k, v in row:
                        if (new_length := len(str(k))) > length:
                            length = new_length
                for k, v in row:
                    self._info(f"{k:<{length}} | {v}")
            elif isinstance(row[0], tuple):
                if not row[0][1]:
                    self._separator(row[0][0], space=False, border=False)
                elif not row[0][0]:
                    self._info(f"{row[0][1]}")
                elif width is None:
                    self._info(f"{row[0][0]} | {row[0][1]}")
                else:
                    self._info(f"{row[0][0]:<{width}} | {row[0][1]}")
            else:
                self._info(row[0])
        self._separator()
        if discord:
            self.discord_request(title, description=description, rows=rows)

    def error_report(self, warning=False, error=True, critical=True, group_only=False):
        for check, title, e_dict in [
            (warning, "Warning", self.warnings),
            (error, "Error", self.errors),
            (critical, "Critical", self.criticals)
        ]:
            if check and e_dict:
                self._separator(f"{title} Report")
                for k, v in e_dict.items():
                    if group_only and k is None:
                        continue
                    self._info()
                    self._info(f"{'Generic' if k is None else k} {title}s: ")
                    for e in v:
                        self._error(f"  {e}", ignore=True)
