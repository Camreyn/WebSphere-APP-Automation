from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import pathlib
import shutil

import yaml


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an immutable release-share example for the AWX workflow."
    )
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--application", default="was-lab")
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", default="local-lab-build")
    parser.add_argument("--release-notes", default="Generated local lab release")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not args.version or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.version):
        raise SystemExit("Version may contain only letters, numbers, dots, underscores, and hyphens.")

    catalog_path = root / "ansible" / "vars" / "was_application_catalog.yml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    applications = catalog.get("was_application_catalog", {})
    if args.application not in applications:
        raise SystemExit(f"Unknown application catalog key: {args.application}")
    application = applications[args.application]
    source = root / "ansible" / "files" / "was-lab.war"
    if not source.is_file():
        raise SystemExit("Sample WAR is missing. Run .\\lab.ps1 sample-app first.")

    release_dir = root / "artifacts" / "releases" / args.application / args.version
    if release_dir.exists() and not args.force:
        raise SystemExit(
            f"Immutable release already exists: {release_dir}. Choose a new version."
        )
    release_dir.mkdir(parents=True, exist_ok=True)
    archive = release_dir / application["artifact_filename"]
    shutil.copy2(source, archive)
    checksum = sha256(archive)
    manifest = {
        "schema_version": 1,
        "application": args.application,
        "version": args.version,
        "filename": application["artifact_filename"],
        "sha256": checksum,
        "source_commit": args.source_commit,
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "built_by": getpass.getuser(),
        "release_notes": args.release_notes,
    }
    (release_dir / application.get("manifest_filename", "release.yml")).write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    print(f"APPLICATION={args.application}")
    print(f"VERSION={args.version}")
    print(f"SHA256={checksum}")
    print(f"RELEASE_DIRECTORY={release_dir}")


if __name__ == "__main__":
    main()
