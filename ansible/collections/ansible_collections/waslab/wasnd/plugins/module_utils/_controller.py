# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


class ControllerError(Exception):
    pass


class ControllerApiError(ControllerError):
    def __init__(self, method, path, status, body):
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super(ControllerApiError, self).__init__(
            "AAP %s %s failed (%s): %s" % (method, path, status, body[:2000])
        )


class ControllerApi(object):
    def __init__(
        self,
        host,
        oauth_token="",
        username="",
        password="",
        validate_certs=True,
        timeout=90,
    ):
        self.host = host.rstrip("/") + "/"
        parsed_host = urlparse(self.host)
        if parsed_host.scheme not in ("http", "https") or not parsed_host.netloc:
            raise ControllerError(
                "controller_host must be a complete HTTP or HTTPS URL"
            )
        self.timeout = timeout
        self.api_prefix = None
        if oauth_token:
            self.authorization = "Bearer " + oauth_token
        elif username and password:
            raw = (username + ":" + password).encode("utf-8")
            self.authorization = "Basic " + base64.b64encode(raw).decode("ascii")
        else:
            raise ControllerError(
                "An OAuth token or controller username/password is required"
            )
        self.ssl_context = ssl.create_default_context()
        if not validate_certs:
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    def endpoint(self, resource):
        if not self.api_prefix:
            raise ControllerError("The controller API prefix has not been discovered")
        return "%s/%s/" % (self.api_prefix.rstrip("/"), resource.strip("/"))

    def absolute_url(self, path):
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.host, path.lstrip("/"))

    def request(self, method, path, payload=None, params=None):
        request_path = path
        if params:
            separator = "&" if "?" in request_path else "?"
            request_path += separator + urlencode(params, doseq=True)
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self.authorization,
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.absolute_url(request_path),
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(
                request,
                timeout=self.timeout,
                context=self.ssl_context,
            ) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise ControllerApiError(method.upper(), request_path, exc.code, body)
        except URLError as exc:
            raise ControllerError(
                "Unable to reach AAP at %s: %s" % (self.absolute_url(request_path), exc)
            )
        if not body:
            return {}
        try:
            return json.loads(body)
        except ValueError as exc:
            raise ControllerError(
                "AAP returned invalid JSON for %s: %s" % (request_path, exc)
            )

    def discover(self, setup_template_id, requested_prefix="auto"):
        if requested_prefix and requested_prefix != "auto":
            candidates = ["/" + requested_prefix.strip("/")]
        else:
            # AAP platform gateway routes controller under /api/controller/v2;
            # AWX and direct controller installations use /api/v2.
            candidates = ["/api/controller/v2", "/api/v2"]
        failures = []
        for candidate in candidates:
            self.api_prefix = candidate
            path = self.endpoint("job_templates") + str(setup_template_id) + "/"
            try:
                template = self.request("GET", path)
                if str(template.get("id")) == str(setup_template_id):
                    return template
                failures.append(
                    "%s did not return job template %s"
                    % (candidate, setup_template_id)
                )
            except ControllerError as exc:
                failures.append(str(exc))
        self.api_prefix = None
        raise ControllerError(
            "Could not discover the Automation Controller API route. "
            + " | ".join(failures)
        )

    def collection(self, resource, params=None):
        results = []
        next_path = self.endpoint(resource)
        next_params = dict(params or {})
        next_params.setdefault("page_size", 200)
        while next_path:
            payload = self.request("GET", next_path, params=next_params)
            results.extend(payload.get("results", []))
            next_path = payload.get("next")
            next_params = None
        return results


SURVEY_QUESTION_FIELDS = (
    "question_name",
    "question_description",
    "required",
    "type",
    "variable",
    "choices",
    "default",
    "min",
    "max",
    "new_question",
)


def normalized_survey(survey):
    if not survey:
        return {"name": "", "description": "", "spec": []}
    questions = []
    for question in survey.get("spec", []):
        normalized = {}
        for field in SURVEY_QUESTION_FIELDS:
            value = question.get(field)
            if field == "choices" and isinstance(value, str):
                value = value.rstrip("\n")
            normalized[field] = value
        questions.append(normalized)
    return {
        "name": survey.get("name", ""),
        "description": survey.get("description", ""),
        "spec": questions,
    }


