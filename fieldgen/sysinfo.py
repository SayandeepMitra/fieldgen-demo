"""Machine facts that differ between Linux, macOS and Windows: installed memory and the process start method."""
import multiprocessing as mp, os, sys


def total_ram_bytes():
    """Installed memory in bytes. Linux: /proc/meminfo (as before); macOS and other Unix: os.sysconf; Windows: GlobalMemoryStatusEx; else 8 GiB."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal"): return int(line.split()[1]) * 1024
    except OSError: pass
    try: return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError): pass
    if sys.platform == "win32":
        try:
            import ctypes
            class MemStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("tpage", ctypes.c_ulonglong), ("apage", ctypes.c_ulonglong), ("tvirt", ctypes.c_ulonglong), ("avirt", ctypes.c_ulonglong), ("ext", ctypes.c_ulonglong)]
            st = MemStatus(); st.length = ctypes.sizeof(MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)): return int(st.total)
        except Exception: pass
    return 8 * 2 ** 30


def process_context():
    """Linux: fork, as before. macOS and Windows: spawn. FIELDGEN_START_METHOD=spawn forces spawn on any system (used to test it on Linux)."""
    want = os.environ.get("FIELDGEN_START_METHOD") or ("fork" if sys.platform.startswith("linux") else "spawn")
    return mp.get_context(want)
