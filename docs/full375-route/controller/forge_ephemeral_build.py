#!/usr/bin/env python3
"""forge_ephemeral_build.py — ephemeral Docker build container launcher.

FACT: This script is the sole entry point for running an isolated, hash-keyed
build inside a Docker container. It never mutates source trees directly;
instead it mounts them read-only and writes all outputs to a content-addressed
host directory under FORGE_EPHEMERAL_BASE.

FACT: Idempotency is enforced via a SUCCESS marker file. A run against an
already-successful recipe_hash returns immediately with the cached result.

HYPOTHESIS: YAML recipe files will be the preferred invocation path for
automated pipelines; the flat CLI flags are provided for quick manual use and
debugging. Both paths share the same BuildRecipe dataclass so hash determinism
is identical.

FACT: Container output goes directly to run.log; verbose mode also relays that
file to stderr while polling the owned Docker client.

Hard rules enforced here:
- No rm -rf of anything without --purge + explicit confirmation.
- No silent overwrites: if output dir exists without SUCCESS, we either resume
  (re-run docker) or refuse (--no-resume).
- Cancellation reaps the owned client before bounded ownership-checked cleanup.
- subprocess only — no docker SDK dependency, keeps the script self-contained
  with stdlib + optional PyYAML.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import re
import signal
import secrets
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("forge_ephemeral_build")

# ---------------------------------------------------------------------------
# Environment / defaults
# ---------------------------------------------------------------------------

def _default_ephemeral_base() -> str:
    if os.environ.get("FORGE_CLOUD_STORAGE_ENABLED", "").lower() in {"1", "true", "yes", "on"}:
        hot = os.environ.get("FORGE_LOCAL_HOT_CACHE_ROOT", "/srv/forge/cache/hot")
        return str(Path(hot) / "ephemeral-builds")
    return "/srv/forge/ephemeral-builds"


FORGE_EPHEMERAL_BASE = Path(os.environ.get("FORGE_EPHEMERAL_BASE", _default_ephemeral_base()))
DEFAULT_TIMEOUT_SECONDS = 4 * 3600  # 4 hours

SUCCESS_MARKER = "SUCCESS"
FAILURE_MARKER = "FAILURE"
ARTIFACTS_JSON = "artifacts.json"
BUILD_ENV_CONTRACT_JSON = "build-env-contract.json"
RUN_LOG = "run.log"
CONTAINER_METADATA_DIR = ".forge-container"
OWNER_LABEL = "androidforge.invocation"
RECIPE_LABEL = "androidforge.recipe_sha256"
CLI_TERMINATE_SECONDS = 1.0
CLI_KILL_SECONDS = 1.0
CLEANUP_SECONDS = 8.0
CLEANUP_POLL_SECONDS = 0.2
SOURCE_PROGRESS_INTERVAL_SECONDS = 30.0
KBUILD_BUILD_USER = "nomore"
KBUILD_BUILD_HOST = "coolnicknames"

BUILD_ENV_CONTRACTS: dict[str, dict[str, object]] = {
    "android-7.1": {
        "android_versions": ["7.1", "cm-14.1", "lineage-14.1"],
        "jdk": "openjdk-8",
        "python": "python2.7",
        "tools": ["repo", "make", "ninja", "jack", "gcc", "clang", "32-bit runtime libs"],
    },
    "android-8.1": {
        "android_versions": ["8.1", "lineage-15.1"],
        "jdk": "openjdk-8",
        "python": "python2.7",
        "tools": ["repo", "make", "ninja", "gcc", "clang", "32-bit runtime libs"],
    },
    "android-9": {
        "android_versions": ["9", "lineage-16.0"],
        "jdk": "openjdk-8",
        "python": "python2.7",
        "tools": ["repo", "make", "ninja", "soong_ui", "gcc", "clang", "32-bit runtime libs"],
    },
    "android-10-11": {
        "android_versions": ["10", "11", "lineage-17.1", "lineage-18.1"],
        "jdk": "openjdk-11",
        "python": "python3",
        "tools": ["repo", "make", "ninja", "soong_ui", "clang"],
    },
    "android-12-13": {
        "android_versions": ["12", "13", "lineage-19.1", "lineage-20.0"],
        "jdk": "openjdk-11",
        "python": "python3",
        "tools": ["repo", "make", "ninja", "soong_ui", "clang"],
    },
    "android-13-14": {
        "android_versions": ["13", "14", "lineage-20.0", "lineage-21.0"],
        "jdk": "openjdk-17",
        "python": "python3",
        "tools": ["repo", "make", "ninja", "soong_ui", "clang"],
    },
    "android-14-15": {
        "android_versions": ["14", "15", "lineage-21.0", "lineage-22.0"],
        "jdk": "openjdk-17",
        "python": "python3",
        "tools": ["repo", "make", "ninja", "soong_ui", "clang"],
    },
    "android-15-16": {
        "android_versions": ["15", "16", "lineage-22.0", "lineage-23.0"],
        "jdk": "openjdk-21",
        "python": "python3",
        "tools": ["repo", "make", "ninja", "soong_ui", "clang"],
    },
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildRecipe:
    image_tag: str
    source_mount_path: Path
    output_dir_in_container: str
    command: list[str]
    env: dict[str, str]
    idempotency_key: str
    timeout_seconds: int
    extra_mounts: list[tuple[Path, str, str]] = field(default_factory=list)
    build_env_key: str | None = None
    build_env_contract: dict[str, object] | None = None
    execution_profile: str = "local"
    scratch_mount_path: Path | None = None
    container_user: str | None = None
    image_id: str | None = None
    required_artifacts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Coerce Path so frozen dataclass works after json round-trip.
        object.__setattr__(self, "source_mount_path", Path(self.source_mount_path))
        env = dict(self.env or {})
        if self.execution_profile not in {"local", "cloud-mounted"}:
            raise ValueError("execution_profile must be local or cloud-mounted")
        if self.execution_profile == "cloud-mounted":
            if not self.scratch_mount_path or not Path(self.scratch_mount_path).is_absolute():
                raise ValueError("cloud-mounted requires an absolute scratch_mount_path")
            object.__setattr__(self, "scratch_mount_path", Path(self.scratch_mount_path))
            if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", self.container_user or ""):
                raise ValueError("cloud-mounted requires a non-root numeric container_user UID:GID")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id or ""):
                raise ValueError("cloud-mounted requires an immutable Docker image_id sha256")
            if not isinstance(self.timeout_seconds, int) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
                raise ValueError("cloud-mounted requires a positive timeout_seconds")
            if self.output_dir_in_container != "/workspace/out":
                raise ValueError("cloud-mounted requires output_dir_in_container=/workspace/out")
            if self.extra_mounts:
                raise ValueError("cloud-mounted requires all inputs in source_mount_path; extra_mounts are not attested")
            if not isinstance(self.required_artifacts, list) or not self.required_artifacts or any(
                not isinstance(name, str) or not name or Path(name).is_absolute()
                or ".." in Path(name).parts or str(Path(name)) != name
                for name in self.required_artifacts
            ):
                raise ValueError("cloud-mounted requires nonempty relative required_artifacts paths")
            for key, subdir in {"OUT_DIR": "out", "TMPDIR": "tmp", "CCACHE_DIR": "ccache", "HOME": "home"}.items():
                expected = f"/workspace/scratch/{subdir}"
                if env.get(key, expected) != expected:
                    raise ValueError(f"cloud-mounted requires {key}={expected}")
                env[key] = expected
        elif self.required_artifacts or any(value is not None for value in (self.scratch_mount_path, self.container_user, self.image_id)):
            raise ValueError("cloud fields require execution_profile=cloud-mounted")
        key = self.build_env_key or _infer_android_env_key(env=env, image_tag=self.image_tag)
        if self.execution_profile == "cloud-mounted" and (
            key not in BUILD_ENV_CONTRACTS or not self.image_tag.startswith("androidforge/build-")
        ):
            raise ValueError("cloud-mounted requires a recognized AndroidForge build image contract")
        contract = self.build_env_contract or (BUILD_ENV_CONTRACTS.get(key) if key else None)
        if key in BUILD_ENV_CONTRACTS:
            _validate_versioned_image(self.image_tag, key)
            env.setdefault("FORGE_BUILD_ENV_KEY", key)
            env.setdefault("FORGE_BUILD_ENV_CONTRACT_JSON", json.dumps(contract, sort_keys=True, separators=(",", ":")))
        env.setdefault("HOME", self.output_dir_in_container)
        env["KBUILD_BUILD_USER"] = KBUILD_BUILD_USER
        env["KBUILD_BUILD_HOST"] = KBUILD_BUILD_HOST
        object.__setattr__(self, "env", env)
        object.__setattr__(self, "build_env_key", key)
        object.__setattr__(self, "build_env_contract", contract)
        object.__setattr__(
            self,
            "extra_mounts",
            [
                (Path(h), c, m)
                for h, c, m in (self.extra_mounts or [])
            ],
        )

    def canonical_json(self) -> str:
        """Return deterministic JSON representation for hashing.

        FACT: sort_keys=True + separators=(',',':') removes all whitespace
        variance so the hash is stable across Python versions and platforms.
        """
        d = asdict(self)
        # Paths are not JSON-serialisable by default.
        d["source_mount_path"] = str(d["source_mount_path"])
        d["extra_mounts"] = [
            [str(h), c, m] for h, c, m in (self.extra_mounts or [])
        ]
        if self.execution_profile == "local":
            # Preserve existing local recipe hashes and cache identity.
            for key in ("execution_profile", "scratch_mount_path", "container_user", "image_id", "required_artifacts"):
                d.pop(key)
        else:
            d["scratch_mount_path"] = str(self.scratch_mount_path)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def recipe_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True)
class BuildResult:
    recipe_hash: str
    output_dir: Path
    success: bool
    exit_code: int
    log_path: Path
    artifacts: dict[str, str]
    container_id: str | None


# ---------------------------------------------------------------------------
# Hashing utilities
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """FACT: sha256 of file bytes, read in 1 MiB chunks to stay memory-safe."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_artifacts(output_dir: Path) -> dict[str, str]:
    """Hash every regular file without following or publishing symlinks."""
    result: dict[str, str] = {}
    for p in sorted(output_dir.rglob("*")):
        if p.is_symlink():
            continue
        if not p.is_file():
            continue
        rel = str(p.relative_to(output_dir))
        if rel.startswith(CONTAINER_METADATA_DIR + "/"):
            continue
        # Skip our own marker / log files from the artifact manifest.
        if rel in {SUCCESS_MARKER, FAILURE_MARKER, ARTIFACTS_JSON, BUILD_ENV_CONTRACT_JSON, RUN_LOG}:
            continue
        result[rel] = sha256_file(p)
    return result


