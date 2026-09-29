#!/usr/bin/env python3
"""Small read-only runner probe; no package installs, builds or private data."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

def command(argv, timeout=12):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": p.returncode, "output": (p.stdout + p.stderr)[:1500]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}

def main():
    out = Path("evidence")
    out.mkdir(exist_ok=True)
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            key, value, _ = line.split()
            mem[key.rstrip(":")] = int(value) * 1024
    disk = shutil.disk_usage(Path.cwd())
    cpu = next((x.split(":", 1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
                if x.startswith("model name")), "unknown")
    report = {"schema": "remeizu.runner-probe.v1",
              "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "requested_runner": "blacksmith-2vcpu-ubuntu-2404",
              "run_id": os.environ.get("GITHUB_RUN_ID"),
              "source_commit": os.environ.get("GITHUB_SHA"),
              "architecture": platform.machine(), "cpu_model": cpu,
              "logical_cpus": os.cpu_count(), "affinity_cpus": len(os.sched_getaffinity(0)),
              "memory_bytes": mem, "disk_bytes": dict(zip(("total", "used", "free"), disk)),
              "tools": {}, "network": {}, "kernel_built": False, "runtime_verified": False}
    for key, argv in {"git": ["git", "--version"], "gcc": ["gcc", "--version"],
                      "python": ["python3", "--version"],
                      "docker": ["docker", "version", "--format", "{{.Server.Version}}"]}.items():
        report["tools"][key] = command(argv)
    for host, url in {"github": "https://api.github.com/repos/ReMeizu/build-infra",
                      "raw_github": "https://raw.githubusercontent.com/ReMeizu/build-infra/main/README.md",
                      "android_sources_http": "https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/"}.items():
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ReMeizu-runner-probe"})
            with urllib.request.urlopen(req, timeout=15) as response:
                report["network"][host] = {"http_status": response.status}
        except Exception as exc:
            report["network"][host] = {"error": type(exc).__name__, "http_status": getattr(exc, "code", None)}
    # The kernel fetch uses Git. Preserve the HTTP observation separately:
    # a failed repository HTML/HEAD route does not establish Git failure.
    git_probe = command(["git", "-c", "credential.helper=", "ls-remote",
                         "https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9",
                         "refs/tags/android-8.1.0_r67"], timeout=45)
    report["network"]["android_sources_git"] = git_probe
    git_ok = (git_probe.get("exit_code") == 0 and
              "06fdac66046e3b7950bfb3676c6aa8b5af475047\trefs/tags/android-8.1.0_r67" in git_probe.get("output", "").splitlines())
    report["probe_pass"] = (report["architecture"] == "x86_64" and report["affinity_cpus"] >= 2
                            and mem.get("MemTotal", 0) >= 6 * 1024**3 and disk.free >= 20 * 1024**3
                            and report["tools"]["docker"].get("exit_code") == 0
                            and all(report["network"][x].get("http_status") == 200 for x in ("github", "raw_github"))
                            and git_ok)
    (out / "runner-probe.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write("Probe: " + ("PASS" if report["probe_pass"] else "FAIL") + "\n\n")
            stream.write("Read-only environment check. No kernel or ROM was compiled.\n")
    return 0 if report["probe_pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
