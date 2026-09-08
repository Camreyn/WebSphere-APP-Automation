# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import glob
import os
import re
import xml.etree.ElementTree as ET

try:
    import pwd
except ImportError:  # pragma: no cover - Ansible runs this module on Linux hosts.
    pwd = None


DEFAULT_INSTALL_ROOTS = (
    "/opt/WebSphere/AppServers",
    "/opt/IBM/WebSphere/AppServer",
    "/opt/ibm/WebSphere/AppServer",
    "/usr/IBM/WebSphere/AppServer",
    "/opt/IBM/Workflow/*",
    "/opt/ibm/Workflow/*",
    "/opt/IBM/BPM/*",
    "/opt/ibm/BPM/*",
)


def unique_real_paths(paths):
    result = []
    seen = set()
    for path in paths:
        if not path:
            continue
        for expanded in glob.glob(path) or [path]:
            normalized = os.path.realpath(expanded)
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


def parse_profile_names(output):
    """Parse manageprofiles.sh -listProfiles output across IBM fix packs."""
    bracketed = re.findall(r"\[([^\]]*)\]", output or "")
    if bracketed:
        value = bracketed[-1].strip()
        if not value:
            return []
        return [item.strip().strip("'\"") for item in value.split(",") if item.strip()]
    names = []
    for line in (output or "").splitlines():
        value = line.strip().strip("'\"")
        if value and not value.startswith(("ADMU", "INSTCONFSUCCESS")):
            names.append(value)
    return names


def parse_about_profile(path):
    result = {}
    if not os.path.isfile(path):
        return result
    labels = {
        "profile name": "profile_name",
        "cell name": "cell",
        "node name": "node",
        "host name": "host",
    }
    with open(path, "r") as stream:
        for line in stream:
            match = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", line)
            if not match:
                continue
            key = labels.get(match.group(1).strip().lower())
            if key and match.group(2):
                result[key] = match.group(2).strip()
    return result


def profile_type(profile_path):
    commands = os.path.join(profile_path, "bin")
    if os.path.isfile(os.path.join(commands, "startManager.sh")):
        return "dmgr"
    if os.path.isfile(os.path.join(commands, "startNode.sh")):
        return "managed"
    if os.path.isfile(os.path.join(commands, "startServer.sh")):
        return "application_server"
    return "unknown"


def configured_nodes(profile_path):
    records = []
    cells_path = os.path.join(profile_path, "config", "cells")
    if not os.path.isdir(cells_path):
        return records
    for cell in sorted(os.listdir(cells_path)):
        nodes_path = os.path.join(cells_path, cell, "nodes")
        if not os.path.isdir(nodes_path):
            continue
        for node in sorted(os.listdir(nodes_path)):
            node_path = os.path.join(nodes_path, node)
            servers_path = os.path.join(node_path, "servers")
            servers = []
            if os.path.isdir(servers_path):
                servers = sorted(
                    name for name in os.listdir(servers_path)
                    if os.path.isdir(os.path.join(servers_path, name))
                )
            records.append(
                {
                    "cell": cell,
                    "node": node,
                    "node_path": node_path,
                    "servers": servers,
                }
            )
    return records


def select_local_node(records, kind, about):
    about_cell = about.get("cell")
    about_node = about.get("node")
    if about_cell and about_node:
        exact = [
            item for item in records
            if item["cell"] == about_cell and item["node"] == about_node
        ]
        if len(exact) == 1:
            return exact[0]

    marker = "dmgr" if kind == "dmgr" else "nodeagent"
    marked = [
        item for item in records
        if marker in [server.lower() for server in item["servers"]]
    ]
    if len(marked) == 1:
        return marked[0]
    if len(records) == 1:
        return records[0]
    return None


def serverindex_details(node_path):
    path = os.path.join(node_path, "serverindex.xml")
    result = {"path": path, "host": "", "soap_port": None}
    if not os.path.isfile(path):
        return result
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        result["host"] = root.attrib.get("hostName", "")
        for element in root.iter():
            if element.attrib.get("endPointName") != "SOAP_CONNECTOR_ADDRESS":
                continue
            for endpoint in element.iter():
                port = endpoint.attrib.get("port")
                if port and str(port).isdigit():
                    result["soap_port"] = int(port)
                    return result
    except (ET.ParseError, OSError):
        pass

    with open(path, "r") as stream:
        content = stream.read()
    host = re.search(r"\bhostName=[\"']([^\"']+)", content)
    if host:
        result["host"] = host.group(1)
    endpoint = re.search(
        r"endPointName=[\"']SOAP_CONNECTOR_ADDRESS[\"'][\s\S]{0,800}?"
        r"\bport=[\"'](\d+)[\"']",
        content,
    )
    if endpoint:
        result["soap_port"] = int(endpoint.group(1))
    return result


def path_owner(path):
    if pwd is None:
        return ""
    try:
        return pwd.getpwuid(os.stat(path).st_uid).pw_name
    except (KeyError, OSError):
        return ""


def inspect_profile(install_root, name, path):
    kind = profile_type(path)
    about = parse_about_profile(os.path.join(path, "logs", "AboutThisProfile.txt"))
    records = configured_nodes(path)
    local_node = select_local_node(records, kind, about)
    cell = about.get("cell", "")
    node = about.get("node", "")
    servers = []
    endpoint = {"host": about.get("host", ""), "soap_port": None, "path": ""}
    if local_node:
        cell = local_node["cell"]
        node = local_node["node"]
        servers = [
            server for server in local_node["servers"]
            if server.lower() not in ("dmgr", "nodeagent")
        ]
        endpoint = serverindex_details(local_node["node_path"])
    return {
        "name": name,
        "path": os.path.realpath(path),
        "install_root": os.path.realpath(install_root),
        "type": kind,
        "owner": path_owner(path),
        "cell": cell,
        "node": node,
        "host": endpoint.get("host") or about.get("host", ""),
        "servers": servers,
        "soap_port": endpoint.get("soap_port") if kind == "dmgr" else None,
        "serverindex": endpoint.get("path", ""),
    }
