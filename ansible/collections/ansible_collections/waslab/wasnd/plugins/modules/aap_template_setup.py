#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: aap_template_setup
short_description: Configure this project's operational AAP job templates
version_added: "0.1.0"
description:
  - Reads the Project, Inventory, and Execution Environment from the job
    template that launched the current setup playbook.
  - Idempotently creates or updates job templates, credential associations,
    and surveys from a repository-owned definition.
  - Can keep setup credentials off generated jobs and enable AAP's native
    credential prompt for operational launches.
options:
  controller_host:
    description: Base URL of the AAP controller or platform gateway.
    type: str
    required: true
  oauth_token:
    description: OAuth bearer token used to call the AAP API.
    type: str
    no_log: true
  controller_username:
    description: Controller username used when an OAuth token is not supplied.
    type: str
  controller_password:
    description: Controller password used when an OAuth token is not supplied.
    type: str
    no_log: true
  controller_api_prefix:
    description:
      - Controller API prefix.
      - C(auto) tries the AAP platform gateway route and then the direct
        Automation Controller or AWX route.
    type: str
    default: auto
  validate_certs:
    description: Validate the TLS certificate presented by AAP.
    type: bool
    default: true
  setup_template_id:
    description: ID of the AAP job template running this setup playbook.
    type: int
    required: true
  definition:
    description: Desired job templates and surveys loaded from the repository.
    type: dict
    required: true
  timeout:
    description: HTTP request timeout in seconds.
    type: int
    default: 90
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Reconcile operational templates with the repository definition
  waslab.wasnd.aap_template_setup:
    controller_host: "{{ lookup('ansible.builtin.env', 'CONTROLLER_HOST') }}"
    oauth_token: "{{ lookup('ansible.builtin.env', 'CONTROLLER_OAUTH_TOKEN') }}"
    setup_template_id: "{{ awx_job_template_id }}"
    definition: "{{ controller_setup_definition }}"
'''

RETURN = r'''
api_prefix:
  description: Discovered Automation Controller API prefix.
  returned: always
  type: str
context:
  description: Project, inventory, organization, and execution environment inherited from setup.
  returned: always
  type: dict
credential_mode:
  description: Whether generated templates inherit credentials or prompt at launch.
  returned: always
  type: str
templates:
  description: Reconciliation result for every managed job template.
  returned: always
  type: list
  elements: dict
copied_credentials:
  description: Operational credentials inherited by generated templates.
  returned: always
  type: list
  elements: str
copied_credential_types:
  description: Types of the operational credentials inherited by generated templates.
  returned: always
  type: list
  elements: str
excluded_credentials:
  description: Setup-only credentials not copied to generated templates.
  returned: always
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._controller import (
    ControllerApi,
    ControllerError,
    configure_controller_templates,
)


def main():
    module = AnsibleModule(
        argument_spec={
            "controller_host": {"type": "str", "required": True},
            "oauth_token": {"type": "str", "default": "", "no_log": True},
            "controller_username": {"type": "str", "default": ""},
            "controller_password": {"type": "str", "default": "", "no_log": True},
            "controller_api_prefix": {"type": "str", "default": "auto"},
            "validate_certs": {"type": "bool", "default": True},
            "setup_template_id": {"type": "int", "required": True},
            "definition": {"type": "dict", "required": True},
            "timeout": {"type": "int", "default": 90},
        },
        supports_check_mode=True,
    )

    try:
        api = ControllerApi(
            host=module.params["controller_host"],
            oauth_token=module.params["oauth_token"],
            username=module.params["controller_username"],
            password=module.params["controller_password"],
            validate_certs=module.params["validate_certs"],
            timeout=module.params["timeout"],
        )
        setup_template = api.discover(
            module.params["setup_template_id"],
            module.params["controller_api_prefix"],
        )
        result = configure_controller_templates(
            api,
            setup_template,
            module.params["definition"],
            check_mode=module.check_mode,
        )
        module.exit_json(**result)
    except ControllerError as exc:
        module.fail_json(msg=str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        module.fail_json(msg="Invalid controller setup definition: %s" % exc)


if __name__ == "__main__":
    main()
