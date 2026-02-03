"""
Memory leak test for PyFTPDrive.

This test monitors memory usage while performing repeated filesystem operations.
Run while mount is active on Z:
"""

import os
import sys
import time

import psutil


def get_pyftpdrive_process():
    """Find the pyftpdrive process."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("pyftpdrive" in str(arg) for arg in cmdline):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def format_bytes(b):
    """Format bytes as human-readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def stress_test_directory_listing(drive_path, iterations):
    """Repeatedly list directories."""
    for _i in range(iterations):
        try:
            for _root, _dirs, _files in os.walk(drive_path):
                pass  # Just traverse
                break  # Shallow walk - only first level
        except Exception as e:
            print(f"[WARN] Walk error: {e}")


def stress_test_file_stats(drive_path, iterations):
    """Repeatedly stat files."""
    try:
        entries = os.listdir(drive_path)
    except Exception as e:
        print(f"[WARN] Cannot list {drive_path}: {e}")
        return

    for _i in range(iterations):
        for entry in entries[:10]:  # First 10 entries
            try:
                path = os.path.join(drive_path, entry)
                os.stat(path)
            except Exception:
                pass


def main():
    drive = sys.argv[1] if len(sys.argv) > 1 else "Z:"
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    print("Memory Leak Test for PyFTPDrive")
    print(f"Drive: {drive}")
    print(f"Iterations per test: {iterations}")
    print("-" * 50)

    # Find process
    proc = get_pyftpdrive_process()
    if not proc:
        print("[ERROR] Cannot find pyftpdrive process")
        print("        Make sure mount is running")
        return 1

    print(f"Found process: PID {proc.pid}")

    # Get initial memory
    try:
        mem_info = proc.memory_info()
        initial_rss = mem_info.rss
        initial_vms = mem_info.vms
    except Exception as e:
        print(f"[ERROR] Cannot read memory: {e}")
        return 1

    print(f"Initial RSS: {format_bytes(initial_rss)}")
    print(f"Initial VMS: {format_bytes(initial_vms)}")
    print("-" * 50)

    # Run stress tests
    tests = [
        ("Directory listing", lambda: stress_test_directory_listing(drive, iterations)),
        ("File stats", lambda: stress_test_file_stats(drive, iterations)),
    ]

    for test_name, test_func in tests:
        print(f"\nRunning: {test_name} ({iterations} iterations)...")

        try:
            mem_before = proc.memory_info().rss
        except Exception:
            print("[WARN] Process may have died")
            return 1

        start = time.time()
        test_func()
        elapsed = time.time() - start

        try:
            mem_after = proc.memory_info().rss
        except Exception:
            print("[WARN] Process may have died")
            return 1

        delta = mem_after - mem_before
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Memory before: {format_bytes(mem_before)}")
        print(f"  Memory after:  {format_bytes(mem_after)}")
        print(f"  Delta: {format_bytes(abs(delta))} {'(+)' if delta > 0 else '(-)'}")

    # Final summary
    print("\n" + "=" * 50)
    print("FINAL SUMMARY")
    print("=" * 50)

    try:
        final_mem = proc.memory_info()
        final_rss = final_mem.rss
        final_vms = final_mem.vms
    except Exception:
        print("[ERROR] Process died during test")
        return 1

    total_rss_delta = final_rss - initial_rss
    total_vms_delta = final_vms - initial_vms

    print(f"Final RSS: {format_bytes(final_rss)}")
    print(f"Final VMS: {format_bytes(final_vms)}")
    print(
        f"Total RSS change: {format_bytes(abs(total_rss_delta))} {'(+)' if total_rss_delta > 0 else '(-)'}"
    )
    print(
        f"Total VMS change: {format_bytes(abs(total_vms_delta))} {'(+)' if total_vms_delta > 0 else '(-)'}"
    )

    # Verdict
    # Allow up to 10MB growth as acceptable (GC hasn't run, caches, etc.)
    threshold_mb = 10
    threshold_bytes = threshold_mb * 1024 * 1024

    if total_rss_delta > threshold_bytes:
        print(f"\n[WARN] Memory grew by more than {threshold_mb}MB")
        print("       This MAY indicate a leak, but could also be caching")
        print("       Run for longer to confirm")
        return 1
    else:
        print(f"\n[OK] Memory growth within acceptable range (<{threshold_mb}MB)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
