#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: smtp_report
short_description: Send a detailed WebSphere automation report by SMTP
version_added: "0.1.0"
description:
  - Sends plain-text and optional HTML reports through an authenticated or relay SMTP server.
  - Runs well with delegate_to localhost inside an AWX execution environment.
options:
  host:
    description: SMTP relay hostname.
    type: str
    required: true
  port:
    description: SMTP relay port.
    type: int
    default: 25
  username:
    description: Optional SMTP username.
    type: str
  password:
    description: Optional SMTP password.
    type: str
  starttls:
    description: Upgrade a plain connection with STARTTLS.
    type: bool
    default: false
  ssl:
    description: Open an implicit TLS SMTP connection.
    type: bool
    default: false
  from_address:
    description: Message sender address.
    type: str
    required: true
  to:
    description: Primary recipients.
    type: list
    elements: str
    required: true
  cc:
    description: Carbon-copy recipients.
    type: list
    elements: str
    default: []
  subject:
    description: Message subject.
    type: str
    required: true
  body:
    description: Plain-text report body.
    type: str
    required: true
  html_body:
    description: Optional HTML alternative body.
    type: str
  attachments:
    description: Controller or execution-environment files to attach.
    type: list
    elements: path
    default: []
  timeout:
    description: SMTP connection timeout in seconds.
    type: int
    default: 30
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Email an AWX deployment report
  delegate_to: localhost
  become: false
  waslab.wasnd.smtp_report:
    host: "{{ was_smtp_host }}"
    port: "{{ was_smtp_port }}"
    username: "{{ was_smtp_username }}"
    password: "{{ was_smtp_password }}"
    starttls: true
    from_address: was-automation@example.com
    to: [was-operations@example.com]
    subject: "[WAS][SUCCESS] PayrollApplication"
    body: "{{ deployment_report }}"
'''

RETURN = r'''
message_id:
  description: Generated RFC message identifier.
  returned: always
  type: str
recipients:
  description: Normalized envelope recipients.
  returned: always
  type: list
  elements: str
'''

import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid

from ansible.module_utils.basic import AnsibleModule


def clean_header(value, name, module):
    if "\r" in value or "\n" in value:
        module.fail_json(msg="Email header contains a newline", header=name)
    return value


def normalize_addresses(values, field, module):
    expanded = []
    for value in values:
        expanded.extend(str(value).replace(";", ",").split(","))
    addresses = []
    for unused_name, address in getaddresses(expanded):
        address = address.strip()
        if not address or "@" not in address or "\r" in address or "\n" in address:
            module.fail_json(msg="Invalid email recipient", field=field, value=address)
        if address not in addresses:
            addresses.append(address)
    return addresses


def add_attachment(message, path, module):
    if not os.path.isfile(path):
        module.fail_json(msg="Email attachment does not exist", path=path)
    content_type, encoding = mimetypes.guess_type(path)
    if content_type is None or encoding is not None:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)
    with open(path, "rb") as stream:
        message.add_attachment(
            stream.read(),
            maintype=maintype,
            subtype=subtype,
            filename=os.path.basename(path),
        )


def main():
    module = AnsibleModule(
        argument_spec={
            "host": {"type": "str", "required": True},
            "port": {"type": "int", "default": 25},
            "username": {"type": "str"},
            "password": {"type": "str", "no_log": True},
            "starttls": {"type": "bool", "default": False},
            "ssl": {"type": "bool", "default": False},
            "from_address": {"type": "str", "required": True},
            "to": {"type": "list", "elements": "str", "required": True},
            "cc": {"type": "list", "elements": "str", "default": []},
            "subject": {"type": "str", "required": True},
            "body": {"type": "str", "required": True},
            "html_body": {"type": "str"},
            "attachments": {"type": "list", "elements": "path", "default": []},
            "timeout": {"type": "int", "default": 30},
        },
        mutually_exclusive=[["starttls", "ssl"]],
        required_together=[["username", "password"]],
        supports_check_mode=True,
    )
    sender = clean_header(module.params["from_address"], "From", module)
    subject = clean_header(module.params["subject"], "Subject", module)
    to_addresses = normalize_addresses(module.params["to"], "to", module)
    cc_addresses = normalize_addresses(module.params["cc"], "cc", module)
    if not to_addresses:
        module.fail_json(msg="At least one primary recipient is required")

    message = EmailMessage()
    message_id = make_msgid(domain=sender.split("@", 1)[-1])
    message["Message-ID"] = message_id
    message["From"] = sender
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    message["Subject"] = subject
    message.set_content(module.params["body"])
    if module.params["html_body"]:
        message.add_alternative(module.params["html_body"], subtype="html")
    for path in module.params["attachments"]:
        add_attachment(message, path, module)

    recipients = to_addresses + cc_addresses
    if module.check_mode:
        module.exit_json(changed=False, message_id=message_id, recipients=recipients)
    smtp_class = smtplib.SMTP_SSL if module.params["ssl"] else smtplib.SMTP
    kwargs = {
        "host": module.params["host"],
        "port": module.params["port"],
        "timeout": module.params["timeout"],
    }
    if module.params["ssl"]:
        kwargs["context"] = ssl.create_default_context()
    try:
        with smtp_class(**kwargs) as client:
            client.ehlo()
            if module.params["starttls"]:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if module.params["username"]:
                client.login(module.params["username"], module.params["password"])
            client.send_message(message, from_addr=sender, to_addrs=recipients)
    except (OSError, smtplib.SMTPException) as exc:
        module.fail_json(
            msg="SMTP report delivery failed",
            error_type=exc.__class__.__name__,
            error=str(exc),
            host=module.params["host"],
            port=module.params["port"],
            recipients=recipients,
        )
    module.exit_json(changed=True, message_id=message_id, recipients=recipients)


if __name__ == "__main__":
    main()
