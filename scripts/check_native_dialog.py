"""Windows smoke check of the actual Tk/native dialogs using only their own HWNDs."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def check(mode, path, cancel=False):
    user = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetDlgItem.restype = wintypes.HWND
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    process = subprocess.Popen([sys.executable, '-B', '-m', 'chronologer_app.native_dialog'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        process.stdin.write(json.dumps(dict(mode=mode, title='ChronoApp dialog smoke check', name=path.name, directory=str(path.parent))))
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 15
        submitted = False
        while process.poll() is None and time.monotonic() < deadline:
            windows = []
            @callback_type
            def visit(hwnd, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                title = ctypes.create_unicode_buffer(256)
                user.GetWindowTextW(hwnd, title, len(title))
                if pid.value == process.pid and title.value == 'ChronoApp dialog smoke check':
                    windows.append(hwnd)
                return True
            user.EnumWindows(visit, 0)
            if windows and not submitted:
                hwnd = windows[0]
                if cancel:
                    user.PostMessageW(hwnd, 0x0111, 2, 0)  # IDCANCEL
                    submitted = True
                else:
                    control = user.GetDlgItem(hwnd, 1148) or user.GetDlgItem(hwnd, 1152)
                    if control:
                        value = ctypes.create_unicode_buffer(str(path))
                        user.SendMessageW(control, 0x000C, 0, ctypes.addressof(value))
                        user.PostMessageW(hwnd, 0x0111, 1, 0)  # IDOK
                        submitted = True
            time.sleep(.1)
        assert process.poll() is not None, 'Native dialog did not finish'
        stdout, stderr = process.communicate()
        result = json.loads(stdout)
        assert 'error' not in result, (result, stderr)
        assert result['path'] is None if cancel else Path(result['path']).resolve() == path.resolve(), result
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='chrono-native-dialog-') as directory:
        source = Path(directory) / 'existing.chrono'
        source.write_bytes(b'dialog selection fixture')
        target = Path(directory) / 'new.chrono'
        check('open', source)
        check('save', target)
        assert not target.exists(), 'Save picker created a placeholder file'
        check('save', target, cancel=True)
        print('PASS: actual Windows Open, Save As, and cancellation dialogs; no placeholder file created.')
