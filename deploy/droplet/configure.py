"""Configure the single Ubuntu demo host. Run explicitly as root after building images.

Does not migrate the database, create OSII accounts, or enqueue ingestion.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def write(path, content, mode=0o644):
    path = Path(path)
    path.write_text(content)
    path.chmod(mode)


def sql(statement):
    return subprocess.check_output(["runuser", "-u", "postgres", "--", "psql", "-XAt", "-v", "ON_ERROR_STOP=1"], input=statement, text=True).strip()


def dashboard_proxy_configuration(source: Path) -> str:
    """Resolve the replaceable API container through the private Podman DNS."""
    template = (source / "deploy/openshift/nginx.conf").read_text()
    upstream = "proxy_pass http://osii-api:8512;"
    if template.count("http {\n") != 1 or template.count(upstream) != 1:
        raise ValueError("Unexpected dashboard proxy template; review before configuring")
    return template.replace("http {\n", "http {\n  resolver 10.89.0.1 valid=5s ipv6=off;\n  resolver_timeout 2s;\n", 1).replace(
        upstream,
        "set $osii_api http://osii-api:8512;\n      proxy_pass $osii_api$request_uri;\n      proxy_connect_timeout 5s;",
        1,
    )


def configure_backup():
    Path("/var/backups/osii").mkdir(mode=0o700, exist_ok=True)
    write("/usr/local/sbin/osii-backup", "#!/bin/sh\nset -eu\numask 077\nbackup=/var/backups/osii/osii-$(date -u +%Y%m%dT%H%M%SZ).dump\ntrap 'rm -f \"$backup.partial\"' EXIT\nrunuser -u postgres -- pg_dump --format=custom osii_server > \"$backup.partial\"\nmv \"$backup.partial\" \"$backup\"\nfind /var/backups/osii -maxdepth 1 -type f -name 'osii-*.dump' -mtime +7 -delete\n", 0o700)
    write("/etc/systemd/system/osii-backup.service", "[Unit]\nDescription=Local OSII PostgreSQL backup\nAfter=postgresql@16-main.service\nRequires=postgresql@16-main.service\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/osii-backup\nTimeoutStartSec=900\n")
    write("/etc/systemd/system/osii-backup.timer", "[Unit]\nDescription=Daily OSII database backup\n\n[Timer]\nOnCalendar=daily\nPersistent=true\nRandomizedDelaySec=300\n\n[Install]\nWantedBy=timers.target\n")


def configure_ocr(source: Path, release_tag: str, bind_address: str = "10.89.0.1"):
    """Explicit optional native services; no NFS/database access or Core deps."""
    import pwd
    import ipaddress
    import re

    ipaddress.ip_address(bind_address)
    if not re.fullmatch(r"[a-z0-9-]+", release_tag):
        raise ValueError("Use an immutable release tag")
    run("apt-get", "update", "-qq")
    run(
        "apt-get",
        "install",
        "-y",
        "tesseract-ocr",
        "tesseract-ocr-eng",
        "python3.12-venv",
    )
    try:
        pwd.getpwnam("osii-ocr")
    except KeyError:
        run(
            "useradd",
            "--system",
            "--no-create-home",
            "--shell",
            "/usr/sbin/nologin",
            "osii-ocr",
        )
    environment = Path("/opt/osii/tools") / ("ocr-" + release_tag)
    run("python3.12", "-m", "venv", str(environment))
    python = environment / "bin/python"
    run(
        str(python),
        "-m",
        "pip",
        "install",
        "--require-hashes",
        "-r",
        str(source / "osii-processor-modules/osii-tesseract/requirements-host.lock.txt"),
    )
    for name, directory, port in [
        ("osii-ocr-page", "osii-core/services/local-tesseract", 8193),
        ("osii-ocr-regions", "osii-processor-modules/osii-tesseract", 8194),
    ]:
        write(
            "/etc/systemd/system/" + name + ".service",
            f"""[Unit]
