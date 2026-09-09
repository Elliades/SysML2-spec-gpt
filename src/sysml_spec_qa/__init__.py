"""SysML v2 / KerML spec search for Cursor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sysml-spec-qa")
except PackageNotFoundError:
    __version__ = "0.1.0"
