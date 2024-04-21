from importlib.metadata import version, PackageNotFoundError
from . import util
from .logging import KometaLogger
from .args import KometaArgs, Version
from .exceptions import Continue, Deleted, Failed, FilterFailed, LimitReached, NonExisting, NotScheduled, NotScheduledRange, TimeoutExpired
from .yaml import YAML


try:
    __version__ = version("kometautils")
except PackageNotFoundError:
    __version__ = ""

__author__ = "Nathan Taggart"
__credits__ = "meisnate12"
__package_name__ = "kometautils"
__project_name__ = "Kometa-Utils"
__description__ = "Util Methods for Kometa"
__url__ = "https://github.com/Kometa-Team/Kometa-Utils"
__email__ = "kometateam@proton.me"
__license__ = 'MIT License'
__all__ = [
    "KometaLogger",
    "KometaArgs",
    "Version",
    "Continue",
    "Deleted",
    "Failed",
    "FilterFailed",
    "LimitReached",
    "NonExisting",
    "NotScheduled",
    "NotScheduledRange",
    "TimeoutExpired",
    "YAML",
]
