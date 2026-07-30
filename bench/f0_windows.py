"""Windows-only host and process measurements for the Lenovo F0 probe.

The module imports on every supported Python host so the offline suite can
exercise pure helpers. Windows APIs are resolved lazily and no command accepts
user-controlled PowerShell.
"""

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import threading
import time


ARM64_PE_MACHINE = 0xAA64
AMD64_PE_MACHINE = 0x8664
X86_PE_MACHINE = 0x014C
_PE_NAMES = {
    ARM64_PE_MACHINE: "arm64",
    AMD64_PE_MACHINE: "amd64",
    X86_PE_MACHINE: "x86",
}


class WindowsProbeError(RuntimeError):
    """A required Windows measurement could not be made safely."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_machine(path):
    """Return the numeric and named COFF machine type of a PE executable."""
    path = Path(path)
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise WindowsProbeError(f"{path} is not a PE executable")
        handle.seek(0x3C)
        raw_offset = handle.read(4)
        if len(raw_offset) != 4:
            raise WindowsProbeError(f"{path} has a truncated DOS header")
        offset = struct.unpack("<I", raw_offset)[0]
        handle.seek(offset)
        if handle.read(4) != b"PE\0\0":
            raise WindowsProbeError(f"{path} has no PE signature")
        raw_machine = handle.read(2)
        if len(raw_machine) != 2:
            raise WindowsProbeError(f"{path} has a truncated COFF header")
    value = struct.unpack("<H", raw_machine)[0]
    return {"value": value, "name": _PE_NAMES.get(value, "unknown")}


def _powershell_json(script):
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise WindowsProbeError(
            "Windows metadata query failed: " + completed.stderr[-500:]
        )
    try:
        return json.loads(completed.stdout)
    except ValueError as exc:
        raise WindowsProbeError(
            "Windows metadata query returned invalid JSON"
        ) from exc


def listener_process():
    """Return PID and executable for the process listening on Ollama's port."""
    value = _powershell_json(
        "$c=Get-NetTCPConnection -State Listen -LocalPort 11434 "
        "-ErrorAction Stop | Select-Object -First 1;"
        "if($null -eq $c){throw 'no listener on port 11434'};"
        "$p=Get-CimInstance Win32_Process -Filter "
        "(\"ProcessId=\"+$c.OwningProcess) -ErrorAction Stop;"
        "[pscustomobject]@{pid=[int]$p.ProcessId;"
        "path=[string]$p.ExecutablePath}|ConvertTo-Json -Compress"
    )
    if not isinstance(value, dict) or not value.get("path"):
        raise WindowsProbeError("Ollama listener executable was not resolved")
    return {"pid": int(value["pid"]), "path": str(value["path"])}


