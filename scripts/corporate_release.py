"""Corporate release jobs. Publishing runs only in a protected GitLab tag pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from corporate_config import apply_defaults
from launcher_catalog import CatalogError, update_catalog, validate_catalog
from publish_multiarch import RELEASE_IMAGES, TOOLBOX_IMAGES, require_new_tag
from release_plan import Plan, load_plan
from release_plan import check as check_release_plan

ROOT = Path(__file__).resolve().parents[1]
IMAGES = RELEASE_IMAGES + TOOLBOX_IMAGES


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Configure the corporate CI variable {name}.")
    return value


def catalog_url() -> str:
    """Return the public-in-corporate-network URL compiled into the launcher."""
    value = required("OSII_CATALOG_URL")
    parsed = urllib.parse.urlparse(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("OSII_CATALOG_URL must be a credential-free HTTPS URL.")
    return value


def catalog_project() -> str:
    """Return the separate GitLab project that owns the reviewed catalog."""
    value = required("OSII_CATALOG_PROJECT")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", value):
        raise ValueError("OSII_CATALOG_PROJECT must be a GitLab group/project path.")
    return value


def catalog_path() -> str:
    value = os.environ.get("OSII_CATALOG_PATH", "catalog.json").strip()
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError("OSII_CATALOG_PATH must be a relative file path in the catalog project.")
    return value


def catalog_target_branch() -> str:
    value = os.environ.get("OSII_CATALOG_TARGET_BRANCH", "main").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value) or ".." in value:
        raise ValueError("OSII_CATALOG_TARGET_BRANCH must be a valid Git branch name.")
    return value


def version() -> str:
    tag = os.environ.get("CI_COMMIT_TAG") or os.environ.get("GITHUB_REF_NAME", "")
    if not re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
        raise ValueError("Release tags must be vX.Y.Z, for example v0.1.0.")
    expected = tag[1:]
    plan = check_release_plan()
    if plan.version != expected:
        raise ValueError("The tag must match the prepared version in release.toml.")
    return expected


def run(*command: str, cwd: Path = ROOT, env: dict | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def preflight() -> str:
    release_version = version()
    if required("CI_COMMIT_REF_PROTECTED") != "true":
        raise ValueError("Corporate releases require a protected GitLab tag.")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Provision Python 3.12 on the release runner.")
    default_branch = required("CI_DEFAULT_BRANCH")
    remote_branch = f"refs/remotes/origin/{default_branch}"
    run("git", "fetch", "--no-tags", "origin",
        f"{default_branch}:{remote_branch}")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", required("CI_COMMIT_SHA"), remote_branch],
        cwd=ROOT,
        check=False,
    )
    if ancestry.returncode:
        raise ValueError("Release tags must point to a commit on the corporate default branch.")
    prefix = required("OSII_IMAGE_PREFIX")
    registry = required("OSII_QUAY_REGISTRY")
    if prefix != f"{registry}/ai-ready-everything/osii" or registry in ("quay.io", "localhost"):
        raise ValueError("OSII_IMAGE_PREFIX must be the approved corporate Quay prefix ending in /ai-ready-everything/osii.")
    catalog_url()
    if not re.search(r"@sha256:[0-9a-f]{64}$", required("OSII_BASE_IMAGE")):
        raise ValueError("OSII_BASE_IMAGE must be an approved RHEL/UBI digest reference.")
    for name in ("OSII_TESSERACT_SOURCE_URL", "OSII_LEPTONICA_SOURCE_URL", "OSII_TESSDATA_BASE_URL"):
        if not required(name).startswith("https://"):
            raise ValueError(f"{name} must use the approved HTTPS artifact mirror.")
    return release_version


def registry_login(directory: Path) -> None:
    # Dedicated, temporary auth file shared by Podman and skopeo in this job.
    os.environ["REGISTRY_AUTH_FILE"] = str(directory / "auth.json")
    subprocess.run(
        ["podman", "login", "--username", required("OSII_QUAY_USER"),
         "--password-stdin", required("OSII_QUAY_REGISTRY")],
        input=required("OSII_QUAY_PASSWORD") + "\n", text=True, check=True,
    )


def image_command(release_version: str, phase: str, architectures: str,
                  plan: Plan) -> list[str]:
    command = [
        sys.executable, "scripts/publish_multiarch.py",
        "--image-prefix", required("OSII_IMAGE_PREFIX"), "--image-tag", release_version,
        "--base-image", required("OSII_BASE_IMAGE"), "--python-version", "3.12",
        "--image-set", "all", "--phase", phase, "--platforms", architectures,
        "--require-new", "--include", *plan.images_to_build,
    ]
    if bundle := os.environ.get("OSII_CA_BUNDLE"):
        command.extend(("--ca-bundle", bundle))
    return command


def build_images() -> None:
    release_version = preflight()
    plan = load_plan()
    if not plan.images_to_build:
        print("No container images need rebuilding for this release.")
        return
    arch = required("OSII_ARCH")
    native = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    if platform.system() != "Linux" or arch != native:
        raise ValueError("Image jobs must run on native Linux runners matching OSII_ARCH.")
    with tempfile.TemporaryDirectory(prefix="osii-registry-") as directory:
        registry_login(Path(directory))
        run(*image_command(release_version, "build", f"linux/{arch}", plan))
        # Exercise installed entry points without exposing host ports or mounting user data.
        for name, _, _ in IMAGES:
            if name not in plan.images_to_build:
                continue
            image = f"{required('OSII_IMAGE_PREFIX')}-{name}:{release_version}-{arch}"
            if name == "dashboard":
                run("podman", "run", "--rm", "--entrypoint", "nginx", image, "-t")
            else:
                code = "import osii.processor_sdk"
                if name == "core":
                    code += "; import osii.main"
                run("podman", "run", "--rm", "--entrypoint", "python", image, "-c", code)


def build_installer() -> None:
    release_version = preflight()
    target = required("OSII_DESKTOP_TARGET")
    expected = {"windows-x64": ("Windows", "amd64"), "macos-arm64": ("Darwin", "arm64"),
                "macos-x64": ("Darwin", "x86_64")}
    if target not in expected or (platform.system(), platform.machine().lower()) != expected[target]:
        raise ValueError(f"Installer runner does not match {target}.")
    config: dict = {"version": release_version}
    if target == "windows-x64":
        config["bundle"] = {"windows": {
            "certificateThumbprint": required("OSII_WINDOWS_CERTIFICATE_THUMBPRINT"),
            "timestampUrl": required("OSII_WINDOWS_TIMESTAMP_URL"),
            "digestAlgorithm": "sha256",
        }}
        bundles = "nsis"
    else:
        for name in ("APPLE_SIGNING_IDENTITY", "APPLE_ID", "APPLE_PASSWORD", "APPLE_TEAM_ID"):
            required(name)
        bundles = "dmg"
    env = os.environ.copy()
    env.update({
        "VITE_OSII_REGISTRY": required("OSII_QUAY_REGISTRY"),
        "VITE_OSII_CATALOG_URL": catalog_url(),
        "VITE_OSII_IMAGE_PREFIX": required("OSII_IMAGE_PREFIX"),
        "VITE_OSII_IMAGE_TAG": release_version,
        "VITE_OSII_OPENAI_BASE_URL": os.environ.get("OSII_MODEL_BASE_URL", ""),
        "VITE_OSII_OPENAI_EMBEDDING_MODEL": os.environ.get("OSII_EMBEDDING_MODEL", ""),
        "VITE_OSII_OPENAI_CHAT_MODEL": os.environ.get("OSII_CHAT_MODEL", ""),
    })
    launcher = ROOT / "osii-launcher"
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run(npm, "ci", cwd=launcher, env=env)
    run(npm, "test", cwd=launcher, env=env)
    run(npm, "run", "tauri", "--", "build", "--bundles", bundles,
        "--config", json.dumps(config), cwd=launcher, env=env)
    bundle_directory = launcher / "src-tauri/target/release/bundle"
    suffix = ".exe" if target == "windows-x64" else ".dmg"
    candidates = list(bundle_directory.rglob("*" + suffix))
    if len(candidates) != 1:
        raise ValueError(f"Expected one {suffix} installer, found {len(candidates)}.")
    installer = candidates[0]
    if target == "windows-x64":
        literal = str(installer).replace("'", "''")
        run("powershell.exe", "-NoProfile", "-Command",
            f"if ((Get-AuthenticodeSignature -LiteralPath '{literal}').Status -ne 'Valid') {{ exit 1 }}")
    else:
        run("xcrun", "stapler", "validate", str(installer))
    output = ROOT / "release/installers"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(installer, output / f"OSII-{release_version}-{target}{suffix}")


def api_request(path: str, *, method: str = "GET", data: bytes | None = None,
                content_type: str = "application/json") -> bytes:
    url = f"{required('CI_API_V4_URL')}/projects/{required('CI_PROJECT_ID')}/{path}"
    request = urllib.request.Request(url, data=data, method=method, headers={
        "JOB-TOKEN": required("CI_JOB_TOKEN"), "Content-Type": content_type,
    })
    context = ssl.create_default_context(cafile=os.environ.get("OSII_CA_BUNDLE") or None)
    with urllib.request.urlopen(request, context=context, timeout=120) as response:
        return response.read()


def deployment_files(release_version: str) -> None:
    import yaml

    output = ROOT / "release"
    configuration = yaml.safe_load((ROOT / "compose.yaml").read_text())
    for service in configuration["services"].values():
        service.pop("build", None)
    defaults = {
        "OSII_IMAGE_PREFIX": required("OSII_IMAGE_PREFIX"),
        "OSII_IMAGE_TAG": release_version,
        "OSII_SOURCE_DIR": "./source",
        "OSII_DEFAULT_EXTRACTOR": "local.native-text",
        "OSII_DEFAULT_SYNTHESIZER": "local.basic-synthesizer",
        "OSII_DEFAULT_EMBEDDER": "local.hashing-embedder",
        "OSII_DEFAULT_ENRICHER": "local.stats-keywords",
        "OSII_MODEL_BASE_URL": os.environ.get("OSII_MODEL_BASE_URL", ""),
        "OPENAI_BASE_URL": os.environ.get("OSII_MODEL_BASE_URL", ""),
        "OPENAI_EMBEDDING_MODEL": os.environ.get("OSII_EMBEDDING_MODEL", ""),
        "OPENAI_CHAT_MODEL": os.environ.get("OSII_CHAT_MODEL", ""),
        "CHAT_PROVIDER": "extractive", "CHAT_PROVIDER_CHAIN": "extractive",
        "OSII_OLLAMA_ALLOWED_MODELS": "", "MCP_DEBUG": "false",
    }
    # Non-secret values only. JSON double quoting also protects spaces and newlines.
    env_text = "\n".join(f"{key}={json.dumps(value)}" for key, value in defaults.items()) + "\n"
    with zipfile.ZipFile(output / "deployment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("compose.yaml", yaml.safe_dump(configuration, sort_keys=False))
        archive.writestr(".env.example", env_text)
        archive.writestr("START-HERE.txt",
            "For Windows/macOS use the OSII installer on this release page.\n"
            "For managed Linux: copy .env.example to .env, set OSII_SOURCE_DIR, then\n"
            "podman compose pull\npodman compose up -d --no-build\n"
            "Open http://localhost:5173\n"
            "Optional tools: podman compose --profile toolbox up -d --no-build --pull missing "
            "tesseract-opencv tabular-extractor tabular-enricher "
            "readable-wiki-enricher concept-entity-wiki-enricher\n"
            "Register optional Processor API endpoints in dashboard Setup.\n")


def publish() -> None:
    release_version = preflight()
    plan = load_plan()
    tag = required("CI_COMMIT_TAG")
    try:
        api_request(f"releases/{urllib.parse.quote(tag, safe='')}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        raise ValueError("This GitLab release already exists. Use a new version.")
    output = ROOT / "release"
    wheels = list((output / "python").glob("*.whl"))
    distributions = list((output / "python").glob("*.tar.gz"))
    if plan.publish_package and (len(wheels) != 1 or len(distributions) != 1):
        raise ValueError("Missing tested Python release artifacts.")
    if not plan.publish_package and (wheels or distributions):
        raise ValueError("A non-Core release must not publish a new Python package.")
    for target, suffix in (("windows-x64", "exe"), ("macos-arm64", "dmg"), ("macos-x64", "dmg")):
        if not (output / "installers" / f"OSII-{release_version}-{target}.{suffix}").is_file():
            raise ValueError(f"Missing signed installer for {target}.")
    with tempfile.TemporaryDirectory(prefix="osii-registry-") as directory:
        registry_login(Path(directory))
        prefix = required("OSII_IMAGE_PREFIX")
        for name, _, _ in IMAGES:
            require_new_tag(f"{prefix}-{name}:{release_version}")
        reused = []
        for name, _, _ in IMAGES:
            if name in plan.images_to_build:
                continue
            source = f"{prefix}-{name}:{plan.previous_tag[1:]}"
            target = f"{prefix}-{name}:{release_version}"
            raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{source}"])
            _verified_platforms(raw, source)
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            reused.append((name, digest, target))
        if plan.images_to_build:
            run(*image_command(release_version, "manifest", "linux/amd64,linux/arm64", plan))
        for name, digest, target in reused:
            run("skopeo", "copy", "--all", "--preserve-digests",
                f"docker://{prefix}-{name}@{digest}",
                f"docker://{target}")
            copied = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{target}"])
            _verified_platforms(copied, target)
            if hashlib.sha256(copied).hexdigest() != digest.removeprefix("sha256:"):
                raise ValueError(f"Copied image does not match the prior release: {target}.")
        records = {}
        for name, _, _ in IMAGES:
            reference = f"{required('OSII_IMAGE_PREFIX')}-{name}:{release_version}"
            raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{reference}"])
            _verified_platforms(raw, reference)
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            records[reference] = digest
    (output / "images.json").write_text(json.dumps(records, indent=2) + "\n")
    (output / "python-package.json").write_text(json.dumps({
        "name": "osii", "version": plan.package_version,
        "published_in_this_release": plan.publish_package,
    }, indent=2) + "\n")
    deployment_files(release_version)
    if plan.publish_package:
        env = os.environ.copy()
        env.update(TWINE_USERNAME="gitlab-ci-token", TWINE_PASSWORD=required("CI_JOB_TOKEN"))
        run(sys.executable, "-m", "twine", "check", *map(str, [*wheels, *distributions]))
        run(sys.executable, "-m", "twine", "upload", "--non-interactive", "--repository-url",
            f"{required('CI_API_V4_URL')}/projects/{required('CI_PROJECT_ID')}/packages/pypi",
            *map(str, [*wheels, *distributions]), env=env)
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}\n"
        for path in files))
    links = []
    for path in [*files, output / "SHA256SUMS"]:
        relative = path.relative_to(output).as_posix()
        asset_name = relative.replace("/", "-")
        package_path = f"packages/generic/osii/{release_version}/{asset_name}"
        api_request(package_path, method="PUT", data=path.read_bytes(),
                    content_type="application/octet-stream")
        links.append({"name": relative, "url":
            f"{required('CI_API_V4_URL')}/projects/{required('CI_PROJECT_ID')}/{package_path}"})
    description = (
        f"OSII {release_version}\n\n"
        "Download the installer matching your computer below. IT must provision Podman Desktop, "
        "a Compose provider, corporate certificates, and Quay read access. Open OSII Launcher, "
        "choose your documents, test access, and start OSII. Registry and image version are prefilled.\n\n"
        "Optional Toolbox images: OpenCV/Tesseract and Tabular (enabled by an administrator).\n\n"
        f"Source: {required('CI_COMMIT_SHA')}\nPipeline: {required('CI_PIPELINE_URL')}\n\n"
        f"Python package: osii {plan.package_version}. "
        "Installation and image smoke checks passed. Complete the fresh-workstation intake/search "
        "acceptance test before distributing this version to users. Roll back by selecting a prior "
        "release in the launcher; back up library data before upgrades.\n"
    )
    api_request("releases", method="POST", data=json.dumps({
        "name": f"OSII {release_version}", "tag_name": tag,
        "description": description, "assets": {"links": links},
    }).encode())


def _release_image_digests(release_version: str) -> dict[str, str]:
    """Resolve only known release tags; never enumerate mutable registry tags."""
    prefix = required("OSII_IMAGE_PREFIX")
    records: dict[str, str] = {}
    for name, _, _ in IMAGES:
        reference = f"{prefix}-{name}:{release_version}"
        raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{reference}"])
        _verified_platforms(raw, reference)
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        pinned = f"{prefix}-{name}@{digest}"
        pinned_raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{pinned}"])
        _verified_platforms(pinned_raw, pinned)
        if hashlib.sha256(pinned_raw).hexdigest() != digest.removeprefix("sha256:"):
            raise ValueError(f"Digest verification did not round-trip for {reference}.")
        records[name] = digest
    return records


def _verify_catalog_digest(reference: str) -> None:
    raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{reference}"])
    _verified_platforms(raw, reference)
    expected = reference.rsplit("@", 1)[1]
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"Quay returned a different digest for {reference}.")


def _catalog_api_request(project: str, path: str, *, data: bytes) -> bytes:
    url = f"{required('CI_API_V4_URL')}/projects/{urllib.parse.quote(project, safe='')}/{path}"
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "JOB-TOKEN": required("CI_JOB_TOKEN"), "Content-Type": "application/json",
    })
    context = ssl.create_default_context(cafile=os.environ.get("OSII_CA_BUNDLE") or None)
    with urllib.request.urlopen(request, context=context, timeout=120) as response:
        return response.read()


def _catalog_git_environment(directory: Path) -> dict[str, str]:
    """Give Git a temporary Job Token credential without putting it in a command line."""
    host = required("CI_SERVER_HOST")
    credential = directory / "git-credentials"
    token = urllib.parse.quote(required("CI_JOB_TOKEN"), safe="")
    credential.write_text(f"https://gitlab-ci-token:{token}@{host}\n", encoding="utf-8")
    credential.chmod(0o600)
    environment = os.environ.copy()
    environment.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": f"store --file={credential}",
    })
    return environment


def _run_catalog_git(*command: str, cwd: Path | None, environment: dict[str, str]) -> None:
    subprocess.run(["git", *command], cwd=cwd, env=environment, check=True)


def update_launcher_catalog() -> None:
    """Open a reviewed catalog merge request after a successful protected release."""
    release_version = preflight()
    plan = load_plan()
    project = catalog_project()
    target_branch = catalog_target_branch()
    path = catalog_path()
    branch = f"release/osii-catalog-v{release_version}"
    with tempfile.TemporaryDirectory(prefix="osii-catalog-") as directory:
        temporary = Path(directory)
        registry_login(temporary)
        digests = _release_image_digests(release_version)
        checkout = temporary / "catalog"
        environment = _catalog_git_environment(temporary)
        clone_url = f"https://{required('CI_SERVER_HOST')}/{project}.git"
        _run_catalog_git("clone", "--branch", target_branch, "--single-branch", clone_url, str(checkout),
                         cwd=None, environment=environment)
        _run_catalog_git("switch", "--create", branch, cwd=checkout, environment=environment)
        catalog_file = checkout / path
        try:
            catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            catalog = {
                "version": 1,
                "registry": required("OSII_QUAY_REGISTRY"),
                "namespace": "ai-ready-everything",
                "stacks": [],
                "tools": [],
                "images": [],
            }
        except json.JSONDecodeError as error:
            raise ValueError(f"{path} is not valid JSON: {error}.") from error
        registry = required("OSII_QUAY_REGISTRY")
        try:
            validate_catalog(catalog, registry=registry, verify_digest=_verify_catalog_digest,
                             allow_empty_stacks=True)
            updated = update_catalog(
                catalog, release=release_version, image_digests=digests,
                published_images=plan.images_to_build,
            )
            validate_catalog(updated, registry=registry, verify_digest=_verify_catalog_digest)
        except CatalogError as error:
            raise ValueError(str(error)) from error
        catalog_file.parent.mkdir(parents=True, exist_ok=True)
        catalog_file.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        changed = subprocess.run(["git", "diff", "--quiet", "--", path], cwd=checkout,
                                 env=environment, check=False).returncode != 0
        if not changed:
            print("Catalog already contains this release; no merge request opened.")
            return
        _run_catalog_git("config", "user.name", "OSII Release Bot", cwd=checkout, environment=environment)
        _run_catalog_git("config", "user.email", "osii-release-bot@invalid", cwd=checkout, environment=environment)
        _run_catalog_git("add", "--", path, cwd=checkout, environment=environment)
        _run_catalog_git("commit", "-m", f"release: add OSII {release_version} catalog", cwd=checkout,
                         environment=environment)
        _run_catalog_git("push", "origin", branch, cwd=checkout, environment=environment)
    mapping = "\n".join(
        f"| osii-{name} | `{required('OSII_QUAY_REGISTRY')}/ai-ready-everything/osii-{name}@{digest}` |"
        for name, digest in sorted(digests.items())
    )
    description = (
        f"## OSII {release_version} approved-image catalog\n\n"
        f"Release tag: `{required('CI_COMMIT_TAG')}`\n\n"
        "| Image | Immutable Quay reference |\n| --- | --- |\n"
        f"{mapping}\n\n"
        "Validation passed:\n"
        "- `catalog.json` parses as JSON and keeps catalog version 1.\n"
        "- every reference uses the configured corporate registry, `ai-ready-everything/osii-*`, "
        "and a lowercase SHA-256 digest; no tags or credentials are present.\n"
        "- every Stack has core, dashboard, and baselineProcessors from this release.\n"
        "- every catalog digest was inspected in Quay and verified as an AMD64/ARM64 manifest.\n"
    )
    response = _catalog_api_request(project, "merge_requests", data=json.dumps({
        "source_branch": branch,
        "target_branch": target_branch,
        "title": f"release: add OSII {release_version} catalog",
        "description": description,
        "remove_source_branch": True,
    }).encode())
    merge_request = json.loads(response)
    print(f"Opened catalog merge request: {merge_request.get('web_url', branch)}")


def promote_latest() -> None:
    release_version = preflight()
    tag = required("CI_COMMIT_TAG")
    api_request(f"releases/{urllib.parse.quote(tag, safe='')}")
    with tempfile.TemporaryDirectory(prefix="osii-registry-") as directory:
        registry_login(Path(directory))
        prefix = required("OSII_IMAGE_PREFIX")
        sources = []
        for name, _, _ in IMAGES:
            source = f"{prefix}-{name}:{release_version}"
            raw = subprocess.check_output(["skopeo", "inspect", "--raw", f"docker://{source}"])
            _verified_platforms(raw, source)
            sources.append((name, "sha256:" + hashlib.sha256(raw).hexdigest()))
        for name, digest in sources:
            reference = f"{prefix}-{name}"
            run("skopeo", "copy", "--all", "--preserve-digests",
                f"docker://{reference}@{digest}",
                f"docker://{reference}:latest")
            current = subprocess.check_output(
                ["skopeo", "inspect", "--raw", f"docker://{reference}:latest"])
            _verified_platforms(current, f"{reference}:latest")
            if hashlib.sha256(current).hexdigest() != digest.removeprefix("sha256:"):
                raise ValueError(f"latest does not match tested release for {name}.")


def _verified_platforms(raw: bytes, reference: str) -> None:
    manifest = json.loads(raw)
    platforms = {(item["platform"]["os"], item["platform"]["architecture"])
                 for item in manifest.get("manifests", [])}
    if platforms != {("linux", "amd64"), ("linux", "arm64")}:
        raise ValueError(f"Incomplete multi-architecture image: {reference}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("version", "preflight", "images", "installer", "publish", "catalog", "promote-latest"),
    )
    args = parser.parse_args()
    apply_defaults()
    actions = {"version": version, "preflight": preflight, "images": build_images,
               "installer": build_installer, "publish": publish,
               "catalog": update_launcher_catalog, "promote-latest": promote_latest}
    result = actions[args.action]()
    if result:
        print(result)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, urllib.error.HTTPError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
