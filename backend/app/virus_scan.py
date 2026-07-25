from __future__ import annotations

import socket
import struct
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings


class VirusScanError(Exception):
    pass


class InfectedFileError(VirusScanError):
    pass


class VirusScannerUnavailableError(VirusScanError):
    pass


class VirusScanner(Protocol):
    def scan(self, path: Path) -> str: ...


class DisabledVirusScanner:
    def scan(self, path: Path) -> str:
        del path
        return "DISABLED"


class ClamAVScanner:
    def __init__(self, settings: Settings):
        self.host = settings.clamav_host
        self.port = settings.clamav_port
        self.timeout = settings.clamav_timeout_seconds

    def scan(self, path: Path) -> str:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as connection:
                connection.sendall(b"zINSTREAM\0")
                with path.open("rb") as source:
                    while chunk := source.read(64 * 1024):
                        connection.sendall(struct.pack("!I", len(chunk)))
                        connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096).decode("utf-8", errors="replace")
        except OSError as exc:
            raise VirusScannerUnavailableError from exc

        if " FOUND" in response:
            signature = response.split(":", 1)[-1].replace("FOUND", "").strip()
            raise InfectedFileError(signature)
        if " OK" not in response:
            raise VirusScannerUnavailableError(response)
        return "CLEAN"


def get_virus_scanner() -> VirusScanner:
    settings = get_settings()
    if settings.virus_scan_enabled:
        return ClamAVScanner(settings)
    return DisabledVirusScanner()
