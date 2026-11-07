import ctypes
import subprocess
import sys
import json
from ctypes import wintypes
from typing import Any


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


def kernel32() -> Any:
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    dll.CreateJobObjectW.restype = wintypes.HANDLE
    dll.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    dll.AssignProcessToJobObject.restype = wintypes.BOOL
    dll.SetHandleInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    dll.SetHandleInformation.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    dll.GetCurrentProcess.restype = wintypes.HANDLE
    dll.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dll.SetInformationJobObject.restype = wintypes.BOOL
    dll.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    dll.TerminateJobObject.restype = wintypes.BOOL
    return dll


def checked(result: Any) -> Any:
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def bootstrap(handle: str, command: list[str]) -> int:
    dll = kernel32()
    handle = wintypes.HANDLE(int(handle))
    checked(dll.AssignProcessToJobObject(handle, dll.GetCurrentProcess()))
    checked(dll.CloseHandle(handle))
    print(json.dumps({"type": "supervisor_bootstrap_ready"}), flush=True)
    return subprocess.call(command)



def create_job() -> Any:
    dll = kernel32()
    job = checked(dll.CreateJobObjectW(None, None))
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000
    try:
        checked(dll.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
    except BaseException:
        dll.CloseHandle(job)
        raise
    return job


if __name__ == "__main__":
    raise SystemExit(bootstrap(sys.argv[1], sys.argv[2:]))
