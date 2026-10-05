"""Verify a packaged core starts, enforces its local token, and shuts down."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


root = Path(__file__).resolve().parents[1]
name = "sovereign-core.exe" if sys.platform == "win32" else "sovereign-core"
binary = root / "apps" / "desktop" / "resources" / "core" / name
doctor = subprocess.run([str(binary), "doctor"], capture_output=True, text=True, check=True)
assert json.loads(doctor.stdout)["ok"] is True

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

token = "smoke-test-token"
env = {**os.environ, "SOVEREIGN_API_TOKEN": token}
process = subprocess.Popen(
    [str(binary), "serve", "--host", "127.0.0.1", "--port", str(port)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    env=env,
)
try:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + 30
    while True:
        if process.poll() is not None:
            raise RuntimeError("packaged core exited before becoming ready")
        try:
            urllib.request.urlopen(url, timeout=1)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                break
            raise
        except (urllib.error.URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise RuntimeError("packaged core failed to start")
            time.sleep(0.25)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=3) as response:
        assert json.load(response)["ok"] is True
    print("Packaged core smoke test passed")
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
