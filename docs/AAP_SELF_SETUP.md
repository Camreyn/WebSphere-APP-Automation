# Configure AAP from inside AAP

This repository is self-configuring. Import it as an AAP Project, create one
small setup job template that runs `setup.yml`, and launch that template. The
playbook uses the AAP API from inside the job to create or update the
repository-managed operational job templates and their surveys.

No GitHub Actions workflow or external runner is involved. Network traffic is
limited to the connections AAP already needs: project synchronization from
GitHub and the setup job's connection back to its own AAP API.

## 1. Import the project

In Automation Controller, create or update a Project with these settings:

- **Source control type:** Git
- **Source control URL:** the URL of this repository in your GitHub installation
- **Source control branch:** the branch to operate from, normally `main`
- **Update revision on launch:** enabled if every setup run should use the
  latest committed definition

Sync the Project and confirm that `setup.yml` is offered as a playbook.

## 2. Create the controller credential

Create a credential using the built-in **Red Hat Ansible Automation Platform**
credential type. Point it at the same AAP instance and use an OAuth token whose
user can read the setup template and create or update job templates, surveys,
and credential associations in the template's organization.

Keep TLS certificate verification enabled when AAP uses a trusted certificate.
If the instance uses an internal certificate authority, add that CA to the
execution environment instead of disabling verification for production.

## 3. Create the one manual setup template

Create a job template such as **WAS - Setup Automation** with:

| Setting | Value |
| --- | --- |
| Inventory | The inventory containing all production WebSphere hosts |
| Project | The imported GitHub Project |
| Playbook | `setup.yml` |
| Execution Environment | The environment intended for the generated jobs |
| Credentials | AAP controller credential, Machine credential, WebSphere credential |

Attach any additional operational credential that every generated job should
inherit. The setup playbook requires at least two non-controller credentials,
including the **Machine** and **WebSphere Administrative Credential** types.
If your custom WebSphere credential type has a different name, update
`required_copied_credential_types` in `config/aap/controller_setup.yml`.

The generated templates inherit this setup template's Project, Inventory,
Execution Environment, and non-controller credentials. The controller API
credential is setup-only: the playbook deliberately does not attach it to the
operational templates, and removes it there if it was attached previously.
Credential associations are reconciled exactly, so replace or remove an
operational credential on the setup template before rerunning setup rather than
editing the generated templates directly.

## 4. Launch setup

Launch **WAS - Setup Automation**. A successful run reports the discovered API
route, inherited context, copied credentials, and whether each managed template
was created, updated, or already current.

The desired objects are declared in
`config/aap/controller_setup.yml`. The first setup run currently creates:

- **WAS - Reboot Nodes by Wave**, using
  `ansible/playbooks/was_wave_reboot.yml`
- its launch survey, including explicit reboot authorization and recovery
  timeouts

Run the setup template again after changing and syncing the repository. Existing
objects are patched only when their managed fields, credential associations, or
survey differ, so reruns are safe and idempotent.

## Production notes

- Restrict launch access to the setup template because its credential can
  change controller configuration.
- Scope the OAuth user to the smallest organization-level permissions that can
  manage the required templates and credential associations.
- Do not add the AAP controller credential to the generated reboot template.
- Use `controller_api_prefix` as an extra variable only if automatic discovery
  cannot choose between `/api/controller/v2` and `/api/v2` in your installation.
- AAP check mode previews template changes without issuing create, patch,
  association, or survey-update requests.
