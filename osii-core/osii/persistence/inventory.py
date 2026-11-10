"""PostgreSQL adapter for hosted metadata observations and immutable batches."""

from __future__ import annotations
import json
from pathlib import Path
import time
from sqlalchemy import (
    and_,
    or_,
    case,
    cast,
    func,
    insert,
    literal,
    select,
    Text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as upsert
from osii.persistence.postgres import jobs, identifier, now
from osii.persistence.workspace_schema import (
    inventory_sources as sources,
    inventory_scans as scans,
    inventory_entries as entries,
    inventory_directories as directories,
    inventory_events as events,
    inventory_selections as selections,
    inventory_members as members,
)
from osii.domain.processing.directory_scan import checked_path
from osii.volume.models import Filters, ScanOptions, SelectionRequest

ACTIVE = ("queued", "running", "pausing", "paused", "cancelling")


class PostgresInventory:
    def __init__(self, store, mount_root: Path):
        self.store, self.root = store, mount_root.absolute()

    def relative(self, value: str) -> str:
        path = Path(value or ".")
        if path.is_absolute():
            try:
                path = path.relative_to(self.root)
            except ValueError:
                raise ValueError(
                    "Choose a location inside the mounted source root"
                ) from None
        if ".." in path.parts:
            raise ValueError("Source paths cannot traverse outside the mount")
        return "" if str(path) == "." else path.as_posix()

    def location(self, value: str) -> Path:
        path = checked_path(self.root, self.relative(value))
        if not path.is_dir():
            raise ValueError("Source directory is unavailable")
        return path

    def _source(self, row):
        return {**dict(row), "root": str(self.root / row["relative_root"])}

    def source(self, source_id: int, c=None) -> dict:
        if c is None:
            with self.store.engine.connect() as connection:
                return self.source(source_id, connection)
        row = (
            c.execute(select(sources).where(sources.c.id == source_id))
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError("Inventory location not found")
        return self._source(row)

    def sources(self):
        with self.store.engine.connect() as c:
            return [
                self._source(row)
                for row in c.execute(select(sources).order_by(sources.c.id)).mappings()
            ]

    def register(self, raw: str, name: str = ""):
        path = self.location(raw)
        info = path.stat()
        relative = self.relative(str(path))
        with self.store.transaction() as c:
            statement = (
                upsert(sources)
                .values(
                    relative_root=relative,
                    name=name or path.name or "Mounted source",
                    device=str(info.st_dev),
                    inode=str(info.st_ino),
                )
                .on_conflict_do_nothing(index_elements=[sources.c.relative_root])
            )
            c.execute(statement)
            row = (
                c.execute(select(sources).where(sources.c.relative_root == relative))
                .mappings()
                .one()
            )
            if (row["device"], row["inode"]) != (str(info.st_dev), str(info.st_ino)):
                raise ValueError(
                    "Source root identity changed; verify and explicitly rebind the registered location"
                )
            return self._source(row)

    def rebind(self, source_id: int, confirmed: str):
        with self.store.transaction() as c:
            c.execute(
                select(sources.c.id).where(sources.c.id == source_id).with_for_update()
            )
            source = self.source(source_id, c)
            if confirmed != source["root"]:
                raise ValueError(
                    "Confirm the exact registered root after verifying the mount"
                )
            path = self.location(confirmed)
            info = path.stat()
            if c.execute(
                select(scans.c.id)
                .join(jobs, jobs.c.id == scans.c.job_id)
                .where(
                    scans.c.source_id == source_id,
                    or_(jobs.c.status.in_(ACTIVE), jobs.c.lease_until > now()),
                )
            ).first():
                raise ValueError(
                    "Cancel active scans and wait for the worker before rebinding"
                )
            c.execute(
                update(sources)
                .where(sources.c.id == source_id)
                .values(
                    device=str(info.st_dev),
                    inode=str(info.st_ino),
                    generation=sources.c.generation + 1,
                )
            )
            c.execute(
                update(entries)
                .where(entries.c.source_id == source_id)
                .values(
                    status="unverified",
                    revision=entries.c.revision + 1,
                    scan_run_id=None,
                    file_id=None,
                )
            )
            return self.source(source_id, c)

    def start(self, source_id: int, options: ScanOptions):
        with self.store.transaction() as c:
            c.execute(
                select(sources.c.id).where(sources.c.id == source_id).with_for_update()
            )
            source = self.source(source_id, c)
            if c.execute(
                select(scans.c.id)
                .join(jobs, jobs.c.id == scans.c.job_id)
                .where(scans.c.source_id == source_id, jobs.c.status.in_(ACTIVE))
            ).first():
                raise ValueError(
                    "Resume or cancel the existing scan before starting another"
                )
            jid = identifier()
            timestamp = time.time()
            payload = {
                **options.model_dump(),
                "isolate": True,
                "source_generation": source["generation"],
                "source_id": source_id,
            }
            c.execute(
                insert(jobs).values(
                    id=jid,
                    kind="inventory_scan",
                    status="queued",
                    payload=payload,
                    logs=[],
                    attempts=0,
                    created_at=now(),
                )
            )
            sid = c.execute(
                insert(scans)
                .values(
                    source_id=source_id,
                    job_id=jid,
                    created=timestamp,
                    updated=timestamp,
                )
                .returning(scans.c.id)
            ).scalar_one()
            c.execute(insert(directories).values(scan_id=sid, path=""))
        return self.run(sid)

    def _run(self, c, row):
        value = dict(row)
        value.update(
            kind="scan",
            error=value.get("error")
            or (
                value["logs"][-1]
                if value["status"] == "error" and value.get("logs")
                else None
            ),
        )
        value["issue_code"] = (
            "identity_changed"
            if "identity changed" in (value["error"] or "").lower()
            else None
        )
        value["current_paths"] = list(
            c.execute(
                select(directories.c.path)
                .where(
                    directories.c.scan_id == value["id"],
                    directories.c.status == "running",
                )
                .limit(8)
            ).scalars()
        )
        return {k: v for k, v in value.items() if k not in {"logs", "payload"}}

    def run(self, scan_id: int):
        with self.store.engine.connect() as c:
            row = (
                c.execute(
                    select(scans, jobs.c.status, jobs.c.logs)
                    .join(jobs, jobs.c.id == scans.c.job_id)
                    .where(scans.c.id == scan_id)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError("Scan not found")
            return self._run(c, row)

    def runs(
        self,
        *,
        source_id=None,
        cursor=0,
        limit=100,
        recent=False,
        before=None,
        active_only=False,
    ):
        query = (
            select(scans, jobs.c.status, jobs.c.logs)
            .join(jobs, jobs.c.id == scans.c.job_id)
            .where(scans.c.id > cursor)
        )
        if source_id is not None:
            query = query.where(scans.c.source_id == source_id)
        if before is not None:
            query = query.where(scans.c.id < before)
        if active_only:
            query = query.where(jobs.c.status.in_(ACTIVE))
        with self.store.engine.connect() as c:
            return [
                self._run(c, row)
                for row in c.execute(
                    query.order_by(scans.c.id.desc() if recent else scans.c.id).limit(
                        limit
                    )
                ).mappings()
            ]

    def control(self, scan_id: int, action: str):
        scan = self.run(scan_id)
        with self.store.transaction() as connection:
            connection.execute(
                select(sources.c.id)
                .where(sources.c.id == scan["source_id"])
                .with_for_update()
            )
            job = (
                connection.execute(
                    select(jobs).where(jobs.c.id == scan["job_id"]).with_for_update()
                )
                .mappings()
                .one()
            )
            if action == "resume" and job["status"] == "error":
                action = "retry"
            transitions = {
                "pause": {"queued": "paused", "running": "pausing"},
                "resume": {"paused": "queued"},
                "retry": {"error": "queued"},
                "cancel": {
                    "queued": "cancelled",
                    "paused": "cancelled",
                    "running": "cancelling",
                    "pausing": "cancelling",
                },
            }
            target = transitions.get(action, {}).get(job["status"])
            if target is None:
                raise ValueError(f"Cannot {action} a {job['status']} scan")
            if target == "queued":
                if connection.execute(
                    select(scans.c.id).where(
                        scans.c.source_id == scan["source_id"], scans.c.id > scan_id
                    )
                ).first():
                    raise ValueError(
                        "A newer scan superseded this one; resume the latest scan"
                    )
                connection.execute(
                    update(directories)
                    .where(
                        directories.c.scan_id == scan_id,
                        directories.c.status == "error",
                    )
                    .values(status="pending", error=None, attempts=0)
                )
                connection.execute(
                    update(scans)
                    .where(scans.c.id == scan_id)
                    .values(error=None, failed=0, updated=time.time())
                )
            connection.execute(
                update(jobs).where(jobs.c.id == job["id"]).values(status=target)
            )
        return self.run(scan_id)

    def events(self, scan_id, cursor=0, limit=100):
        self.run(scan_id)
        with self.store.engine.connect() as c:
            return [
                dict(row)
                for row in c.execute(
                    select(events)
                    .where(events.c.scan_id == scan_id, events.c.id > cursor)
                    .order_by(events.c.id)
                    .limit(limit)
                ).mappings()
            ]

    def filter(self, filters: Filters):
        e = entries.c
        terms = [e.kind.in_(("file", "unknown")), e.status == "present"]
        if filters.source_id is not None:
            terms.append(e.source_id == filters.source_id)
        if filters.path:
            path = filters.path.strip("/")
            terms.append(
                or_(e.path == path, e.path.startswith(path + "/", autoescape=True))
            )
        if filters.name:
            terms.append(e.name.contains(filters.name, autoescape=True))
        if filters.suffix:
            terms.append(e.suffix == "." + filters.suffix.lower().lstrip("."))
        if filters.metadata_state != "any":
            terms.append(e.metadata_state == filters.metadata_state)
        if filters.text_state != "any":
            terms.append(
                e.file_id.is_(None)
                if filters.text_state == "metadata_only"
                else e.file_id.is_not(None)
            )
        if filters.sidecar_state != "any":
            terms.append(
                e.file_id.is_(None)
                if filters.sidecar_state == "missing"
                else e.file_id.is_not(None)
            )
        if filters.min_bytes or filters.max_bytes is not None:
            terms += [e.metadata_state == "known", e.size_bytes >= filters.min_bytes]
        if filters.max_bytes is not None:
            terms.append(e.size_bytes <= filters.max_bytes)
        for value, after in (
            (filters.modified_after, True),
            (filters.modified_before, False),
        ):
            if value is not None:
                terms += [
                    e.metadata_state == "known",
                    e.mtime_ns >= value * 10**9
                    if after
                    else e.mtime_ns < (value + 1) * 10**9,
                ]
        return and_(*terms)

    @staticmethod
    def _entry(row):
        value = dict(row)
        value["extraction_id"] = value["file_id"]
        if value["metadata_state"] != "known":
            value.update(size_bytes=None, mtime_ns=None, ctime_ns=None)
        return value

    def entries(self, filters: Filters, cursor=0, limit=100):
        with self.store.engine.connect() as c:
            rows = [
                self._entry(row)
                for row in c.execute(
                    select(entries)
                    .where(self.filter(filters), entries.c.id > cursor)
                    .order_by(entries.c.id)
                    .limit(limit + 1)
                ).mappings()
            ]
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def summary(self, filters: Filters):
        where = self.filter(filters)
        with self.store.engine.connect() as c:
            result = dict(
                c.execute(
                    select(
                        func.count().label("files"),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        entries.c.metadata_state == "known",
                                        entries.c.size_bytes,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label("bytes"),
                        func.count(entries.c.file_id).label("extracted"),
                        func.count()
                        .filter(entries.c.metadata_state != "known")
                        .label("unknown_sizes"),
                    ).where(where)
                )
                .mappings()
                .one()
            )
            result["formats"] = [
                dict(row)
                for row in c.execute(
                    select(
                        entries.c.suffix,
                        func.count().label("files"),
                        func.sum(entries.c.size_bytes).label("bytes"),
                    )
                    .where(where)
                    .group_by(entries.c.suffix)
                    .order_by(func.count().desc())
                    .limit(100)
                ).mappings()
            ]
        result["scan_status"] = self.runs(
            source_id=filters.source_id, recent=True, limit=100
        )
        return result

    def select(self, request: SelectionRequest):
        if request.filters.source_id is None:
            raise ValueError("Choose one inventory location before freezing a batch")
        if request.entry_ids is not None and request.sample:
            raise ValueError("Explicit files cannot also be sampled")
        with self.store.transaction() as c:
            c.execute(
                select(sources.c.id)
                .where(sources.c.id == request.filters.source_id)
                .with_for_update()
            )
            source = self.source(request.filters.source_id, c)
            scan = (
                c.execute(
                    select(scans, jobs.c.status)
                    .join(jobs, jobs.c.id == scans.c.job_id)
                    .where(scans.c.source_id == source["id"])
                    .order_by(scans.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if scan is None:
                raise ValueError("Scan this location before selecting inventory files")
            c.execute(
                select(jobs.c.id).where(jobs.c.id == scan["job_id"]).with_for_update()
            )
            state = c.execute(
                select(jobs.c.status).where(jobs.c.id == scan["job_id"])
            ).scalar_one()
            if state != "done" and not request.allow_partial:
                raise ValueError(
                    "Discovery coverage is incomplete; wait or explicitly allow a partial selection"
                )
            where = and_(
                self.filter(request.filters),
                entries.c.kind == "file",
                entries.c.metadata_state == "known",
                entries.c.scan_run_id == scan["id"],
                entries.c.size_bytes <= request.max_bytes,
            )
            if request.entry_ids is not None:
                where = and_(where, entries.c.id.in_(set(request.entry_ids)))
            base = select(entries).where(where)
            if request.sample:
                order = func.md5(literal(request.seed) + cast(entries.c.id, Text))
                base = base.add_columns(
                    func.row_number()
                    .over(
                        partition_by=[
                            entries.c.parent,
                            entries.c.suffix,
                            case(
                                (entries.c.size_bytes < 1024**2, 0),
                                (entries.c.size_bytes < 100 * 1024**2, 1),
                                else_=2,
                            ),
                            func.trunc(entries.c.mtime_ns / 31557600000000000),
                        ],
                        order_by=[order, entries.c.id],
                    )
                    .label("sample_rank"),
                    order.label("random_order"),
                )
                sample = base.subquery()
                base = select(sample).where(sample.c.sample_rank <= request.per_stratum)
            else:
                base = base.order_by(entries.c.id).limit(request.max_files)
            candidates = base.subquery()
            order = (
                [candidates.c.sample_rank, candidates.c.random_order, candidates.c.id]
                if request.sample
                else [candidates.c.id]
            )
            bounded = select(
                candidates,
                func.sum(candidates.c.size_bytes)
                .over(order_by=order)
                .label("running_bytes"),
                func.row_number().over(order_by=order).label("position"),
            ).subquery()
            accepted = (
                select(bounded)
                .where(
                    bounded.c.position <= request.max_files,
                    bounded.c.running_bytes <= request.max_bytes,
                )
                .subquery()
            )
            timestamp = time.time()
            coverage = [
                {
                    "id": scan["id"],
                    "source_id": source["id"],
                    "status": state,
                    "updated": scan["updated"],
                }
            ]
            sid = c.execute(
                insert(selections)
                .values(
                    request=request.model_dump(), coverage=coverage, created=timestamp
                )
                .returning(selections.c.id)
            ).scalar_one()
            snapshot = func.jsonb_build_object(
                "revision",
                accepted.c.revision,
                "source_id",
                accepted.c.source_id,
                "path",
                accepted.c.path,
                "size_bytes",
                accepted.c.size_bytes,
                "mtime_ns",
                accepted.c.mtime_ns,
                "ctime_ns",
                accepted.c.ctime_ns,
                "file_device",
                accepted.c.device,
                "file_inode",
                accepted.c.inode,
                "source_generation",
                source["generation"],
                "source_device",
                source["device"],
                "source_inode",
                source["inode"],
                "relative_root",
                source["relative_root"],
            )
            c.execute(
                insert(members).from_select(
                    ["selection_id", "entry_id", "snapshot"],
                    select(literal(sid), accepted.c.id, snapshot),
                )
            )
            count, total = c.execute(
                select(
                    func.count(),
                    func.coalesce(
                        func.sum(
                            cast(
                                members.c.snapshot["size_bytes"].astext,
                                entries.c.size_bytes.type,
                            )
                        ),
                        0,
                    ),
                ).where(members.c.selection_id == sid)
            ).one()
            if request.entry_ids is not None and count != len(set(request.entry_ids)):
                raise ValueError(
                    "Some selected files changed, are unavailable, or exceed the selection limits"
                )
            if count == 0:
                raise ValueError("No available files match this batch selection")
            c.execute(
                update(selections)
                .where(selections.c.id == sid)
                .values(count=count, bytes=total)
            )
        return self.selection(sid)

    def selection(self, selection_id):
        with self.store.engine.connect() as c:
            row = (
                c.execute(select(selections).where(selections.c.id == selection_id))
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError("Frozen selection not found")
            return {
                **dict(row),
                "request": json.dumps(row["request"]),
                "coverage": json.dumps(row["coverage"]),
            }

    def selections(self, cursor=0, limit=100):
        with self.store.engine.connect() as c:
            ids = list(
                c.execute(
                    select(selections.c.id)
                    .where(selections.c.id > cursor)
                    .order_by(selections.c.id)
                    .limit(limit)
                ).scalars()
            )
        return [self.selection(sid) for sid in ids]

    def selection_entries(self, selection_id, cursor=0, limit=100):
        self.selection(selection_id)
        with self.store.engine.connect() as c:
            rows = (
                c.execute(
                    select(entries, members.c.snapshot)
                    .join(members, members.c.entry_id == entries.c.id)
                    .where(
                        members.c.selection_id == selection_id, entries.c.id > cursor
                    )
                    .order_by(entries.c.id)
                    .limit(limit + 1)
                )
                .mappings()
                .all()
            )
        result = []
        for row in rows:
            snapshot = row["snapshot"]
            value = self._entry({k: v for k, v in row.items() if k != "snapshot"})
            value.update(
                {k: snapshot[k] for k in ("path", "size_bytes", "mtime_ns", "ctime_ns")}
            )
            value["stale"] = (
                row["revision"] != snapshot["revision"] or row["status"] != "present"
            )
            result.append(value)
        return {
            "items": result[:limit],
            "next_cursor": result[limit - 1]["id"] if len(result) > limit else None,
        }

    def frozen(self, selection_id):
        selection = self.selection(selection_id)
        if not 0 < selection["count"] <= 5000:
            raise ValueError(
                "Intake supports 1–5,000 frozen files per plan; select a smaller batch"
            )
        with self.store.engine.connect() as c:
            result = []
            for row in c.execute(
                select(
                    members.c.entry_id,
                    members.c.snapshot,
                    entries.c.revision,
                    entries.c.status,
                    entries.c.metadata_state,
                )
                .join(entries, entries.c.id == members.c.entry_id)
                .where(members.c.selection_id == selection_id)
                .order_by(members.c.entry_id)
            ).mappings():
                snapshot = row["snapshot"]
                source = self.source(snapshot["source_id"], c)
                if (
                    row["revision"] != snapshot["revision"]
                    or row["status"] != "present"
                    or row["metadata_state"] != "known"
                    or source["generation"] != snapshot["source_generation"]
                ):
                    raise ValueError(
                        "Frozen selection is stale; scan and select the files again"
                    )
                result.append({**snapshot, "entry_id": row["entry_id"]})
        if len(result) != selection["count"]:
            raise ValueError("Frozen selection is incomplete")
        return result

    def scan_context(self, job, worker):
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (job["id"], worker))
            scan = dict(
                c.execute(select(scans).where(scans.c.job_id == job["id"]))
                .mappings()
                .one()
            )
            source = self.source(scan["source_id"], c)
            if source["generation"] != job["payload"]["source_generation"]:
                raise ValueError("Source generation changed; start a new scan")
            c.execute(
                update(directories)
                .where(
                    directories.c.scan_id == scan["id"],
                    directories.c.status == "running",
                )
                .values(status="pending")
            )
        return scan, source

    def _scan_owner(self, c, job, worker):
        from osii.domain.processing.directory_scan import InterruptedRun

        self.store.assert_job_owner(c, (job["id"], worker))
        if (
            c.execute(select(jobs.c.status).where(jobs.c.id == job["id"])).scalar_one()
            != "running"
        ):
            raise InterruptedRun()

    def claim_directory(self, scan, job, worker):
        with self.store.transaction() as c:
            self._scan_owner(c, job, worker)
            row = c.execute(
                select(directories.c.path)
                .where(
                    directories.c.scan_id == scan["id"],
                    directories.c.status == "pending",
                    directories.c.attempts < 3,
                )
                .order_by(directories.c.path)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if row is None:
                c.execute(
                    update(directories)
                    .where(
                        directories.c.scan_id == scan["id"],
                        directories.c.status == "pending",
                        directories.c.attempts >= 3,
                    )
                    .values(
                        status="error",
                        error="Directory recovery exhausted; explicitly resume to retry",
                    )
                )
                return None
            c.execute(
                update(directories)
                .where(
                    directories.c.scan_id == scan["id"], directories.c.path == row.path
                )
                .values(
                    status="running",
                    attempts=directories.c.attempts + 1,
                    updated=time.time(),
                )
            )
            return row.path

    def write_batch(self, scan, job, worker, rows, children):
        rows = list({row[1]: row for row in rows}.values())
        names = (
            "source_id",
            "path",
            "parent",
            "name",
            "kind",
            "suffix",
            "size_bytes",
            "mtime_ns",
            "ctime_ns",
            "device",
            "inode",
            "observed",
            "seen_token",
            "metadata_state",
            "metadata_error",
            "status",
        )
        with self.store.transaction() as c:
            self._scan_owner(c, job, worker)
            old = (
                {
                    r["path"]: dict(r)
                    for r in c.execute(
                        select(entries).where(
                            entries.c.source_id == scan["source_id"],
                            entries.c.path.in_([row[1] for row in rows]),
                        )
                    ).mappings()
                }
                if rows
                else {}
            )
            if rows:
                statement = upsert(entries).values(
                    [
                        {**dict(zip(names, row)), "scan_run_id": scan["id"]}
                        for row in rows
                    ]
                )
                fields = (
                    "size_bytes",
                    "mtime_ns",
                    "ctime_ns",
                    "kind",
                    "status",
                    "metadata_state",
                    "device",
                    "inode",
                )
                changed = or_(
                    *(
                        entries.c[name].is_distinct_from(statement.excluded[name])
                        for name in fields
                    )
                )
                changes = {
                    name: statement.excluded[name]
                    for name in names
                    if name not in {"source_id", "path", "parent", "name"}
                }
                changes.update(
                    scan_run_id=scan["id"],
                    revision=entries.c.revision + case((changed, 1), else_=0),
                    file_id=case((changed, None), else_=entries.c.file_id),
                )
                c.execute(
                    statement.on_conflict_do_update(
                        constraint="inventory_entry_source_path", set_=changes
                    )
                )
            if children:
                c.execute(
                    upsert(directories)
                    .values(
                        [
                            {"scan_id": scan["id"], "path": path}
                            for path in set(children)
                        ]
                    )
                    .on_conflict_do_nothing()
                )
            observed, byte_delta, error_delta = 0, 0, 0
            for row in rows:
                previous = old.get(row[1])
                current = previous and previous["scan_run_id"] == scan["id"]
                observed += not current
                byte_delta += (
                    row[6]
                    if row[4] == "file" and row[13] == "known" and row[15] == "present"
                    else 0
                ) - (
                    previous["size_bytes"]
                    if current
                    and previous["kind"] == "file"
                    and previous["metadata_state"] == "known"
                    and previous["status"] == "present"
                    else 0
                )
                error_delta += bool(row[14]) - bool(
                    current and previous["metadata_error"]
                )
                if row[14] and (not current or row[14] != previous["metadata_error"]):
                    c.execute(
                        insert(events).values(
                            scan_id=scan["id"],
                            created=time.time(),
                            path=row[1],
                            message=row[14],
                        )
                    )
            c.execute(
                update(scans)
                .where(scans.c.id == scan["id"])
                .values(
                    updated=time.time(),
                    observed_entries=scans.c.observed_entries + observed,
                    known_bytes=scans.c.known_bytes + byte_delta,
                    metadata_errors=scans.c.metadata_errors + error_delta,
                )
            )

    def finish_directory(self, scan, job, worker, path, message):
        from sqlalchemy import text

        error = (
            message[1]
            if message[0] == "error"
            else "Some entry metadata is unavailable; coverage incomplete"
            if message[2]
            else None
        )
        with self.store.transaction() as c:
            self._scan_owner(c, job, worker)
            if not error:
                # Absence is evidence only after a complete, stable enumeration.
                c.execute(
                    text("""WITH RECURSIVE missing(id,path) AS (
                  SELECT id,path FROM inventory_entries WHERE source_id=:source AND parent=:parent AND seen_token!=:token AND status!='excluded'
                  UNION SELECT child.id,child.path FROM inventory_entries child JOIN inventory_entries parent
                    ON child.source_id=parent.source_id AND child.parent=parent.path
                    WHERE parent.source_id=:source AND parent.parent=:parent AND parent.kind!='directory' AND parent.metadata_state='known'
                  UNION ALL SELECT e.id,e.path FROM inventory_entries e JOIN missing m ON e.parent=m.path WHERE e.source_id=:source)
                  UPDATE inventory_entries SET status='missing',revision=revision+CASE WHEN status!='missing' THEN 1 ELSE 0 END,file_id=NULL
                  WHERE id IN (SELECT id FROM missing)"""),
                    {"source": scan["source_id"], "parent": path, "token": message[1]},
                )
            c.execute(
                update(directories)
                .where(directories.c.scan_id == scan["id"], directories.c.path == path)
                .values(
                    status="error" if error else "done",
                    error=error,
                    updated=time.time(),
                )
            )
            c.execute(
                update(scans)
                .where(scans.c.id == scan["id"])
                .values(updated=time.time(), completed=scans.c.completed + 1)
            )
            if error:
                c.execute(
                    insert(events).values(
                        scan_id=scan["id"],
                        created=time.time(),
                        path=path,
                        message=error,
                    )
                )

    def finish_scan(self, scan, job, worker, error=None):
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (job["id"], worker))
            c.execute(
                update(directories)
                .where(
                    directories.c.scan_id == scan["id"],
                    directories.c.status == "running",
                )
                .values(status="pending")
            )
            failed = c.execute(
                select(func.count()).where(
                    directories.c.scan_id == scan["id"], directories.c.status == "error"
                )
            ).scalar_one()
            pending = c.execute(
                select(func.count()).where(
                    directories.c.scan_id == scan["id"],
                    directories.c.status == "pending",
                )
            ).scalar_one()
            reason = error
            if not reason and failed:
                reason = c.execute(
                    select(directories.c.error)
                    .where(
                        directories.c.scan_id == scan["id"],
                        directories.c.status == "error",
                    )
                    .order_by(directories.c.path)
                    .limit(1)
                ).scalar()
            c.execute(
                update(scans)
                .where(scans.c.id == scan["id"])
                .values(failed=failed, error=reason, updated=time.time())
            )
            if error:
                c.execute(
                    insert(events).values(
                        scan_id=scan["id"], created=time.time(), message=error
                    )
                )
        return bool(error or failed), bool(pending)

    def verify_member(self, member):
        with self.store.engine.connect() as connection:
            row = connection.execute(
                select(entries.c.revision, entries.c.status).where(
                    entries.c.id == member["entry_id"]
                )
            ).first()
            source = self.source(member["source_id"], connection)
            if (
                row is None
                or row.revision != member["revision"]
                or row.status != "present"
                or source["generation"] != member["source_generation"]
            ):
                raise ValueError(
                    "Frozen source observation changed; scan and select it again"
                )
        return self._verify_files([member])[0]

    def verify_members(self, selection_id):
        return self._verify_files(self.frozen(selection_id))

    def _verify_files(self, result):
        for member in result:
            source = self.source(member["source_id"])
            root = self.location(source["root"])
            root_stat = root.stat()
            if (str(root_stat.st_dev), str(root_stat.st_ino)) != (
                member["source_device"],
                member["source_inode"],
            ):
                raise ValueError(
                    "Source root identity changed; verify the mount and rebind before processing"
                )
            path = checked_path(root, member["path"])
            info = path.stat()
            if not path.is_file() or (
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
                str(info.st_dev),
                str(info.st_ino),
            ) != (
                member["size_bytes"],
                member["mtime_ns"],
                member["ctime_ns"],
                member["file_device"],
                member["file_inode"],
            ):
                raise ValueError(
                    "A frozen source file changed; scan and select it again"
                )
            member["source_relpath"] = (
                Path(member["relative_root"]) / member["path"]
            ).as_posix()
        return result

    def link(self, member, file_id, job, worker):
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (job["id"], worker))
            c.execute(
                update(entries)
                .where(
                    entries.c.id == member["entry_id"],
                    entries.c.revision == member["revision"],
                    entries.c.status == "present",
                )
                .values(file_id=file_id)
            )