def exact_named(items, name, organization=None):
    matches = [item for item in items if item.get("name") == name]
    if organization is not None:
        matches = [item for item in matches if item.get("organization") == organization]
    if len(matches) > 1:
        raise ControllerError("More than one AAP object is named %r" % name)
    return matches[0] if matches else None


def credential_type_name(api, credential, cache):
    summary_name = (
        credential.get("summary_fields", {})
        .get("credential_type", {})
        .get("name")
    )
    if summary_name:
        return summary_name
    type_id = credential.get("credential_type")
    if type_id not in cache:
        path = api.endpoint("credential_types") + str(type_id) + "/"
        cache[type_id] = api.request("GET", path).get("name", "")
    return cache[type_id]


def template_payload(template, context):
    payload = {
        "description": template.get("description", ""),
        "job_type": template.get("job_type", "run"),
        "inventory": context["inventory"],
        "project": context["project"],
        "playbook": template["playbook"],
        "execution_environment": context.get("execution_environment"),
        "verbosity": int(template.get("verbosity", 1)),
        "allow_simultaneous": bool(template.get("allow_simultaneous", False)),
        "ask_variables_on_launch": bool(
            template.get("ask_variables_on_launch", False)
        ),
        "survey_enabled": bool(template.get("survey")),
    }
    if "extra_vars" in template:
        payload["extra_vars"] = json.dumps(template["extra_vars"])
    return payload


