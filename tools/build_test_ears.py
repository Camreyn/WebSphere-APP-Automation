from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape

import yaml


KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def write_entry(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(entry, content)


def web_descriptor(application: dict[str, str]) -> bytes:
    values = {key: xml_escape(str(value)) for key, value in application.items()}
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://xmlns.jcp.org/xml/ns/javaee http://xmlns.jcp.org/xml/ns/javaee/web-app_3_1.xsd"
         version="3.1">
  <display-name>{values["display_name"]}</display-name>
  <context-param>
    <param-name>waslab.applicationName</param-name>
    <param-value>{values["display_name"]}</param-value>
  </context-param>
  <context-param>
    <param-name>waslab.description</param-name>
    <param-value>{values["description"]}</param-value>
  </context-param>
  <context-param>
    <param-name>waslab.accentColor</param-name>
    <param-value>{values["accent_color"]}</param-value>
  </context-param>
  <welcome-file-list>
    <welcome-file>index.jsp</welcome-file>
  </welcome-file-list>
</web-app>
'''
    return document.encode("utf-8")


def application_descriptor(application: dict[str, str]) -> bytes:
    display_name = xml_escape(application["display_name"])
    web_uri = xml_escape(f'{application["key"]}.war')
    context_root = xml_escape(application["context_root"])
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<application xmlns="http://xmlns.jcp.org/xml/ns/javaee"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://xmlns.jcp.org/xml/ns/javaee http://xmlns.jcp.org/xml/ns/javaee/application_7.xsd"
             version="7">
  <display-name>{display_name}</display-name>
  <module>
    <web>
      <web-uri>{web_uri}</web-uri>
      <context-root>{context_root}</context-root>
    </web>
  </module>
</application>
'''
    return document.encode("utf-8")


def build_war(application: dict[str, str], index_page: bytes) -> bytes:
    output = io.BytesIO()
    manifest = b"Manifest-Version: 1.0\r\nCreated-By: WAS ND Lab\r\n\r\n"
    with zipfile.ZipFile(output, "w") as archive:
        write_entry(archive, "META-INF/MANIFEST.MF", manifest)
        write_entry(archive, "WEB-INF/web.xml", web_descriptor(application))
        write_entry(archive, "index.jsp", index_page)
    return output.getvalue()


def validate(applications: list[dict[str, str]]) -> None:
    if not applications:
        raise SystemExit("test_ears must contain at least one application")
    keys: set[str] = set()
    contexts: set[str] = set()
    required = {"key", "display_name", "context_root", "accent_color", "description"}
    for application in applications:
        missing = sorted(required - set(application))
        if missing:
            raise SystemExit(f"Test EAR entry is missing: {', '.join(missing)}")
        key = str(application["key"])
        context_root = str(application["context_root"])
        if not KEY_PATTERN.fullmatch(key):
            raise SystemExit(f"Unsafe test EAR key: {key}")
        if not context_root.startswith("/") or context_root == "/":
            raise SystemExit(f"Invalid context root for {key}: {context_root}")
        if not COLOR_PATTERN.fullmatch(str(application["accent_color"])):
            raise SystemExit(f"Invalid accent color for {key}: {application['accent_color']}")
        if key in keys or context_root in contexts:
            raise SystemExit(f"Duplicate test EAR key or context root: {key}")
        keys.add(key)
        contexts.add(context_root)


def build(config: pathlib.Path, template: pathlib.Path, output: pathlib.Path) -> list[pathlib.Path]:
    document = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    applications = document.get("test_ears") or []
    if not isinstance(applications, list) or not all(isinstance(item, dict) for item in applications):
        raise SystemExit("test_ears must be a list of mappings")
    validate(applications)
    index_page = template.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    built: list[pathlib.Path] = []
    manifest = b"Manifest-Version: 1.0\r\nCreated-By: WAS ND Lab\r\n\r\n"
    for application in applications:
        normalized = {key: str(value) for key, value in application.items()}
        war_name = f'{normalized["key"]}.war'
        ear_path = output / f'{normalized["key"]}.ear'
        with zipfile.ZipFile(ear_path, "w") as archive:
            write_entry(archive, "META-INF/MANIFEST.MF", manifest)
            write_entry(archive, "META-INF/application.xml", application_descriptor(normalized))
            write_entry(archive, war_name, build_war(normalized, index_page))
        built.append(ear_path)
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic Java EE test EAR files.")
    parser.add_argument("--config", type=pathlib.Path, default=pathlib.Path("config/test_ears.yml"))
    parser.add_argument(
        "--template", type=pathlib.Path, default=pathlib.Path("sample-ear-template/index.jsp")
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=pathlib.Path("ansible/files/test-ears")
    )
    args = parser.parse_args()
    for ear_path in build(args.config.resolve(), args.template.resolve(), args.output.resolve()):
        digest = hashlib.sha256(ear_path.read_bytes()).hexdigest()
        print(f"EAR={ear_path.name} SHA256={digest}")


if __name__ == "__main__":
    main()
