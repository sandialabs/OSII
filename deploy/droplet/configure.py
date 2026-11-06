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


def configure_backup():
    Path("/var/backups/osii").mkdir(mode=0o700, exist_ok=True)
    write("/usr/local/sbin/osii-backup", "#!/bin/sh\nset -eu\numask 077\nbackup=/var/backups/osii/osii-$(date -u +%Y%m%dT%H%M%SZ).dump\ntrap 'rm -f \"$backup.partial\"' EXIT\nrunuser -u postgres -- pg_dump --format=custom osii_server > \"$backup.partial\"\nmv \"$backup.partial\" \"$backup\"\nfind /var/backups/osii -maxdepth 1 -type f -name 'osii-*.dump' -mtime +7 -delete\n", 0o700)
    write("/etc/systemd/system/osii-backup.service", "[Unit]\nDescription=Local OSII PostgreSQL backup\nAfter=postgresql@16-main.service\nRequires=postgresql@16-main.service\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/osii-backup\nTimeoutStartSec=900\n")
    write("/etc/systemd/system/osii-backup.timer", "[Unit]\nDescription=Daily OSII database backup\n\n[Timer]\nOnCalendar=daily\nPersistent=true\nRandomizedDelaySec=300\n\n[Install]\nWantedBy=timers.target\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--image-tag", required=True)
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
        write(config / "runtime.env", f"DATABASE_URL=postgresql+psycopg://osii:{password}@/osii_server?host=/var/run/postgresql\nOSII_SOURCE_DIR=/data/source\nOPENAI_BASE_URL=https://openrouter.ai/api/v1\nOSII_MODEL_API_KEY_FILE=/run/osii-model-key\nOSII_ORIGINS=https://{args.hostname}\nOSII_EXTRACTOR_URL=http://osii-extractor:8192\n", 0o600)
    for component, memory in [("api", "1g"), ("worker", "1g"), ("extractor", "768m"), ("dashboard", "128m")]:
        image = f"localhost/osii-{'dashboard' if component == 'dashboard' else 'core'}:{args.image_tag}"
        command = f"/usr/bin/podman run --rm --name osii-{component} --network osii --read-only --cap-drop ALL --security-opt no-new-privileges --user 1001:0 --tmpfs /tmp:rw,nosuid,nodev,size=256m --memory {memory}"
        dependencies = ""
        if component in {"api", "worker"}:
            dependencies = "Wants=postgresql@16-main.service\nAfter=postgresql@16-main.service\nRequiresMountsFor=/mnt/nfs-documents\n"
            command += " --env-file /etc/osii/runtime.env --volume /var/run/postgresql:/var/run/postgresql:ro --volume /etc/osii/model-key:/run/osii-model-key:ro --volume /etc/osii/keys:/run/osii-keys:ro --volume /mnt/nfs-documents:/data/source:ro"
        if component == "dashboard":
            dependencies = "Wants=osii-api.service\nAfter=osii-api.service\n"
            command += " --publish 127.0.0.1:18080:8080"
        command += " " + image
        if component == "worker":
            command += " python3.12 -m osii.server.worker"
        if component == "extractor":
            command += " python3.12 -m uvicorn app.main:app --app-dir /app/osii-core/services/local-extractor --host 0.0.0.0 --port 8192"
        check_mount = "ExecStartPre=/usr/bin/findmnt -rn -M /mnt/nfs-documents -t nfs,nfs4\n" if component in {"api", "worker"} else ""
        write(f"/etc/systemd/system/osii-{component}.service", f"[Unit]\nDescription=OSII {component}\nAfter=network-online.target osii-network.service\nWants=network-online.target\nRequires=osii-network.service\n{dependencies}StartLimitIntervalSec=0\n\n[Service]\nRestart=always\nRestartSec=5\nTimeoutStartSec=120\nTimeoutStopSec=45\n{check_mount}ExecStartPre=-/usr/bin/podman rm -f osii-{component}\nExecStart={command}\nExecStop=/usr/bin/podman stop --time 20 osii-{component}\n\n[Install]\nWantedBy=multi-user.target\n")
    write("/etc/caddy/Caddyfile", f"{args.hostname} {{\n    reverse_proxy 127.0.0.1:18080\n}}\n")
    configure_backup()
    run("caddy", "validate", "--config", "/etc/caddy/Caddyfile")
    run("systemctl", "daemon-reload")
    print("Configured. Run the explicit migration, then enable/start OSII services and Caddy. No ingestion or account bootstrap was performed.")


if __name__ == "__main__":
    main()