def _infer_android_env_key(*, env: dict[str, str], image_tag: str) -> str | None:
    explicit = env.get("FORGE_BUILD_ENV_KEY")
    if explicit:
        return explicit
    raw = (
        env.get("FORGE_ROM_VERSION")
        or env.get("FORGE_ROM_BRANCH")
        or env.get("FORGE_ROM_ANDROID_VERSION")
        or env.get("LUNCH")
        or env.get("TARGET_PRODUCT")
        or image_tag.rsplit(":", 1)[-1]
        or ""
    ).lower()
    if raw in BUILD_ENV_CONTRACTS:
        return raw
    number = _first_version_number(raw)
    if raw.startswith("cm-") or "cm_" in raw or (number is not None and number <= 14.1):
        return "android-7.1"
    if number is not None and number <= 15.1:
        return "android-8.1"
    if number is not None and number <= 16.0:
        return "android-9"
    if number is not None and number <= 18.1:
        return "android-10-11"
    if number is not None and number <= 20.0:
        return "android-12-13"
    if number is not None and number <= 21.0:
        return "android-13-14"
    if number is not None and number <= 22.0:
        return "android-14-15"
    if number is not None:
        return "android-15-16"
    return None


def _first_version_number(text: str) -> float | None:
    import re

    match = re.search(r"(?<!\d)(\d{1,2}(?:\.\d)?)(?!\d)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _validate_versioned_image(image_tag: str, key: str) -> None:
    lowered = image_tag.strip().lower()
    if lowered in {"host", "local", "none"} or lowered.startswith("host:"):
        raise ValueError(f"{key} requires a Docker build image; host fallback is forbidden")
    tag = lowered.rsplit(":", 1)[-1]
    if tag != key:
        raise ValueError(
            f"{key} requires image tag '*:{key}', got {image_tag!r}. "
            "Build it with: docker compose -f infra/build-envs/compose.build-envs.yml build "
            f"{key}."
        )


def write_build_env_contract(output_dir: Path, recipe: BuildRecipe) -> None:
    if not recipe.build_env_key:
        return
    (output_dir / BUILD_ENV_CONTRACT_JSON).write_text(
        json.dumps(
            {
                "build_env_key": recipe.build_env_key,
                "image_tag": recipe.image_tag,
                "contract": recipe.build_env_contract,
                **({"execution_profile": recipe.execution_profile, "image_id": recipe.image_id,
                    "container_user": recipe.container_user} if recipe.execution_profile == "cloud-mounted" else {}),
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------


def _git_output(source_dir: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(source_dir), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"cannot verify source provenance for {source_dir}: {exc}") from exc


def _git_head_and_diff(source_dir: Path) -> tuple[bytes, bytes]:
    try:
        head = _git_output(source_dir, "rev-parse", "--verify", "HEAD").strip()
    except RuntimeError as head_error:
        try:
            symbolic_head = _git_output(source_dir, "symbolic-ref", "-q", "HEAD").strip()
            cached_diff = _git_output(source_dir, "diff", "--binary", "--cached", "--")
            worktree_diff = _git_output(source_dir, "diff", "--binary", "--")
        except RuntimeError:
            raise head_error
        return (
            b"<unborn>:" + symbolic_head,
            b"git-diff-cached\0" + cached_diff + b"git-diff-worktree\0" + worktree_diff,
        )
    return head, _git_output(source_dir, "diff", "--binary", "HEAD", "--")


@dataclass
class _SourceProvenanceProgress:
    """Best-effort stderr telemetry, never part of the source identity."""

    source_dir: Path
    pass_index: int
    files: int = 0
    bytes_read: int = 0
    current_path: str = "."
    started: float = field(default_factory=time.monotonic)
    last_emit: float = field(init=False)

    def __post_init__(self) -> None:
        self.last_emit = self.started
        self._emit("start", self.started)

    def _emit(self, event: str, now: float, status: str | None = None) -> None:
        record = {
            "event": event, "pass": self.pass_index, "files": self.files,
            "bytes": self.bytes_read, "elapsed_seconds": round(now - self.started, 3),
            "current_path": self.current_path,
        }
        if status is not None:
            record["status"] = status
        try:
            print("==> source_provenance " + json.dumps(record, sort_keys=True),
                  file=sys.stderr, flush=True)
        except (OSError, ValueError):
            # A closed or unavailable progress sink must not change provenance.
            pass

    def _tick(self) -> None:
        now = time.monotonic()
        if now - self.last_emit >= SOURCE_PROGRESS_INTERVAL_SECONDS:
            self._emit("progress", now)
            self.last_emit = now

    def visit(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.source_dir).as_posix()
        except ValueError:
            relative = "<outside-source>"
        self.current_path = relative if len(relative) <= 240 else relative[:237] + "..."
        self._tick()

    def read(self, size: int) -> None:
        self.bytes_read += size
        self._tick()

    def file_done(self) -> None:
        self.files += 1
        self._tick()

    def finish(self, status: str) -> None:
        self._emit("end", time.monotonic(), status)


def _source_provenance_snapshot(
    source_dir: Path, progress: _SourceProvenanceProgress | None = None,
) -> dict[str, str]:
    head, diff = _git_head_and_diff(source_dir)
    index_entries = _git_output(source_dir, "ls-files", "-v", "-z").split(b"\0")
    flagged = [entry for entry in index_entries if entry and not entry.startswith(b"H ")]
    if flagged:
        paths = ", ".join(os.fsdecode(entry[2:]) for entry in flagged)
        raise RuntimeError(
            f"source index contains hidden or nonstandard tracked entries: {paths}"
        )
    status = _git_output(
        source_dir, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    untracked = _git_output(
        source_dir, "ls-files", "-z", "--others", "--exclude-standard"
    ).split(b"\0")
    ignored = _git_output(
        source_dir, "ls-files", "-z", "--others", "--ignored", "--exclude-standard"
    ).split(b"\0")
    gitlinks = []
    for entry in _git_output(source_dir, "ls-files", "-z", "--stage").split(b"\0"):
        if not entry.startswith(b"160000 "):
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
        except ValueError as exc:
            raise RuntimeError(f"malformed gitlink entry in {source_dir}") from exc
        gitlinks.append((raw_path, metadata))

    content = hashlib.sha256()
    content.update(b"git-diff\0")
    content.update(diff)
    for raw_path, metadata in sorted(gitlinks):
        path = source_dir / os.fsdecode(raw_path)
        if progress is not None:
            progress.visit(path)
        content.update(b"gitlink\0")
        content.update(raw_path)
        content.update(b"\0")
        content.update(metadata)
        content.update(b"\0")
        if not path.exists():
            content.update(b"uninitialized\0")
            continue
        if not path.is_dir():
            raise RuntimeError(f"git submodule path is not a directory: {path}")
        submodule_root = Path(
            os.fsdecode(_git_output(path, "rev-parse", "--show-toplevel").strip())
        )
        if submodule_root.resolve() != path.resolve():
            if any(path.iterdir()):
                raise RuntimeError(
                    f"uninitialized git submodule path is not empty: {path}"
                )
            content.update(b"uninitialized\0")
            continue
        submodule_status = _git_output(
            path, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        )
        if submodule_status:
            raise RuntimeError(f"git submodule worktree must be clean: {path}")
        submodule_provenance = _source_provenance_snapshot(path, progress)
        content.update(b"initialized\0")
        content.update(
            json.dumps(
                submodule_provenance,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        content.update(b"\0")
    for kind, paths in ((b"untracked", untracked), (b"ignored", ignored)):
        for raw_path in sorted(path for path in paths if path):
            path = source_dir / os.fsdecode(raw_path)
            if progress is not None:
                progress.visit(path)
            content.update(kind + b"\0")
            content.update(raw_path)
            content.update(b"\0")
            try:
                if path.is_symlink():
                    content.update(b"symlink\0")
                    content.update(os.fsencode(os.readlink(path)))
                    if progress is not None:
                        progress.file_done()
                elif path.is_file():
                    content.update(b"file\0")
                    with path.open("rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            content.update(chunk)
                            if progress is not None:
                                progress.read(len(chunk))
                    if progress is not None:
                        progress.file_done()
                elif path.is_dir():
                    nested_root_raw = _git_output(path, "rev-parse", "--show-toplevel").strip()
                    nested_root = Path(os.fsdecode(nested_root_raw))
                    if nested_root.resolve() != path.resolve():
                        raise RuntimeError(
                            f"source directory is not an embedded git repository: {path}"
                        )
                    content.update(b"git-repository\0")
                    content.update(
                        json.dumps(
                            _source_provenance_snapshot(path, progress),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                else:
                    raise RuntimeError(f"source path is not a file: {path}")
            except OSError as exc:
                raise RuntimeError(f"cannot hash source path {path}: {exc}") from exc

    return {
        "git_head": head.decode("ascii"),
        "git_status_sha256": hashlib.sha256(status).hexdigest(),
        "working_tree_sha256": content.hexdigest(),
    }


def current_source_provenance(source_dir: Path) -> dict[str, str]:
    """Return a content-sensitive source identity stable across two snapshots."""
    snapshots = []
    for pass_index in (1, 2):
        progress = _SourceProvenanceProgress(source_dir, pass_index)
        try:
            snapshot = _source_provenance_snapshot(source_dir, progress)
        except BaseException:
            progress.finish("failed")
            raise
        progress.finish("complete")
        snapshots.append(snapshot)
    first, second = snapshots
    if first != second:
        raise RuntimeError(f"source tree changed while provenance was being computed: {source_dir}")
    return first


def read_cached_artifacts(output_dir: Path) -> dict[str, str]:
    """Load and verify every artifact recorded by a cached successful run."""
    path = output_dir / ARTIFACTS_JSON
    try:
        artifacts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cached artifact manifest is unavailable or malformed: {exc}") from exc
    if not isinstance(artifacts, dict) or not all(
        isinstance(name, str)
        and isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
        for name, digest in artifacts.items()
    ):
        raise RuntimeError(
            "cached artifact manifest must map strings to lowercase SHA-256 digests"
        )

    root = output_dir.resolve()
    for name, expected in artifacts.items():
        artifact = output_dir / name
        try:
            if artifact.is_symlink():
                raise RuntimeError(f"cached artifact must not be a symlink: {name}")
            resolved = artifact.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(f"cached artifact is missing: {name}: {exc}") from exc
        if root not in resolved.parents or not resolved.is_file():
            raise RuntimeError(f"cached artifact path is unsafe or not a file: {name}")
        actual = sha256_file(resolved)
        if actual != expected:
            raise RuntimeError(
                f"cached artifact digest mismatch for {name}: expected {expected}, got {actual}"
            )
    return artifacts


def read_success_marker(output_dir: Path) -> dict | None:
    marker = output_dir / SUCCESS_MARKER
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SUCCESS marker is unavailable or malformed: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("SUCCESS marker must be a JSON object")
    return data


def write_success_marker(
    output_dir: Path,
    recipe_hash: str,
    artifacts: dict,
    source_provenance: dict[str, str],
) -> None:
    manifest = output_dir / ARTIFACTS_JSON
    marker = output_dir / SUCCESS_MARKER
    manifest_pending = output_dir / f".{ARTIFACTS_JSON}.pending.{os.getpid()}"
    marker_pending = output_dir / f".{SUCCESS_MARKER}.pending.{os.getpid()}"
    manifest_pending.write_text(
        json.dumps(artifacts, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    manifest_sha256 = sha256_file(manifest_pending)
    marker_pending.write_text(
        json.dumps(
            {
                "recipe_hash": recipe_hash,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "artifacts_count": len(artifacts),
                "artifacts_sha256": manifest_sha256,
                "source_provenance": source_provenance,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest_pending.replace(manifest)
    marker_pending.replace(marker)


def write_failure_marker(output_dir: Path, exit_code: int, log_path: Path) -> None:
    marker = output_dir / FAILURE_MARKER
    last_lines: list[str] = []
    if log_path.exists():
        try:
            last_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        except Exception:
            pass
    marker.write_text(
        json.dumps(
            {
                "exit_code": exit_code,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_log_lines": last_lines,
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Docker invocation
# ---------------------------------------------------------------------------


def cloud_scratch_dir(recipe: BuildRecipe) -> Path:
    assert recipe.scratch_mount_path is not None
    return recipe.scratch_mount_path / "forge-scratch" / recipe.recipe_hash()


def _mount_filesystems() -> dict[Path, tuple[str, str]]:
    """Read Linux mount identity without invoking a shell or accepting a bind of /."""
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields, filesystem = left.split(), right.split()[0]
        mountpoint = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
        mounts[Path(mountpoint)] = (fields[2], filesystem)
    return mounts


def validate_cloud_profile(recipe: BuildRecipe) -> None:
    """Fail closed before mkdir/cache/containers if an explicit cloud disk is absent."""
    mount = recipe.scratch_mount_path
    assert mount is not None
    if mount == Path("/") or mount.resolve(strict=True) != mount or not mount.is_dir():
        raise ValueError("cloud scratch must be a real, canonical, non-root mount directory")
    mounts = _mount_filesystems()
    identity = mounts.get(mount)
    if not identity or identity[1] not in {"ext4", "xfs"} or identity[0] == mounts[Path("/")][0]:
        raise ValueError("cloud scratch requires a separate mounted ext4/xfs filesystem, not the root disk")
    source = recipe.source_mount_path.resolve(strict=True)
    if not source.is_dir() or source != recipe.source_mount_path:
        raise ValueError("cloud source_mount_path must be a canonical absolute directory")
    for path in (FORGE_EPHEMERAL_BASE, FORGE_EPHEMERAL_BASE / recipe.recipe_hash(), cloud_scratch_dir(recipe)):
        resolved = path.resolve()
        if not path.is_absolute() or resolved != path or not path.is_relative_to(mount) or path == mount:
            raise ValueError(f"cloud output must remain inside the mounted disk without symlinks: {path}")
        if path.is_relative_to(source) or source.is_relative_to(path):
            raise ValueError("cloud source and writable output directories must not overlap")
    scratch = cloud_scratch_dir(recipe)
    if scratch.is_relative_to(FORGE_EPHEMERAL_BASE) or FORGE_EPHEMERAL_BASE.is_relative_to(scratch):
        raise ValueError("cloud scratch and artifact publication directories must not overlap")
    uid, gid = map(int, recipe.container_user.split(":"))
    if os.getuid() != 0 and (uid, gid) != (os.getuid(), os.getgid()):
        raise ValueError("container_user mapping requires root launcher or the same host UID:GID")
    inspected = subprocess.run(
        ["docker", "image", "inspect", recipe.image_tag, "--format", "{{.Id}}"],
        capture_output=True, text=True, timeout=15, check=True,
    )
    if inspected.stdout.strip() != recipe.image_id:
        raise ValueError("cloud Docker image identity differs from the recipe image_id")


def prepare_cloud_directories(recipe: BuildRecipe, output_dir: Path) -> None:
    uid, gid = map(int, recipe.container_user.split(":"))
    scratch = cloud_scratch_dir(recipe)
    for path in (output_dir, scratch, *(scratch / name for name in ("out", "tmp", "ccache", "home"))):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"cloud writable directory must not be a symlink: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if os.getuid() == 0:
            os.chown(path, uid, gid)
        elif (path.stat().st_uid, path.stat().st_gid) != (uid, gid):
            raise ValueError(f"cloud writable directory has a different owner: {path}")


def validate_required_artifacts(recipe: BuildRecipe, output_dir: Path, artifacts: dict[str, str]) -> None:
    for name in recipe.required_artifacts:
        if name not in artifacts or (output_dir / name).stat().st_size == 0:
            raise RuntimeError(f"required artifact is missing or empty: {name}")


def build_docker_argv(
    recipe: BuildRecipe,
    output_dir: Path,
    container_name: str,
) -> list[str]:
    """Construct the docker create argument list; starting is a separate phase.

    FACT: Uses exec form (list passed directly to subprocess) — no shell
    injection is possible because subprocess never invokes a shell.
    """
    uid_gid = recipe.container_user or f"{os.getuid()}:{os.getgid()}"

    argv: list[str] = [
        "docker", "create",
        "--rm",
        f"--name={container_name}",
        f"--user={uid_gid}",
        "-v", f"{recipe.source_mount_path}:/workspace/src:ro",
        "-v", f"{output_dir}:{recipe.output_dir_in_container}:rw",
        "--workdir", "/workspace",
    ]
    if recipe.execution_profile == "cloud-mounted":
        argv += ["-v", f"{cloud_scratch_dir(recipe)}:/workspace/scratch:rw", "--network=none"]

    for host_path, container_path, mode in (recipe.extra_mounts or []):
        argv += ["-v", f"{host_path}:{container_path}:{mode}"]

    for key, val in recipe.env.items():
        argv += ["-e", f"{key}={val}"]

    argv.append(recipe.image_id or recipe.image_tag)
    argv.extend(recipe.command)

    return argv


def _write_container_state(path: Path, state: dict) -> None:
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
    pending.replace(path)


def _terminate_cli(proc: subprocess.Popen) -> bool:
    """Stop and reap only our directly spawned Docker client, within a bound."""
    if proc.poll() is not None:
        return True
    try:
        proc.terminate()
        proc.wait(timeout=CLI_TERMINATE_SECONDS)
        return True
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=CLI_KILL_SECONDS)
            return True
        except subprocess.TimeoutExpired:
            return False
    except ProcessLookupError:
        try:
            proc.wait(timeout=CLI_KILL_SECONDS)
            return True
        except subprocess.TimeoutExpired:
            return False


def _wait_container_cli(argv: list[str], log_fh, cancelled: list[int], deadline: float | None = None) -> tuple[int, bool, bool]:
    if cancelled[0]:
        return 128 + cancelled[0], True, False
    if deadline is not None and time.monotonic() >= deadline:
        return 124, True, False
    # Direct file output avoids blocking forever on a silent stdout iterator.
    # The signal handler never raises while Popen is assigning the child handle.
    with Path(log_fh.name).open("rb") as log_reader:
        log_fh.flush()
        log_reader.seek(log_fh.tell())

        def relay_debug_output() -> None:
            if log.isEnabledFor(logging.DEBUG):
                # Snapshot the file end so a noisy child cannot keep this loop
                # busy indefinitely and postpone cancellation processing.
                remaining = os.fstat(log_reader.fileno()).st_size - log_reader.tell()
                while remaining > 0:
                    chunk = log_reader.read(min(remaining, 65536))
                    if not chunk:
                        break
                    sys.stderr.buffer.write(chunk)
                    remaining -= len(chunk)
                sys.stderr.buffer.flush()

        proc = subprocess.Popen(argv, stdout=log_fh, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while not cancelled[0]:
                if deadline is not None and time.monotonic() >= deadline:
                    return 124, _terminate_cli(proc), True
                try:
                    code = proc.wait(timeout=0.2)
                    if deadline is not None and time.monotonic() >= deadline:
                        return 124, True, True
                    return code, True, True
                except subprocess.TimeoutExpired:
                    relay_debug_output()
            return 128 + cancelled[0], _terminate_cli(proc), True
        finally:
            if proc.poll() is None:
                _terminate_cli(proc)
            relay_debug_output()


def _cleanup_owned_container(state: dict) -> dict:
    """Reconcile by exact invocation name, verify labels, then remove by full ID.

    An absent name after interrupted create is NOT proof of cancellation at the
    daemon. Keep cleanup_needed unless an identified object was removed, or a
    known completed create's ID is confirmed absent.
    """
    if not state.get("create_issued") and state.get("client_reaped"):
        return {"cleanup_needed": False, "cleanup_reason": "cancelled before create was issued"}
    deadline = time.monotonic() + CLEANUP_SECONDS
    target = state.get("container_id") or state["container_name"]
    result = {"cleanup_needed": True, "cleanup_reason": "daemon state unresolved"}
    while time.monotonic() < deadline:
        timeout = max(0.01, min(1.0, deadline - time.monotonic()))
        try:
            inspected = subprocess.run(
                ["docker", "container", "inspect", target], capture_output=True, text=True,
                check=False, timeout=timeout,
            )
            if inspected.returncode:
                missing = "No such object" in inspected.stderr or "No such container" in inspected.stderr
                if missing and state.get("container_id") and state.get("client_reaped"):
                    return {"cleanup_needed": False, "cleanup_reason": "known container absent"}
                result["cleanup_reason"] = "create may complete late" if missing else "inspect failed"
            else:
                objects = json.loads(inspected.stdout)
                obj = objects[0] if isinstance(objects, list) and len(objects) == 1 else {}
                if not isinstance(obj, dict) or not isinstance(obj.get("Config"), dict):
                    raise ValueError("invalid inspect object")
                labels = (obj.get("Config") or {}).get("Labels") or {}
                if not isinstance(labels, dict):
                    raise ValueError("invalid inspect labels")
                cid = obj.get("Id", "")
                if (
                    labels.get(OWNER_LABEL) != state["invocation"]
                    or labels.get(RECIPE_LABEL) != state["recipe_hash"]
                    or obj.get("Name") != "/" + state["container_name"]
                    or not isinstance(cid, str) or len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid)
                    or (state.get("container_id") and state["container_id"] != cid)
                ):
                    return {"cleanup_needed": True, "cleanup_reason": "container ownership mismatch"}
                state["container_id"] = cid
                target = cid
                removed = subprocess.run(
                    ["docker", "container", "rm", "--force", cid], capture_output=True, text=True,
                    check=False, timeout=max(0.01, min(1.0, deadline - time.monotonic())),
                )
                if removed.returncode == 0 and state.get("client_reaped"):
                    return {"cleanup_needed": False, "cleanup_reason": "owned container removed"}
                result["cleanup_reason"] = "owned removal or client reap incomplete"
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
            result["cleanup_reason"] = f"cleanup unavailable: {exc}"
        time.sleep(min(CLEANUP_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    return result


def pending_container_cleanup(output_dir: Path) -> list[Path]:
    pending = []
    for path in (output_dir / CONTAINER_METADATA_DIR).glob("*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("cleanup_needed", True):
                pending.append(path)
        except (OSError, ValueError, AttributeError):
            pending.append(path)
    return pending


def run_container(
    recipe: BuildRecipe,
    output_dir: Path,
    container_name: str,
    log_path: Path,
) -> int:
    """Create then start one owned container; cancellation never starts a late create."""
    invocation = secrets.token_hex(16)
    container_name = f"{container_name}-{invocation[:12]}"
    metadata = output_dir / CONTAINER_METADATA_DIR
    metadata.mkdir(mode=0o700, exist_ok=True)
    state_path = metadata / f"{invocation}.json"
    cid_path = metadata / f"{invocation}.cid"
    state: dict[str, Any] = {
        "invocation": invocation, "recipe_hash": recipe.recipe_hash(),
        "container_name": container_name, "container_id": None,
        "cidfile": str(cid_path), "phase": "creating", "cleanup_needed": True,
        "client_reaped": False, "create_issued": False,
    }
    _write_container_state(state_path, state)
    argv = build_docker_argv(recipe, output_dir, container_name)
    argv[2:2] = [f"--cidfile={cid_path}", f"--label={OWNER_LABEL}={invocation}",
                 f"--label={RECIPE_LABEL}={state['recipe_hash']}"]
    log.debug("docker argv: %s", argv)
    cancelled = [0]
    deadline = time.monotonic() + recipe.timeout_seconds if recipe.execution_profile == "cloud-mounted" else None

    def _cancel(signum: int, _frame) -> None:  # noqa: ANN001
        if not cancelled[0]:
            cancelled[0] = signum

    handlers = {sig: signal.signal(sig, _cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
    exit_code = 1
    try:
        with log_path.open("ab") as log_fh:
            exit_code, state["client_reaped"], state["create_issued"] = _wait_container_cli(argv, log_fh, cancelled, deadline)
            if cid_path.is_file():
                cid = cid_path.read_text(encoding="ascii").strip()
                if len(cid) == 64 and all(c in "0123456789abcdef" for c in cid):
                    state["container_id"] = cid
            if cancelled[0]:
                exit_code = 128 + cancelled[0]
            elif exit_code == 0:
                if not state["container_id"]:
                    log_fh.write(b"forge: successful create missing a valid container ID\n")
                    exit_code = 125
                else:
                    state["phase"] = "starting"
                    state["client_reaped"] = False
                    _write_container_state(state_path, state)
                    exit_code, state["client_reaped"], _ = _wait_container_cli(
                        ["docker", "start", "--attach", state["container_id"]], log_fh, cancelled, deadline,
                    )
            if cancelled[0]:
                exit_code = 128 + cancelled[0]
                log_fh.write(f"forge: cancelled signal={cancelled[0]} invocation={invocation}\n".encode())
            state["exit_code"] = exit_code
            state["phase"] = "cancelled" if cancelled[0] else "finished"
            if not cancelled[0] and deadline is not None and exit_code == 124 and time.monotonic() >= deadline:
                state["phase"] = "timed_out"
                log_fh.write(f"forge: timeout_seconds={recipe.timeout_seconds} invocation={invocation}\n".encode())
            if exit_code == 0:
                state.update(cleanup_needed=False, cleanup_reason="attached container exited; auto-remove enabled")
            else:
                state.update(_cleanup_owned_container(state))
            _write_container_state(state_path, state)
    except OSError as exc:
        state.update(phase="failed", exit_code=127, error=str(exc))
        state.update(_cleanup_owned_container(state))
        _write_container_state(state_path, state)
        exit_code = 127
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    if state["cleanup_needed"]:
        print(f"ERROR: cleanup unresolved; resume blocked by {state_path}", file=sys.stderr)
    return exit_code


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------


def run_build(recipe: BuildRecipe, *, no_resume: bool = False, dry_run: bool = False) -> BuildResult:
    if dry_run:
        return _run_build(recipe, no_resume=no_resume, dry_run=True)
    if recipe.execution_profile == "cloud-mounted":
        try:
            validate_cloud_profile(recipe)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            output_dir = FORGE_EPHEMERAL_BASE / recipe.recipe_hash()
            print(f"ERROR: cloud preflight rejected: {exc}", file=sys.stderr)
            return BuildResult(recipe.recipe_hash(), output_dir, False, 125, output_dir / RUN_LOG, {}, None)
    rhash = recipe.recipe_hash()
    lock_dir = FORGE_EPHEMERAL_BASE / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    # Cross-process ownership covers cache validation, provenance, container
    # lifecycle and marker publication, not merely the final Docker command.
    with (lock_dir / f"{rhash}.lock").open("a+") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            output_dir = FORGE_EPHEMERAL_BASE / rhash
            print(f"ERROR: another launcher owns recipe {rhash}", file=sys.stderr)
            return BuildResult(rhash, output_dir, False, 125, output_dir / RUN_LOG, {}, None)
        try:
            return _run_build(recipe, no_resume=no_resume)
        finally:
            fcntl.flock(lease, fcntl.LOCK_UN)


def _run_build(recipe: BuildRecipe, *, no_resume: bool = False, dry_run: bool = False) -> BuildResult:
    """Execute (or cache-hit) a build recipe.

    FACT: recipe_hash is computed before any filesystem access so the hash is
    purely a function of the recipe inputs, not of any prior run state.
    """
    rhash = recipe.recipe_hash()
    output_dir = FORGE_EPHEMERAL_BASE / rhash
    log_path = output_dir / RUN_LOG
    container_name = f"forge-eph-{rhash[:12]}"

    log.info("recipe_hash=%s  output_dir=%s", rhash, output_dir)

    if dry_run:
        argv = build_docker_argv(recipe, output_dir, container_name)
        print("DRY-RUN docker invocation:")
        print("  " + " ".join(argv))
        return BuildResult(
            recipe_hash=rhash,
            output_dir=output_dir,
            success=False,
            exit_code=-1,
            log_path=log_path,
            artifacts={},
            container_id=None,
        )

    # ------------------------------------------------------------------
    # Check for cached success
    # ------------------------------------------------------------------
    if output_dir.exists():
        pending = pending_container_cleanup(output_dir)
        if pending:
            print(f"ERROR: unresolved container cleanup; refusing resume: {pending}", file=sys.stderr)
            return BuildResult(rhash, output_dir, False, 125, log_path, {}, None)
        try:
            marker_data = read_success_marker(output_dir)
        except RuntimeError as exc:
            print(f"ERROR: refusing cached SUCCESS: {exc}", file=sys.stderr)
            sys.exit(1)
        if marker_data is not None:
            recorded_provenance = marker_data.get("source_provenance")
            try:
                if marker_data.get("recipe_hash") != rhash:
                    raise RuntimeError("SUCCESS marker recipe hash does not match its directory")
                source_provenance = current_source_provenance(recipe.source_mount_path)
                if recorded_provenance != source_provenance:
                    raise RuntimeError(
                        "current source provenance does not match the successful run: "
                        f"recorded={recorded_provenance!r}, current={source_provenance!r}"
                    )
                manifest_path = output_dir / ARTIFACTS_JSON
                recorded_manifest_sha256 = marker_data.get("artifacts_sha256")
                if (
                    not isinstance(recorded_manifest_sha256, str)
                    or len(recorded_manifest_sha256) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in recorded_manifest_sha256
                    )
                ):
                    raise RuntimeError(
                        "SUCCESS marker does not contain a valid artifacts.json digest"
                    )
                try:
                    current_manifest_sha256 = sha256_file(manifest_path)
                except OSError as exc:
                    raise RuntimeError(
                        f"cached artifact manifest is unavailable: {exc}"
                    ) from exc
                if current_manifest_sha256 != recorded_manifest_sha256:
                    raise RuntimeError(
                        "cached artifacts.json digest does not match SUCCESS marker"
                    )
                artifacts = read_cached_artifacts(output_dir)
                validate_required_artifacts(recipe, output_dir, artifacts)
                artifacts_count = marker_data.get("artifacts_count")
                if (
                    not isinstance(artifacts_count, int)
                    or isinstance(artifacts_count, bool)
                    or artifacts_count != len(artifacts)
                ):
                    raise RuntimeError(
                        "SUCCESS marker artifact count does not match artifacts.json"
                    )
            except RuntimeError as exc:
                print(f"ERROR: refusing cached SUCCESS: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"CACHED  recipe_hash={rhash}  output_dir={output_dir}", file=sys.stderr)
            return BuildResult(
                recipe_hash=rhash,
                output_dir=output_dir,
                success=True,
                exit_code=0,
                log_path=log_path,
                artifacts=artifacts,
                container_id=None,
            )

        # Output dir exists but no SUCCESS marker — prior failure or partial run.
        if no_resume:
            print(
                f"ERROR: output dir exists without SUCCESS marker and --no-resume is set.\n"
                f"       output_dir={output_dir}\n"
                f"       Remove or rename the directory manually, or drop --no-resume to retry.",
                file=sys.stderr,
            )
            sys.exit(1)

        log.info("Prior run found without SUCCESS marker — resuming (re-running docker).")

    if recipe.execution_profile == "cloud-mounted":
        try:
            prepare_cloud_directories(recipe, output_dir)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cloud output preparation rejected: {exc}", file=sys.stderr)
            return BuildResult(rhash, output_dir, False, 125, log_path, {}, None)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
    write_build_env_contract(output_dir, recipe)

    try:
        source_provenance_before = current_source_provenance(recipe.source_mount_path)
    except RuntimeError as exc:
        write_failure_marker(output_dir, 1, log_path)
        print(f"==> FAILURE  source provenance unavailable: {exc}", file=sys.stderr)
        return BuildResult(
            recipe_hash=rhash,
            output_dir=output_dir,
            success=False,
            exit_code=1,
            log_path=log_path,
            artifacts={},
            container_id=None,
        )

    # ------------------------------------------------------------------
    # Run the container
    # ------------------------------------------------------------------
    print(
        f"==> forge_ephemeral_build  container={container_name}  hash={rhash}",
        file=sys.stderr,
    )
    print(f"    output_dir={output_dir}", file=sys.stderr)
    print(f"    image={recipe.image_tag}", file=sys.stderr)
    print(f"    command={recipe.command}", file=sys.stderr)

    exit_code = run_container(recipe, output_dir, container_name, log_path)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------
    if exit_code == 0:
        try:
            artifacts = collect_artifacts(output_dir)
            validate_required_artifacts(recipe, output_dir, artifacts)
            source_provenance_after = current_source_provenance(recipe.source_mount_path)
            if source_provenance_after != source_provenance_before:
                raise RuntimeError(
                    "source tree changed while the container was building: "
                    f"before={source_provenance_before!r}, "
                    f"after={source_provenance_after!r}"
                )
            write_success_marker(output_dir, rhash, artifacts, source_provenance_before)
        except (OSError, RuntimeError) as exc:
            write_failure_marker(output_dir, 1, log_path)
            print(f"==> FAILURE  artifact publication rejected: {exc}", file=sys.stderr)
            return BuildResult(
                recipe_hash=rhash,
                output_dir=output_dir,
                success=False,
                exit_code=1,
                log_path=log_path,
                artifacts={},
                container_id=None,
            )
        print(
            f"==> SUCCESS  recipe_hash={rhash}  artifacts={len(artifacts)}  log={log_path}",
            file=sys.stderr,
        )
        return BuildResult(
            recipe_hash=rhash,
            output_dir=output_dir,
            success=True,
            exit_code=0,
            log_path=log_path,
            artifacts=artifacts,
            container_id=None,
        )

    # ------------------------------------------------------------------
    # Failure path
    # ------------------------------------------------------------------
    write_failure_marker(output_dir, exit_code, log_path)
    print(
        f"==> FAILURE  recipe_hash={rhash}  exit_code={exit_code}  log={log_path}",
        file=sys.stderr,
    )
    return BuildResult(
        recipe_hash=rhash,
        output_dir=output_dir,
        success=False,
        exit_code=exit_code,
        log_path=log_path,
        artifacts={},
        container_id=None,
    )


# ---------------------------------------------------------------------------
# Recipe loading (YAML / JSON)
# ---------------------------------------------------------------------------


def load_recipe_from_file(path: Path) -> BuildRecipe:
    """Load a BuildRecipe from a YAML or JSON file.

    FACT: PyYAML is optional. If not installed, JSON is accepted instead.
    A missing PyYAML produces a clear error only when a .yaml/.yml file is
    supplied; .json files always work without any extra dependency.
    """
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(text)
        except ImportError:
            print(
                "ERROR: PyYAML is not installed and a .yaml recipe was supplied.\n"
                "       Install it with: pip install pyyaml\n"
                "       Or convert the recipe to .json format.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        data = json.loads(text)

    return recipe_from_dict(data)


def recipe_from_dict(data: dict) -> BuildRecipe:
    """Build a BuildRecipe from a plain dict (from YAML or JSON)."""
    extra_raw = data.get("extra_mounts") or []
    extra_mounts: list[tuple[Path, str, str]] = [
        (Path(h), str(c), str(m)) for h, c, m in extra_raw
    ]
    return BuildRecipe(
        image_tag=str(data["image_tag"]),
        source_mount_path=Path(data["source_mount_path"]),
        output_dir_in_container=str(data["output_dir_in_container"]),
        command=list(data["command"]),
        env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
        idempotency_key=str(data["idempotency_key"]),
        timeout_seconds=int(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        extra_mounts=extra_mounts,
        build_env_key=data.get("build_env_key"),
        build_env_contract=data.get("build_env_contract"),
        execution_profile=data.get("execution_profile", "local"),
        scratch_mount_path=data.get("scratch_mount_path"),
        container_user=data.get("container_user"),
        image_id=data.get("image_id"),
        required_artifacts=data.get("required_artifacts", []),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Launch an ephemeral Docker build container for AndroidForge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # YAML recipe (preferred):
  forge_ephemeral_build.py --recipe /srv/forge/recipes/kernel-m681.yaml

  # Inline flags:
  forge_ephemeral_build.py \\
      --image androidforge/build-android-5.0:latest \\
      --mount /srv/forge/android/kernel-src \\
      --cmd make -j$(nproc) \\
      --idempotency-key kernel-m681-v1

  # Dry run (print docker command, don't run):
  forge_ephemeral_build.py --recipe kernel.yaml --dry-run
""",
    )

    p.add_argument(
        "--recipe",
        metavar="PATH",
        help="Path to a YAML or JSON recipe file (preferred over individual flags).",
    )

    # Flat flag alternatives
    p.add_argument("--image", metavar="IMAGE_TAG", help="Docker image tag.")
    p.add_argument(
        "--mount",
        metavar="HOST_PATH",
        help="Host path mounted read-only to /workspace/src.",
    )
    p.add_argument(
        "--cmd",
        nargs=argparse.REMAINDER,
        metavar="CMD",
        help="Command to run inside the container.",
    )
    p.add_argument(
        "--output-dir-in-container",
        default="/workspace/out",
        metavar="PATH",
        help="Container path for output (default: /workspace/out).",
    )
    p.add_argument(
        "--idempotency-key",
        metavar="KEY",
        help="Human-chosen idempotency key (folded into recipe hash).",
    )
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="Environment variable passed to container. Repeatable.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"Container stop timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )

    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker invocation without running it.",
    )
    p.add_argument(
        "--no-resume",
        action="store_true",
        help="Refuse to re-run if output dir exists without SUCCESS marker.",
    )
    p.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v = INFO, -vv = DEBUG).",
    )

    return p.parse_args()


def build_recipe_from_args(args: argparse.Namespace) -> BuildRecipe:
    missing = []
    if not args.image:
        missing.append("--image")
    if not args.mount:
        missing.append("--mount")
    if not args.cmd:
        missing.append("--cmd")
    if not args.idempotency_key:
        missing.append("--idempotency-key")
    if missing:
        print(
            f"ERROR: missing required flags when --recipe is not supplied: {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    env: dict[str, str] = {}
    for kv in args.env or []:
        if "=" not in kv:
            print(f"ERROR: --env value must be KEY=VALUE, got: {kv!r}", file=sys.stderr)
            sys.exit(1)
        k, _, v = kv.partition("=")
        env[k] = v

    return BuildRecipe(
        image_tag=args.image,
        source_mount_path=Path(args.mount),
        output_dir_in_container=args.output_dir_in_container,
        command=list(args.cmd),
        env=env,
        idempotency_key=args.idempotency_key,
        timeout_seconds=args.timeout,
    )


def main() -> int:
    args = parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    if args.recipe:
        recipe_path = Path(args.recipe)
        if not recipe_path.exists():
            print(f"ERROR: recipe file not found: {recipe_path}", file=sys.stderr)
            return 1
        recipe = load_recipe_from_file(recipe_path)
    else:
        recipe = build_recipe_from_args(args)

    result = run_build(recipe, no_resume=args.no_resume, dry_run=args.dry_run)

    # Emit structured result to stdout for programmatic callers.
    print(
        json.dumps(
            {
                "recipe_hash": result.recipe_hash,
                "output_dir": str(result.output_dir),
                "success": result.success,
                "exit_code": result.exit_code,
                "log_path": str(result.log_path),
                "artifacts_count": len(result.artifacts),
                "container_id": result.container_id,
            },
            sort_keys=True,
        )
    )

    return 0 if result.success or args.dry_run else result.exit_code


if __name__ == "__main__":
    sys.exit(main())