Description=Optional OSII native OCR service
After=osii-api.service
Wants=osii-api.service
[Service]
User=osii-ocr
Group=osii-ocr
WorkingDirectory={source / directory}
Environment=PYTHONPATH={source / "osii-core"}
Environment=ENABLE_DEMO=false
Environment=OMP_THREAD_LIMIT=1
Environment=OPENBLAS_NUM_THREADS=1
ExecStart={python} -m uvicorn app.main:app --app-dir {source / directory} --host {bind_address} --port {port}
Restart=on-failure
RestartSec=5
MemoryMax=1G
CPUQuota=100%
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
InaccessiblePaths=/etc/osii /mnt/nfs-documents /var/run/postgresql
[Install]
WantedBy=multi-user.target
""",
        )
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "osii-ocr-page", "osii-ocr-regions")
    run("systemctl", "restart", "osii-ocr-page", "osii-ocr-regions")


def configure_tool_control(source: Path):
    """Explicitly install the socket-only, fixed-unit tool controller."""
    import shutil
    destination = Path("/opt/osii/tool-supervisor.py")
    shutil.copyfile(source / "deploy/droplet/tool_supervisor.py", destination)
    destination.chmod(0o700)
    write("/etc/systemd/system/osii-tool-controller.service", """[Unit]
