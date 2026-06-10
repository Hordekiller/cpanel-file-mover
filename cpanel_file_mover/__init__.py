"""cpanel_file_mover package

Provides a robust, well-documented API to transfer files between local
paths and remote SFTP servers. Use the `transfer()` function for a
simple CLI-friendly interface.
"""

from .transfer import transfer, SFTPConnection, parse_target

__all__ = ["transfer", "SFTPConnection", "parse_target"]
