"""Minimal WinUSB access to the DJI receiver's vendor interface (MI_06).

Windows has no inbox driver for interface 6. After driver/install_winusb.ps1
binds Microsoft's winusb.sys to it, user mode can open the interface through
SetupAPI and exchange Bulk transfers on OUT 0x06 / IN 0x86.

The ctypes plumbing is adapted from hogancv/dji-mic-mini-monitor (MIT), with
write support and a class-based lifecycle added. See docs/CREDITS.md.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import threading

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
winusb = ctypes.WinDLL("winusb", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

GUID_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
GUID_USB_DEVICE_BYTES = (0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED)

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
ERROR_NO_MORE_ITEMS = 259
ERROR_SEM_TIMEOUT = 121
FILE_FLAG_OVERLAPPED = 0x40000000
OPEN_EXISTING = 3
GENERIC_READ_WRITE = 0xC0000000
FILE_SHARE_READ_WRITE = 0x03
PIPE_TRANSFER_TIMEOUT = 0x03
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258

PIPE_IN = 0x86
PIPE_OUT = 0x06


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.DWORD),
        ("Data2", w.WORD),
        ("Data3", w.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", w.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", w.DWORD),
        ("OffsetHigh", w.DWORD),
        ("hEvent", ctypes.c_void_p),
    ]


def _make_guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(
        int(parts[0], 16),
        int(parts[1], 16),
        int(parts[2], 16),
        (ctypes.c_ubyte * 8)(*data4),
    )


GUID_INTERFACE = _make_guid(GUID_USB_DEVICE)

setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    w.LPCWSTR,
    w.HWND,
    w.DWORD,
]
setupapi.SetupDiEnumDeviceInterfaces.restype = w.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    w.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = w.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    w.DWORD,
    ctypes.POINTER(w.DWORD),
    ctypes.c_void_p,
]
setupapi.SetupDiDestroyDeviceInfoList.restype = w.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

k32.CreateFileW.restype = ctypes.c_void_p
k32.CreateFileW.argtypes = [
    w.LPCWSTR,
    w.DWORD,
    w.DWORD,
    ctypes.c_void_p,
    w.DWORD,
    w.DWORD,
    ctypes.c_void_p,
]
k32.CloseHandle.restype = w.BOOL
k32.CloseHandle.argtypes = [ctypes.c_void_p]
k32.CreateEventW.restype = ctypes.c_void_p
k32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
k32.WaitForSingleObject.restype = w.DWORD
k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, w.DWORD]
k32.CancelIoEx.restype = w.BOOL
k32.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(OVERLAPPED)]

winusb.WinUsb_Initialize.restype = w.BOOL
winusb.WinUsb_Initialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
winusb.WinUsb_Free.restype = w.BOOL
winusb.WinUsb_Free.argtypes = [ctypes.c_void_p]
winusb.WinUsb_SetPipePolicy.restype = w.BOOL
winusb.WinUsb_SetPipePolicy.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ubyte,
    w.ULONG,
    w.ULONG,
    ctypes.c_void_p,
]
winusb.WinUsb_ReadPipe.restype = w.BOOL
winusb.WinUsb_ReadPipe.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ubyte,
    ctypes.c_void_p,
    w.ULONG,
    ctypes.POINTER(w.ULONG),
    ctypes.POINTER(OVERLAPPED),
]
winusb.WinUsb_WritePipe.restype = w.BOOL
winusb.WinUsb_WritePipe.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ubyte,
    ctypes.c_void_p,
    w.ULONG,
    ctypes.POINTER(w.ULONG),
    ctypes.POINTER(OVERLAPPED),
]
winusb.WinUsb_GetOverlappedResult.restype = w.BOOL
winusb.WinUsb_GetOverlappedResult.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(OVERLAPPED),
    ctypes.POINTER(w.ULONG),
    w.BOOL,
]

_INVALID_HANDLE = ctypes.c_void_p(-1).value


def enum_device_paths() -> list[str]:
    """All USB device interface paths currently present."""
    paths: list[str] = []
    handle = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(GUID_INTERFACE),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if not handle:
        return paths
    try:
        index = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA()
            data.cbSize = ctypes.sizeof(data)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                handle, None, ctypes.byref(GUID_INTERFACE), index, ctypes.byref(data)
            ):
                break
            index += 1
            needed = w.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                handle,
                ctypes.byref(data),
                None,
                0,
                ctypes.byref(needed),
                None,
            )
            if not needed.value:
                continue
            buf = ctypes.create_string_buffer(needed.value)
            detail_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = detail_size
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                handle,
                ctypes.byref(data),
                buf,
                needed.value,
                ctypes.byref(needed),
                None,
            ):
                paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(handle)
    return paths


def _is_receiver(path: str) -> bool:
    low = path.lower()
    return "vid_2ca3" in low and "pid_4011" in low


def find_interface_path() -> str | None:
    """Device path of MI_06, or None when the interface is absent/unbound."""
    for path in enum_device_paths():
        low = path.lower()
        if _is_receiver(path) and "mi_06" in low:
            return path
    return None


def receiver_present() -> bool:
    return any(_is_receiver(path) for path in enum_device_paths())


def driver_state() -> str:
    """'ready', 'driver-missing', or 'absent'."""
    paths = enum_device_paths()
    if any(_is_receiver(p) and "mi_06" in p.lower() for p in paths):
        return "ready"
    if any(_is_receiver(p) for p in paths):
        return "driver-missing"
    return "absent"


class WinUsbDevice:
    """An open MI_06 interface. Reads and writes may run on different threads."""

    def __init__(self, path: str, read_timeout_ms: int = 200):
        self.path = path
        self.read_timeout_ms = read_timeout_ms
        self.handle: int | None = None
        self.interface: ctypes.c_void_p | None = None
        self._closed = threading.Event()
        self._close_guard = threading.Lock()
        self._io_guard = threading.Lock()
        self._active_io = 0
        self._io_idle = threading.Event()
        self._io_idle.set()

    def _enter_io(self) -> bool:
        with self._io_guard:
            if self._closed.is_set() or self.interface is None:
                return False
            self._active_io += 1
            self._io_idle.clear()
            return True

    def _leave_io(self) -> None:
        with self._io_guard:
            self._active_io -= 1
            if self._active_io == 0:
                self._io_idle.set()

    def open(self) -> None:
        handle = k32.CreateFileW(
            self.path,
            GENERIC_READ_WRITE,
            FILE_SHARE_READ_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        if not handle or handle == _INVALID_HANDLE:
            raise OSError(ctypes.get_last_error(), "CreateFile(MI_06) failed")
        interface = ctypes.c_void_p()
        if not winusb.WinUsb_Initialize(handle, ctypes.byref(interface)):
            error = ctypes.get_last_error()
            k32.CloseHandle(handle)
            raise OSError(error, "WinUsb_Initialize failed")
        self.handle = handle
        self.interface = interface
        timeout_in = w.ULONG(self.read_timeout_ms)
        winusb.WinUsb_SetPipePolicy(
            interface,
            PIPE_IN,
            PIPE_TRANSFER_TIMEOUT,
            ctypes.sizeof(timeout_in),
            ctypes.byref(timeout_in),
        )
        timeout_out = w.ULONG(1500)
        winusb.WinUsb_SetPipePolicy(
            interface,
            PIPE_OUT,
            PIPE_TRANSFER_TIMEOUT,
            ctypes.sizeof(timeout_out),
            ctypes.byref(timeout_out),
        )

    @property
    def is_open(self) -> bool:
        return self.handle is not None and not self._closed.is_set()

    def read(self, size: int = 1024, timeout_ms: int | None = None) -> bytes | None:
        """Read one bulk-IN transfer. b'' on timeout, None on a real error."""
        if not self._enter_io():
            return None
        timeout = self.read_timeout_ms if timeout_ms is None else timeout_ms
        event = k32.CreateEventW(None, True, False, None)
        if not event:
            self._leave_io()
            return None
        overlapped = OVERLAPPED()
        overlapped.hEvent = event
        buf = ctypes.create_string_buffer(size)
        got = w.ULONG(0)
        try:
            ok = winusb.WinUsb_ReadPipe(
                self.interface,
                PIPE_IN,
                buf,
                size,
                ctypes.byref(got),
                ctypes.byref(overlapped),
            )
            if ok:
                return bytes(buf.raw[: got.value])
            error = ctypes.get_last_error()
            if error != ERROR_IO_PENDING:
                return b"" if error == ERROR_SEM_TIMEOUT else None
            if k32.WaitForSingleObject(event, timeout) != WAIT_OBJECT_0:
                k32.CancelIoEx(self.handle, ctypes.byref(overlapped))
                k32.WaitForSingleObject(event, 1000)
                winusb.WinUsb_GetOverlappedResult(
                    self.interface, ctypes.byref(overlapped), ctypes.byref(got), False
                )
                return b""
            if not winusb.WinUsb_GetOverlappedResult(
                self.interface, ctypes.byref(overlapped), ctypes.byref(got), False
            ):
                return None
            return bytes(buf.raw[: got.value])
        finally:
            k32.CloseHandle(event)
            self._leave_io()

    def write(self, data: bytes, timeout_ms: int = 1500) -> int:
        if len(data) > 1024:
            raise ValueError("transfer too large")
        if not self._enter_io():
            raise OSError("interface is not open")
        event = k32.CreateEventW(None, True, False, None)
        if not event:
            self._leave_io()
            raise OSError(ctypes.get_last_error(), "CreateEvent failed")
        overlapped = OVERLAPPED()
        overlapped.hEvent = event
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        sent = w.ULONG(0)
        try:
            ok = winusb.WinUsb_WritePipe(
                self.interface,
                PIPE_OUT,
                buf,
                len(data),
                ctypes.byref(sent),
                ctypes.byref(overlapped),
            )
            if not ok:
                error = ctypes.get_last_error()
                if error != ERROR_IO_PENDING:
                    if error == ERROR_SEM_TIMEOUT:
                        raise TimeoutError("WinUsb_WritePipe timed out")
                    raise OSError(error, "WinUsb_WritePipe failed")
                if k32.WaitForSingleObject(event, timeout_ms) != WAIT_OBJECT_0:
                    k32.CancelIoEx(self.handle, ctypes.byref(overlapped))
                    k32.WaitForSingleObject(event, 1000)
                    winusb.WinUsb_GetOverlappedResult(
                        self.interface, ctypes.byref(overlapped), ctypes.byref(sent), False
                    )
                    raise TimeoutError("WinUsb_WritePipe timed out")
                if not winusb.WinUsb_GetOverlappedResult(
                    self.interface, ctypes.byref(overlapped), ctypes.byref(sent), False
                ):
                    raise OSError(ctypes.get_last_error(), "WinUsb write failed")
            return int(sent.value)
        finally:
            k32.CloseHandle(event)
            self._leave_io()

    def close(self) -> None:
        with self._close_guard:
            if self._closed.is_set():
                return
            self._closed.set()
            if self.handle:
                try:
                    k32.CancelIoEx(self.handle, None)
                except Exception:
                    pass
            # Let an in-flight read/write leave user mode before freeing the
            # interface; otherwise WinUsb_GetOverlappedResult touches freed memory.
            self._io_idle.wait(2.0)
            if self.interface:
                try:
                    winusb.WinUsb_Free(self.interface)
                except Exception:
                    pass
                self.interface = None
            if self.handle:
                try:
                    k32.CloseHandle(self.handle)
                except Exception:
                    pass
                self.handle = None