Description=OSII private tool lifecycle controller
After=network.target
[Service]
ExecStart=/usr/bin/python3 /opt/osii/tool-supervisor.py
RuntimeDirectory=osii-tools
RuntimeDirectoryMode=0750
RuntimeDirectoryPreserve=yes
UMask=0077
Restart=on-failure
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateNetwork=yes
RestrictAddressFamilies=AF_UNIX
InaccessiblePaths=/etc/osii /mnt/nfs-documents /var/run/postgresql
[Install]
WantedBy=multi-user.target
""")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "osii-tool-controller")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--with-ocr", action="store_true", help="Explicitly install optional native OCR services")
    parser.add_argument("--with-tool-control", action="store_true", help="Enable admin lifecycle controls for the fixed deployed tool units")
    args = parser.parse_args()
    import re
    if not re.fullmatch(r"[a-z0-9.-]+", args.hostname) or not re.fullmatch(r"[a-z0-9-]+", args.image_tag):
        parser.error("Use a DNS hostname and a simple immutable release tag")
    if os.geteuid() != 0:
        parser.error("Run this explicit deployment configuration as root on the demo host")
    config = Path("/etc/osii")
    config.mkdir(mode=0o700, exist_ok=True)
    config.chmod(0o700)
    if not (config / "model-key").is_file():
        parser.error("Install the private provider key at /etc/osii/model-key first")
    (config / "model-key").chmod(0o440)
    (config / "keys").mkdir(mode=0o750, exist_ok=True)
    (config / "keys").chmod(0o750)
    network = subprocess.run(["podman", "network", "exists", "osii"], check=False)
    if network.returncode:
        run("podman", "network", "create", "--subnet", "10.89.0.0/24", "--gateway", "10.89.0.1", "osii")
    else:
        import json
        existing = json.loads(subprocess.check_output(["podman", "network", "inspect", "osii"]))[0]
        if not any(s["subnet"] == "10.89.0.0/24" and s["gateway"] == "10.89.0.1" for s in existing["subnets"]):
            parser.error("Existing osii network differs; left unchanged")
    # Only API/worker get the PostgreSQL socket; the database has no public port.
    write("/etc/postgresql/16/main/conf.d/osii.conf", "listen_addresses = '127.0.0.1'\npassword_encryption = 'scram-sha-256'\n")
    hba = Path("/etc/postgresql/16/main/pg_hba.conf")
    rule = "local osii_server osii scram-sha-256"
    if rule not in hba.read_text().splitlines():
        write(hba, rule + "\n" + hba.read_text(), 0o640)
    write("/etc/systemd/system/osii-network.service", "[Unit]\nDescription=OSII container network\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/podman network exists osii\n\n[Install]\nWantedBy=multi-user.target\n")
    run("systemctl", "restart", "postgresql@16-main")
    password_file = config / "database.password"
    if not password_file.exists():
        if sql("SELECT 1 FROM pg_roles WHERE rolname='osii';"):
            parser.error("Existing osii database role has no managed password file; left unchanged")
        write(password_file, secrets.token_urlsafe(32), 0o600)
    password = password_file.read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", password):
        parser.error("Unexpected password file format")
    if not sql("SELECT 1 FROM pg_roles WHERE rolname='osii';"):
        sql(f"CREATE ROLE osii LOGIN PASSWORD '{password}';")
    if not sql("SELECT 1 FROM pg_database WHERE datname='osii_server';"):
        sql("CREATE DATABASE osii_server OWNER osii;")
    if not (config / "runtime.env").exists():
        write(config / "runtime.env", f"DATABASE_URL=postgresql+psycopg://osii:{password}@/osii_server?host=/var/run/postgresql\nOSII_SOURCE_DIR=/data/source\nOPENAI_BASE_URL=https://openrouter.ai/api/v1\nOSII_MODEL_API_KEY_FILE=/run/osii-model-key\nOSII_ORIGINS=https://{args.hostname}\nOSII_EXTRACTOR_URL=http://osii-extractor:8192\nOSII_PROCESSOR_GATEWAY_URL=http://osii-api:8512/api/processor-model/v1\n", 0o600)
    write(config / "dashboard-nginx.conf", dashboard_proxy_configuration(Path(__file__).resolve().parents[2]))
    if args.with_tool_control:
        configure_tool_control(Path(__file__).resolve().parents[2])
    for component, memory in [("api", "1g"), ("worker", "1g"), ("extractor", "768m"), ("dashboard", "128m")]:
        image = f"localhost/osii-{'dashboard' if component == 'dashboard' else 'core'}:{args.image_tag}"
        command = f"/usr/bin/podman run --rm --name osii-{component} --network osii --read-only --cap-drop ALL --security-opt no-new-privileges --user 1001:0 --tmpfs /tmp:rw,nosuid,nodev,size=256m --memory {memory}"
        dependencies = ""
        if component in {"api", "worker"}:
            dependencies = "Wants=postgresql@16-main.service\nAfter=postgresql@16-main.service\nRequiresMountsFor=/mnt/nfs-documents\n"
            command += " --env-file /etc/osii/runtime.env --volume /var/run/postgresql:/var/run/postgresql:ro --volume /etc/osii/model-key:/run/osii-model-key:ro --volume /etc/osii/keys:/run/osii-keys:ro --volume /mnt/nfs-documents:/data/source:ro"
        if component == "api" and Path("/etc/systemd/system/osii-tool-controller.service").exists():
            dependencies += "Wants=osii-tool-controller.service\nAfter=osii-tool-controller.service\n"
            command += " --env OSII_TOOL_CONTROL_SOCKET=/run/osii-tools/control.sock --volume /run/osii-tools:/run/osii-tools:ro"
        if component == "dashboard":
            dependencies = "Wants=osii-api.service\nAfter=osii-api.service\n"
            command += " --publish 127.0.0.1:18080:8080 --volume /etc/osii/dashboard-nginx.conf:/etc/nginx/nginx.conf:ro"
        command += " " + image
        if component == "worker":
            command += " python3.12 -m osii.server.worker"
        if component == "extractor":
            command += " python3.12 -m uvicorn app.main:app --app-dir /app/osii-core/services/local-extractor --host 0.0.0.0 --port 8192"
        check_mount = "ExecStartPre=/usr/bin/findmnt -rn -M /mnt/nfs-documents -t nfs,nfs4\n" if component in {"api", "worker"} else ""
        write(f"/etc/systemd/system/osii-{component}.service", f"[Unit]\nDescription=OSII {component}\nAfter=network-online.target osii-network.service\nWants=network-online.target\nRequires=osii-network.service\n{dependencies}StartLimitIntervalSec=0\n\n[Service]\nRestart=always\nRestartSec=5\nTimeoutStartSec=120\nTimeoutStopSec=45\n{check_mount}ExecStartPre=-/usr/bin/podman rm -f osii-{component}\nExecStart={command}\nExecStop=/usr/bin/podman stop --time 20 osii-{component}\n\n[Install]\nWantedBy=multi-user.target\n")
    write("/etc/caddy/Caddyfile", f"{args.hostname} {{\n    reverse_proxy 127.0.0.1:18080\n}}\n")
    if args.with_ocr:
        configure_ocr(Path(__file__).resolve().parents[2], args.image_tag)
    configure_backup()
    run("caddy", "validate", "--config", "/etc/caddy/Caddyfile")
    run("systemctl", "daemon-reload")
    print("Configured. Run the explicit migration, then enable/start OSII services and Caddy. No ingestion or account bootstrap was performed.")


if __name__ == "__main__":
    main()
