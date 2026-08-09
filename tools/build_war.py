from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import zipfile


def _write_entry(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(entry, content)


def _compile_java(java_source: pathlib.Path, api_stubs: pathlib.Path, output: pathlib.Path) -> None:
    sources = sorted(java_source.rglob("*.java"))
    stubs = sorted(api_stubs.rglob("*.java"))
    if not sources:
        return
    if not stubs:
        raise SystemExit(f"Missing Java EE compile-only API stubs below {api_stubs}")
    javac = shutil.which("javac")
    if not javac:
        raise SystemExit("javac is required to compile the sample application's startup hook")
    command = [
        javac,
        "--release",
        "8",
        "-encoding",
        "UTF-8",
        "-d",
        str(output),
        *[str(path) for path in sources],
        *[str(path) for path in stubs],
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"Unable to compile the sample application's Java classes: {detail}")


def build(
    source: pathlib.Path,
    output: pathlib.Path,
    java_source: pathlib.Path | None = None,
    api_stubs: pathlib.Path | None = None,
) -> str:
    if not (source / "WEB-INF" / "web.xml").is_file():
        raise SystemExit(f"Missing deployment descriptor below {source}")
    java_source = java_source or source.parent / "sample-app-java"
    api_stubs = api_stubs or pathlib.Path(__file__).resolve().parent / "java-stubs"
    output.parent.mkdir(parents=True, exist_ok=True)
    build_root = source.parent / ".data" / "war-build"
    if build_root.exists():
        shutil.rmtree(build_root)
    classes = build_root / "classes"
    classes.mkdir(parents=True)
    try:
        _compile_java(java_source, api_stubs, classes)
        with zipfile.ZipFile(output, "w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    _write_entry(archive, path.relative_to(source).as_posix(), path.read_bytes())
            for path in sorted(classes.rglob("*.class")):
                relative = path.relative_to(classes)
                if relative.parts[:2] == ("javax", "servlet"):
                    continue
                _write_entry(
                    archive,
                    f"WEB-INF/classes/{relative.as_posix()}",
                    path.read_bytes(),
                )
    finally:
        shutil.rmtree(build_root, ignore_errors=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the lab's Java EE WAR deterministically.")
    parser.add_argument("--source", type=pathlib.Path, default=pathlib.Path("sample-app"))
    parser.add_argument(
        "--output", type=pathlib.Path, default=pathlib.Path("ansible/files/was-lab.war")
    )
    parser.add_argument(
        "--java-source", type=pathlib.Path, default=pathlib.Path("sample-app-java")
    )
    parser.add_argument(
        "--api-stubs", type=pathlib.Path, default=pathlib.Path("tools/java-stubs")
    )
    args = parser.parse_args()
    digest = build(
        args.source.resolve(),
        args.output.resolve(),
        args.java_source.resolve(),
        args.api_stubs.resolve(),
    )
    print(f"WAR={args.output}")
    print(f"SHA256={digest}")


if __name__ == "__main__":
    main()