def configure_controller_templates(api, setup_template, definition, check_mode=False):
    project_id = setup_template.get("project")
    inventory_id = setup_template.get("inventory")
    execution_environment_id = setup_template.get("execution_environment")
    organization_id = setup_template.get("organization")
    if not project_id or not inventory_id:
        raise ControllerError(
            "The setup job template must have both a Project and an Inventory"
        )
    if not organization_id:
        project_path = api.endpoint("projects") + str(project_id) + "/"
        organization_id = api.request("GET", project_path).get("organization")
    if not organization_id:
        raise ControllerError("Unable to determine the setup template organization")

    templates = definition.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ControllerError("Controller setup definition has no templates")
    if definition.get("version") != 1:
        raise ControllerError("Controller setup definition version must be 1")
    template_names = []
    for template in templates:
        if (
            not isinstance(template, dict)
            or not template.get("name")
            or not template.get("playbook")
        ):
            raise ControllerError("Every template requires name and playbook")
        if template.get("name") == setup_template.get("name"):
            raise ControllerError(
                "Managed template %r has the same name as the running setup template"
                % template["name"]
            )
        survey = template.get("survey")
        if survey is not None and (
            not isinstance(survey, dict) or not isinstance(survey.get("spec"), list)
        ):
            raise ControllerError(
                "Template %r has an invalid survey definition" % template["name"]
            )
        template_names.append(template["name"])
    duplicate_names = sorted(
        name for name in set(template_names) if template_names.count(name) > 1
    )
    if duplicate_names:
        raise ControllerError(
            "Controller setup contains duplicate template names: %s"
            % ", ".join(duplicate_names)
        )
    exclusions_value = definition.get("excluded_credential_types", [])
    required_types_value = definition.get("required_copied_credential_types", [])
    if not isinstance(exclusions_value, list) or not isinstance(
        required_types_value, list
    ):
        raise ControllerError("Credential type settings must be lists")
    exclusions = set(exclusions_value)
    minimum_credentials = int(definition.get("minimum_copied_credentials", 0))
    if minimum_credentials < 0:
        raise ControllerError("minimum_copied_credentials cannot be negative")
    required_credential_types = set(required_types_value)
    type_cache = {}

    setup_credentials = api.collection(
        "job_templates/%s/credentials" % setup_template["id"]
    )
    copied_credentials = []
    copied_credential_types = []
    excluded_credentials = []
    for credential in setup_credentials:
        type_name = credential_type_name(api, credential, type_cache)
        if type_name in exclusions:
            excluded_credentials.append(credential)
        else:
            copied_credentials.append(credential)
            copied_credential_types.append(type_name)
    if len(copied_credentials) < minimum_credentials:
        raise ControllerError(
            "The setup template has %s operational credential(s); at least %s are required"
            % (len(copied_credentials), minimum_credentials)
        )
    missing_credential_types = sorted(
        required_credential_types - set(copied_credential_types)
    )
    if missing_credential_types:
        raise ControllerError(
            "The setup template is missing required operational credential types: %s"
            % ", ".join(missing_credential_types)
        )

    context = {
        "organization": organization_id,
        "project": project_id,
        "inventory": inventory_id,
        "execution_environment": execution_environment_id,
    }
    overall_changed = False
    configured = []

    for template in templates:
        name = template["name"]
        desired = template_payload(template, context)
        candidates = api.collection(
            "job_templates",
            {"name": name, "organization": organization_id},
        )
        existing = exact_named(candidates, name, organization_id)
        if existing and existing.get("id") == setup_template.get("id"):
            raise ControllerError(
                "Managed template %r resolves to the running setup template; "
                "use distinct names" % name
            )
        action = "unchanged"
        target = existing
        changed_fields = []
        if existing is None:
            overall_changed = True
            action = "created"
            changed_fields = sorted(desired.keys())
            if not check_mode:
                target = api.request(
                    "POST",
                    api.endpoint("job_templates"),
                    {"name": name, **desired},
                )
        else:
            changed_fields = [
                key for key, value in desired.items() if existing.get(key) != value
            ]
            if changed_fields:
                overall_changed = True
                action = "updated"
                if not check_mode:
                    target = api.request("PATCH", existing["url"], desired)

        credentials_added = []
        credentials_removed = []
        survey_changed = False
        target_id = target.get("id") if target else None
        if target_id:
            credential_resource = "job_templates/%s/credentials" % target_id
            target_credentials = api.collection(credential_resource)
            target_ids = set(item["id"] for item in target_credentials)
            copied_ids = set(item["id"] for item in copied_credentials)
            # Remove stale credentials before adding replacements because AAP
            # permits only one credential for some kinds, including Machine.
            for credential in target_credentials:
                if credential["id"] not in copied_ids:
                    overall_changed = True
                    credentials_removed.append(credential["name"])
                    if not check_mode:
                        api.request(
                            "POST",
                            api.endpoint(credential_resource),
                            {"id": credential["id"], "disassociate": True},
                        )
            for credential in copied_credentials:
                if credential["id"] not in target_ids:
                    overall_changed = True
                    credentials_added.append(credential["name"])
                    if not check_mode:
                        api.request(
                            "POST",
                            api.endpoint(credential_resource),
                            {"id": credential["id"]},
                        )

            desired_survey = template.get("survey")
            if desired_survey:
                survey_path = api.endpoint("job_templates") + str(target_id) + "/survey_spec/"
                current_survey = api.request("GET", survey_path)
                survey_changed = normalized_survey(current_survey) != normalized_survey(
                    desired_survey
                )
                if survey_changed:
                    overall_changed = True
                    if not check_mode:
                        api.request("POST", survey_path, desired_survey)
        else:
            # A not-yet-created template in check mode necessarily needs its
            # credential associations and survey applied when run for real.
            credentials_added = [item["name"] for item in copied_credentials]
            survey_changed = bool(template.get("survey"))

        if action == "unchanged" and (
            credentials_added or credentials_removed or survey_changed
        ):
            action = "updated"

        configured.append(
            {
                "name": name,
                "id": target_id,
                "action": action,
                "changed_fields": changed_fields,
                "credentials_added": credentials_added,
                "credentials_removed": credentials_removed,
                "survey_changed": survey_changed,
            }
        )

    return {
        "changed": overall_changed,
        "api_prefix": api.api_prefix,
        "context": context,
        "copied_credentials": [item["name"] for item in copied_credentials],
        "copied_credential_types": copied_credential_types,
        "excluded_credentials": [item["name"] for item in excluded_credentials],
        "templates": configured,
    }