def ollama_ps(executable):
    """Capture Ollama's human-readable processor placement report verbatim."""
    completed = subprocess.run(
        [str(executable), "ps"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise WindowsProbeError(
            "ollama ps failed: " + completed.stderr[-500:]
        )
    return completed.stdout


def _physical_memory_bytes():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    value = MEMORYSTATUSEX()
    value.dwLength = ctypes.sizeof(value)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    memory_status = kernel32.GlobalMemoryStatusEx
    memory_status.argtypes = (ctypes.POINTER(MEMORYSTATUSEX),)
    memory_status.restype = wintypes.BOOL
    if not memory_status(ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(value.ullTotalPhys)


def _filesystem_name(path):
    root = str(Path(path).resolve().anchor)
    if not root:
        raise WindowsProbeError("output path has no Windows volume")
    filesystem = ctypes.create_unicode_buffer(64)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_information = kernel32.GetVolumeInformationW
    dword_pointer = ctypes.POINTER(wintypes.DWORD)
    volume_information.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        dword_pointer,
        dword_pointer,
        dword_pointer,
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    volume_information.restype = wintypes.BOOL
    if not volume_information(
        root, None, 0, None, None, None, filesystem, len(filesystem)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return root, filesystem.value


def _drive_type(volume_root):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = (wintypes.LPCWSTR,)
    get_drive_type.restype = wintypes.UINT
    return int(get_drive_type(volume_root))


def _inside_onedrive(path):
    candidate = os.path.normcase(os.path.realpath(str(path)))
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(key)
        if not root:
            continue
        root = os.path.normcase(os.path.realpath(root))
        try:
            if os.path.commonpath((candidate, root)) == root:
                return True
        except ValueError:
            continue
    return False


def collect_environment(
    output_root,
    minimum_physical_memory_bytes,
    minimum_free_disk_bytes,
):
    """Collect and evaluate the canonical Lenovo host prerequisites."""
    if os.name != "nt":
        return {
            "schema_version": "brick.f0.environment/1",
            "passed": False,
            "failures": ["native Windows is required"],
            "system": platform.system(),
            "machine": platform.machine(),
        }

    output_root = Path(output_root).resolve()
    listener = listener_process()
    python_machine = pe_machine(sys.executable)
    ollama_machine = pe_machine(listener["path"])
    total_memory = _physical_memory_bytes()
    volume_root, filesystem = _filesystem_name(output_root)
    drive_type = _drive_type(volume_root)
    disk = shutil.disk_usage(str(output_root))
    build = int(sys.getwindowsversion().build)
    machine = platform.machine().casefold()
    metadata = _powershell_json(
        "$bios=Get-CimInstance Win32_BIOS;"
        "$system=Get-CimInstance Win32_ComputerSystem;"
        "$product=Get-CimInstance Win32_ComputerSystemProduct;"
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "$gpu=@(Get-CimInstance Win32_VideoController | "
        "Select-Object Name,DriverVersion);"
        "$disks=@(Get-CimInstance Win32_DiskDrive | Select-Object "
        "Model,SerialNumber,FirmwareRevision,Size,InterfaceType);"
        "$qualcomm=@(Get-CimInstance Win32_PnPSignedDriver | "
        "Where-Object {$_.Manufacturer -match 'Qualcomm' -or "
        "$_.DeviceName -match 'Qualcomm'} | Select-Object "
        "DeviceName,Manufacturer,DriverVersion,DriverDate,InfName);"
        "$defender=Get-MpComputerStatus -ErrorAction SilentlyContinue;"
        "$search=Get-Service WSearch -ErrorAction SilentlyContinue;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$powerline=[System.Windows.Forms.SystemInformation]::"
        "PowerStatus.PowerLineStatus.ToString();"
        "$power=(powercfg /getactivescheme | Out-String).Trim();"
        "$powerkey=Get-ItemProperty "
        "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes' "
        "-Name ActiveOverlayAcPowerScheme -ErrorAction SilentlyContinue;"
        "$overlay=[string]$powerkey.ActiveOverlayAcPowerScheme;"
        "[pscustomobject]@{computer=[pscustomobject]@{"
        "manufacturer=$system.Manufacturer;model=$system.Model;"
        "product_name=$product.Name;product_version=$product.Version};"
        "os=[pscustomobject]@{caption=$os.Caption;version=$os.Version;"
        "build=$os.BuildNumber};bios=[pscustomobject]@{"
        "manufacturer=$bios.Manufacturer;version=$bios.SMBIOSBIOSVersion;"
        "release_date=$bios.ReleaseDate};cpu=[string]$cpu.Name;gpu=$gpu;"
        "qualcomm_drivers=$qualcomm;storage_devices=$disks;"
        "power_scheme=$power;power_overlay_ac=$overlay;"
        "power_line=$powerline;"
        "defender=[pscustomobject]@{antivirus_enabled="
        "$defender.AntivirusEnabled;realtime_enabled="
        "$defender.RealTimeProtectionEnabled};"
        "windows_search_status=[string]$search.Status}"
        "|ConvertTo-Json -Compress -Depth 5"
    )
    failures = []
    if build < 22000:
        failures.append("Windows 11 build 22000 or newer is required")
    if machine not in {"arm64", "aarch64"}:
        failures.append("platform.machine() is not ARM64")
    if python_machine["value"] != ARM64_PE_MACHINE:
        failures.append("Python executable is not native ARM64")
    if ollama_machine["value"] != ARM64_PE_MACHINE:
        failures.append("Ollama listener is not native ARM64")
    if total_memory < minimum_physical_memory_bytes:
        failures.append("physical memory is below the protocol minimum")
    if filesystem.casefold() != "ntfs":
        failures.append("F0 output volume is not NTFS")
    if drive_type != 3:  # DRIVE_FIXED
        failures.append("F0 output volume is not a fixed local drive")
    if disk.free < minimum_free_disk_bytes:
        failures.append("free disk is below the protocol minimum")
    if _inside_onedrive(output_root):
        failures.append("F0 output root is inside OneDrive")
    if not isinstance(metadata, dict):
        failures.append("Windows hardware metadata is malformed")
    else:
        computer = metadata.get("computer")
        if not isinstance(computer, dict) or not computer.get("model"):
            failures.append("Lenovo model metadata is missing")
        elif "lenovo" not in str(
            computer.get("manufacturer", "")
        ).casefold():
            failures.append("computer manufacturer is not Lenovo")
        cpu = str(metadata.get("cpu", "")).casefold()
        if "snapdragon" not in cpu or "x elite" not in cpu:
            failures.append("CPU is not identified as Snapdragon X Elite")
        storage_devices = metadata.get("storage_devices")
        if not isinstance(storage_devices, (dict, list)) or not storage_devices:
            failures.append("storage-device metadata is missing")
        qualcomm = metadata.get("qualcomm_drivers")
        if not isinstance(qualcomm, (dict, list)) or not qualcomm:
            failures.append("Qualcomm driver metadata is missing")
        if not metadata.get("power_scheme"):
            failures.append("active power-plan metadata is missing")
        power = str(metadata.get("power_scheme", "")).casefold()
        overlay = str(
            metadata.get("power_overlay_ac", "")
        ).casefold().strip("{}")
        if not (
            "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" in power
            or "e9a42b02-d5df-448d-aa00-03f14749eb61" in power
            or overlay == "ded574b5-45a0-4f42-8737-46345c09c238"
        ):
            failures.append("Windows power mode is not Best Performance")
        if str(metadata.get("power_line", "")).casefold() != "online":
            failures.append("Lenovo is not connected to AC power")
        defender = metadata.get("defender")
        if (
            not isinstance(defender, dict)
            or defender.get("antivirus_enabled") is not True
            or defender.get("realtime_enabled") is not True
        ):
            failures.append("Microsoft Defender real-time protection is off")
        if str(
            metadata.get("windows_search_status", "")
        ).casefold() != "running":
            failures.append("Windows Search indexing service is not running")

    return {
        "schema_version": "brick.f0.environment/1",
        "passed": not failures,
        "failures": failures,
        "system": platform.system(),
        "windows_build": build,
        "machine": platform.machine(),
        "physical_memory_bytes": total_memory,
        "volume": {
            "root": volume_root,
            "filesystem": filesystem,
            "drive_type": drive_type,
            "free_bytes": disk.free,
        },
        "python": {
            "version": platform.python_version(),
            "path": str(Path(sys.executable).resolve()),
            "sha256": sha256_file(sys.executable),
            "pe_machine": python_machine,
        },
        "ollama_listener": {
            "pid": listener["pid"],
            "path": listener["path"],
            "sha256": sha256_file(listener["path"]),
            "pe_machine": ollama_machine,
        },
        "onedrive_contained": _inside_onedrive(output_root),
        "hardware": metadata,
    }


def _process_entries():
    """Return parent and executable-name metadata using Toolhelp32."""
    if os.name != "nt":
        raise WindowsProbeError("process sampling requires Windows")

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    create_snapshot.restype = wintypes.HANDLE
    process_first = kernel32.Process32FirstW
    process_first.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    )
    process_first.restype = wintypes.BOOL
    process_next = kernel32.Process32NextW
    process_next.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    )
    process_next.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    snapshot = create_snapshot(0x00000002, 0)
    invalid = ctypes.c_void_p(-1).value
    if snapshot == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    values = {}
    try:
        ok = process_first(snapshot, ctypes.byref(entry))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        while ok:
            values[int(entry.th32ProcessID)] = {
                "parent_pid": int(entry.th32ParentProcessID),
                "image": str(entry.szExeFile),
            }
            ok = process_next(snapshot, ctypes.byref(entry))
    finally:
        close_handle(snapshot)
    return values


def _process_memory(pid):
    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
        wintypes.DWORD,
    )
    get_memory.restype = wintypes.BOOL
    handle = open_process(0x1000 | 0x0010, False, pid)
    if not handle:
        return None
    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(counters)
    try:
        if not get_memory(
            handle, ctypes.byref(counters), counters.cb
        ):
            return None
        return {
            "private_commit_bytes": int(counters.PrivateUsage),
            "working_set_bytes": int(counters.WorkingSetSize),
        }
    finally:
        close_handle(handle)


def sample_process_tree(root_pid):
    processes = _process_entries()
    root_pid = int(root_pid)
    if root_pid not in processes:
        raise WindowsProbeError("Ollama listener PID is not present")
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, process in processes.items():
            if (
                process["parent_pid"] in selected
                and pid not in selected
            ):
                selected.add(pid)
                changed = True
    private = 0
    working = 0
    measured = []
    unmeasured = []
    process_records = []
    for pid in sorted(selected):
        usage = _process_memory(pid)
        if usage is None:
            unmeasured.append(pid)
            continue
        measured.append(pid)
        private += usage["private_commit_bytes"]
        working += usage["working_set_bytes"]
        process = processes.get(pid, {})
        process_records.append(
            {
                "pid": pid,
                "parent_pid": process.get("parent_pid"),
                "image": process.get("image"),
                **usage,
            }
        )
    if root_pid in unmeasured:
        raise WindowsProbeError("Ollama listener memory was not measurable")
    if unmeasured:
        latest = _process_entries()
        live_unmeasured = [
            pid for pid in unmeasured if pid in latest
        ]
        if live_unmeasured:
            raise WindowsProbeError(
                "live Ollama descendants were not measurable: "
                + ", ".join(str(pid) for pid in live_unmeasured)
            )
    if not measured:
        raise WindowsProbeError("Ollama process tree could not be measured")
    return {
        "monotonic_seconds": time.monotonic(),
        "selected_pids": sorted(selected),
        "pids": measured,
        "processes": process_records,
        "exited_before_measurement_pids": unmeasured,
        "private_commit_bytes": private,
        "working_set_bytes": working,
    }


class ProcessTreeMonitor:
    """Sample one process tree until stopped."""

    def __init__(self, root_pid, interval_seconds=0.25):
        self.root_pid = int(root_pid)
        self.interval_seconds = float(interval_seconds)
        self.samples = []
        self.error = None
        self._stop = threading.Event()
        self._thread = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self.samples.append(sample_process_tree(self.root_pid))
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                return
            self._stop.wait(self.interval_seconds)

    def start(self):
        if self._thread is not None:
            raise RuntimeError("monitor already started")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive() and self.error is None:
                self.error = "process-memory monitor did not stop"
        return self.summary()

    def summary(self):
        return {
            "schema_version": "brick.f0.process-memory/1",
            "error": self.error,
            "samples": list(self.samples),
            "peak_private_commit_bytes": max(
                (
                    sample["private_commit_bytes"]
                    for sample in self.samples
                ),
                default=None,
            ),
            "peak_working_set_bytes": max(
                (
                    sample["working_set_bytes"]
                    for sample in self.samples
                ),
                default=None,
            ),
            "peak_process_count": max(
                (len(sample["pids"]) for sample in self.samples),
                default=0,
            ),
        }
