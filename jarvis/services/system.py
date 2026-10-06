"""Host system telemetry (CPU, memory, battery, disk).

Only the host process can report these values, so the web front door labels them
as server statistics. ``psutil`` is optional: without it we degrade to the
standard library rather than crashing the way the legacy script did.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

try:  # pragma: no cover - platform dependent
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore[assignment]


@dataclass(slots=True)
class SystemStatus:
    platform: str
    python: str
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    battery_percent: float | None = None
    battery_plugged: bool | None = None
    disk_free_gb: float | None = None
    uptime_hours: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "python": self.python,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_gb": _round(self.memory_used_gb),
            "memory_total_gb": _round(self.memory_total_gb),
            "battery_percent": self.battery_percent,
            "battery_plugged": self.battery_plugged,
            "disk_free_gb": _round(self.disk_free_gb),
            "uptime_hours": _round(self.uptime_hours),
        }

    def spoken(self) -> str:
        parts: list[str] = []
        if self.cpu_percent is not None:
            parts.append(f"CPU is at {round(self.cpu_percent)} percent")
        if self.memory_percent is not None:
            parts.append(f"memory is at {round(self.memory_percent)} percent")
        if self.battery_percent is not None:
            state = "charging" if self.battery_plugged else "on battery"
            parts.append(f"battery is at {round(self.battery_percent)} percent and {state}")
        if self.disk_free_gb is not None:
            parts.append(f"{round(self.disk_free_gb)} gigabytes of disk are free")
        if not parts:
            parts.append("I can only read detailed system statistics when psutil is installed")
        return ", ".join(parts) + "."


class SystemService:
    def __init__(self, ctx: object | None = None) -> None:  # context kept for interface parity
        self.ctx = ctx

    def status(self) -> SystemStatus:
        status = SystemStatus(
            platform=f"{platform.system()} {platform.release()}",
            python=platform.python_version(),
            uptime_hours=_uptime_hours(),
        )
        if psutil is not None:
            try:
                status.cpu_percent = float(psutil.cpu_percent(interval=0.2))
                memory = psutil.virtual_memory()
                status.memory_percent = float(memory.percent)
                status.memory_used_gb = float(memory.used) / 1024**3
                status.memory_total_gb = float(memory.total) / 1024**3
                battery = getattr(psutil, "sensors_battery", lambda: None)()
                if battery is not None:
                    status.battery_percent = float(battery.percent)
                    status.battery_plugged = bool(battery.power_plugged)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("psutil telemetry unavailable: %s", exc)
        try:
            usage = shutil.disk_usage(os.path.expanduser("~"))
            status.disk_free_gb = usage.free / 1024**3
        except OSError:  # pragma: no cover - defensive
            pass
        return status


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _uptime_hours() -> float | None:
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            return float(handle.read().split()[0]) / 3600
    except (OSError, ValueError, IndexError):
        return None


def monotonic_ms() -> float:
    return time.monotonic() * 1000
