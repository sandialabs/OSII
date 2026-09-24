"""Prepare and verify one immutable OSII stack release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "release.toml"
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
SCOPES = (
    "full", "core", "ui", "launcher", "toolbox-tesseract-opencv",
    "toolbox-tabular", "toolbox-llm-wikis",
)
IMAGES = (
    "core", "dashboard", "baseline-processors", "tesseract-opencv", "tabular", "llm-wikis",
)
PYTHON_IMAGES = tuple(name for name in IMAGES if name != "dashboard")
TOOLBOX_IMAGE = {
    "toolbox-tesseract-opencv": "tesseract-opencv",
    "toolbox-tabular": "tabular",
    "toolbox-llm-wikis": "llm-wikis",
}


@dataclass(frozen=True)
class Plan:
    version: str
    previous_tag: str
    scope: str
    package_version: str

    @property
    def images_to_build(self) -> tuple[str, ...]:
        if self.scope == "full":
            return IMAGES
        if self.scope == "core":
            return PYTHON_IMAGES
        if self.scope == "ui":
            return ("dashboard",)
        if self.scope in TOOLBOX_IMAGE:
            return (TOOLBOX_IMAGE[self.scope],)
        return ()

    @property
    def publish_package(self) -> bool:
        return self.scope in {"full", "core"}


def _version(value: str) -> str:
    if not VERSION.fullmatch(value):
        raise ValueError(f"Use an X.Y.Z version, not {value!r}.")
    return value


def load_plan(path: Path = PLAN_FILE) -> Plan:
    record = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(record) != {"version", "previous_tag", "scope", "package_version"}:
        raise ValueError("release.toml must contain only version, previous_tag, scope, and package_version.")
    version = _version(record["version"])
    package_version = _version(record["package_version"])
    previous = record["previous_tag"]
    if previous and (not previous.startswith("v") or not VERSION.fullmatch(previous[1:])):
        raise ValueError("previous_tag must be an immutable vX.Y.Z tag.")
    scope = record["scope"]
    if scope not in SCOPES:
        raise ValueError(f"Unknown release scope {scope!r}.")
    if not previous and scope != "full":
        raise ValueError("The first release must be full.")
    if scope in {"full", "core"} and package_version != version:
        raise ValueError("A Core/full release must publish a package matching the stack version.")
    return Plan(version, previous, scope, package_version)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _project_version(path: str) -> str:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))["project"]["version"]


def _previous_package_version(tag: str) -> str:
    source = _git("show", f"{tag}:osii-core/pyproject.toml")
    return tomllib.loads(source)["project"]["version"]


def _build_defaults_changed(tag: str) -> bool:
    private = ROOT / "corporate/osii.toml"
    if not private.is_file():
        return False
    current = tomllib.loads(private.read_text(encoding="utf-8"))["defaults"]
    try:
        previous = tomllib.loads(_git("show", f"{tag}:corporate/osii.toml"))["defaults"]
    except subprocess.CalledProcessError:
        return True
    build_inputs = {
        "OSII_BASE_IMAGE", "OSII_TESSERACT_SOURCE_URL",
        "OSII_LEPTONICA_SOURCE_URL", "OSII_TESSDATA_BASE_URL", "OSII_CA_BUNDLE",
    }
    return any(current.get(name) != previous.get(name) for name in build_inputs)


def classify(path: str) -> str:
    if path == "release.toml" or path.startswith("docs/") or path.endswith(".md"):
        return "neutral"
    if path.startswith((".github/", ".gitlab/", "corporate/")) or path == "mkdocs.yml":
        return "neutral"
    if path.startswith("osii-core/") or path == "uv.lock" or path == "pyproject.toml":
        return "core"
    if path.startswith("osii-dashboard/"):
        return "ui"
    if path.startswith("osii-launcher/"):
        return "launcher"
    for directory, scope in (
        ("osii-toolbox/osii-tesseract/", "toolbox-tesseract-opencv"),
        ("osii-toolbox/tabular-dataset-processors/", "toolbox-tabular"),
        ("osii-toolbox/llm-wiki-enrichers/", "toolbox-llm-wikis"),
    ):
        if path.startswith(directory):
            return scope
    if path in {"compose.yaml", "Makefile", ".gitlab-ci.yml"} or path.startswith("scripts/"):
        return "full"
    return "unknown"


def check_scope(plan: Plan, changed: list[str]) -> None:
    if plan.scope == "full":
        return
    allowed = {"core": {"core", "launcher"},
               "ui": {"ui", "launcher"}, "launcher": {"launcher"}}.get(
                   plan.scope, {plan.scope, "launcher"})
    unexpected = sorted(path for path in changed
                        if (category := classify(path)) != "neutral" and category not in allowed)
    if unexpected:
        shown = ", ".join(unexpected[:10])
        remainder = f" (and {len(unexpected) - 10} more)" if len(unexpected) > 10 else ""
        raise ValueError(f"Changes exceed release scope: {shown}{remainder}. Choose 'full' "
                         "or review the diff from the previous release tag.")


def check(plan: Plan | None = None, *, compare: bool = True) -> Plan:
    plan = plan or load_plan()
    if _project_version("osii-core/pyproject.toml") != plan.package_version:
        raise ValueError("osii-core/pyproject.toml does not match release.toml package_version.")
    for path in ("osii-launcher/package.json", "osii-launcher/src-tauri/tauri.conf.json"):
        if json.loads((ROOT / path).read_text(encoding="utf-8"))["version"] != plan.version:
            raise ValueError(f"{path} must match the stack version.")
    cargo = tomllib.loads((ROOT / "osii-launcher/src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    if cargo["package"]["version"] != plan.version:
        raise ValueError("Launcher Cargo.toml must match the stack version.")
    package_lock = json.loads((ROOT / "osii-launcher/package-lock.json").read_text(encoding="utf-8"))
    if (package_lock["version"] != plan.version or
            package_lock["packages"][""]["version"] != plan.version):
        raise ValueError("Launcher package-lock.json must match the stack version.")
    cargo_lock = (ROOT / "osii-launcher/src-tauri/Cargo.lock").read_text(encoding="utf-8")
    if not re.search(rf'name = "osii-launcher"\nversion = "{re.escape(plan.version)}"', cargo_lock):
        raise ValueError("Launcher Cargo.lock must match the stack version.")
    lock = ROOT / "uv.lock"
    if lock.exists():
        packages = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
        if next(item["version"] for item in packages if item["name"] == "osii") != plan.package_version:
            raise ValueError("uv.lock must match the osii package version.")
    if plan.previous_tag:
        _git("rev-parse", "--verify", f"{plan.previous_tag}^{{commit}}")
        subprocess.run(["git", "merge-base", "--is-ancestor", plan.previous_tag, "HEAD"],
                       cwd=ROOT, check=True)
        if plan.scope != "full" and _build_defaults_changed(plan.previous_tag):
            raise ValueError("Approved base, mirror, or CA changes require a full release.")
        if not plan.publish_package and _previous_package_version(plan.previous_tag) != plan.package_version:
            raise ValueError("A non-Core release must reuse the prior Python package version.")
        if compare:
            changed = _git("diff", "--name-only", f"{plan.previous_tag}..HEAD").splitlines()
            check_scope(plan, changed)
    return plan


def _updated_version(path: Path, old: str, new: str) -> str:
    content = path.read_text(encoding="utf-8")
    if path.name == "Cargo.lock":
        pattern = rf'(name = "osii-launcher"\nversion = "){re.escape(old)}(")'
    elif path.name == "Cargo.toml" or path.name == "pyproject.toml":
        pattern = rf'(^version = "){re.escape(old)}(")'
    else:
        pattern = rf'("version": "){re.escape(old)}(")'
    expected = 2 if path.name == "package-lock.json" else 1
    updated, count = re.subn(pattern, rf'\g<1>{new}\g<2>', content,
                             count=expected, flags=re.MULTILINE)
    if count != expected:
        raise ValueError(f"Expected old version {old} in {path}.")
    return updated


def prepare(version: str, scope: str, previous_tag: str, *, dry_run: bool = False) -> Plan:
    version = _version(version)
    if scope not in SCOPES:
        raise ValueError(f"Choose a scope from: {', '.join(SCOPES)}")
    prior = load_plan()
    if tuple(map(int, version.split("."))) <= tuple(map(int, prior.version.split("."))):
        raise ValueError("The new stack version must be greater than the previous version.")
    if not previous_tag:
        if scope != "full":
            raise ValueError("The first release must be full.")
    elif previous_tag != f"v{prior.version}":
        raise ValueError("The prior release plan must match --previous-tag.")
    if previous_tag:
        _git("rev-parse", "--verify", f"{previous_tag}^{{commit}}")
        subprocess.run(["git", "merge-base", "--is-ancestor", previous_tag, "HEAD"],
                       cwd=ROOT, check=True)
        if scope != "full" and _build_defaults_changed(previous_tag):
            raise ValueError("Approved base, mirror, or CA changes require a full release.")
        check_scope(Plan(version, previous_tag, scope, prior.package_version),
                    _git("diff", "--name-only", f"{previous_tag}..HEAD").splitlines())
    package_version = version if scope in {"full", "core"} else prior.package_version
    plan = Plan(version, previous_tag, scope, package_version)
    paths = [
        ROOT / "osii-launcher/package.json",
        ROOT / "osii-launcher/package-lock.json",
        ROOT / "osii-launcher/src-tauri/Cargo.toml",
        ROOT / "osii-launcher/src-tauri/Cargo.lock",
        ROOT / "osii-launcher/src-tauri/tauri.conf.json",
    ]
    if plan.publish_package:
        paths.append(ROOT / "osii-core/pyproject.toml")
    updated = {
        path: _updated_version(path, prior.version if path.name != "pyproject.toml"
                               else prior.package_version, version)
        for path in paths
    }
    lock = ROOT / "uv.lock"
    if plan.publish_package and lock.exists():
        updated_lock, count = re.subn(
            rf'(name = "osii"\nversion = "){re.escape(prior.package_version)}(")',
            rf'\g<1>{version}\g<2>', lock.read_text(encoding="utf-8"), count=1,
        )
        if count != 1:
            raise ValueError("uv.lock does not contain the previous osii package version.")
        updated[lock] = updated_lock
    if dry_run:
        return plan
    for path, content in updated.items():
        path.write_text(content, encoding="utf-8")
    PLAN_FILE.write_text(
        f'version = "{version}"\nprevious_tag = "{previous_tag}"\n'
        f'scope = "{scope}"\npackage_version = "{package_version}"\n',
        encoding="utf-8",
    )
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    commands.add_parser("needs-package")
    prepared = commands.add_parser("prepare")
    prepared.add_argument("--version", required=True)
    prepared.add_argument("--scope", required=True, choices=SCOPES)
    prepared.add_argument("--previous-tag", required=True)
    prepared.add_argument("--dry-run", action="store_true", help="Validate and show work without editing files")
    args = parser.parse_args()
    plan = (check() if args.command in {"check", "needs-package"} else prepare(
        args.version, args.scope, args.previous_tag, dry_run=args.dry_run))
    if args.command == "needs-package":
        raise SystemExit(0 if plan.publish_package else 1)
    print(f"OSII {plan.version}: {plan.scope}; build {', '.join(plan.images_to_build) or 'no images'}; "
          f"{'publish' if plan.publish_package else 'reuse'} Python package {plan.package_version}.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
