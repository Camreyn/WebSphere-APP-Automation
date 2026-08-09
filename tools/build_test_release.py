from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import pathlib
import re
import zipfile

import yaml

from build_test_ears import application_descriptor, build_war, validate, write_entry


VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an immutable visible-version EAR for the simple AWX deployment job."
    )
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--application", default="orders-test")
    parser.add_argument("--version", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not VERSION_PATTERN.fullmatch(args.version):
        raise SystemExit(
            "Version must begin with a letter or number and contain only letters, "
            "numbers, dots, underscores, and hyphens."
        )

    config_path = root / "config" / "test_ears.yml"
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    applications = document.get("test_ears") or []
    validate(applications)
    matches = [item for item in applications if str(item["key"]) == args.application]
    if len(matches) != 1:
        raise SystemExit(f"Unknown test EAR application: {args.application}")

    application = {key: str(value) for key, value in matches[0].items()}
    release_marker = f"Immutable release {args.version}"
    application["description"] = (
        f'{application["description"]} {release_marker}.'
    )
    release_dir = root / "artifacts" / "releases" / args.application / args.version
    archive_path = release_dir / f"{args.application}.ear"
    manifest_path = release_dir / "release.yml"
    if (archive_path.exists() or manifest_path.exists()) and not args.force:
        raise SystemExit(f"Immutable release already exists: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=True)

    manifest_bytes = b"Manifest-Version: 1.0\r\nCreated-By: WAS ND Lab\r\n\r\n"
    template = (root / "sample-ear-template" / "index.jsp").read_bytes()
    war_name = f"{args.application}.war"
    with zipfile.ZipFile(archive_path, "w") as archive:
        write_entry(archive, "META-INF/MANIFEST.MF", manifest_bytes)
        write_entry(archive, "META-INF/application.xml", application_descriptor(application))
        write_entry(archive, war_name, build_war(application, template))

    checksum = sha256(archive_path)
    manifest = {
        "schema_version": 1,
        "application": args.application,
        "version": args.version,
        "filename": archive_path.name,
        "sha256": checksum,
        "source_commit": "local-lab-operator-release",
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "built_by": getpass.getuser(),
        "release_notes": f"Visible operator workflow verification release {args.version}",
        "health": {
            "url": f'http://localhost:9080{application["context_root"]}/',
            "status_code": 200,
            "contains": release_marker,
            "retries": 20,
            "delay": 2,
        },
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    print(f"APPLICATION={args.application}")
    print(f"VERSION={args.version}")
    print(f"SHA256={checksum}")
    print(f"RELEASE_DIRECTORY={release_dir}")


if __name__ == "__main__":
    main()
