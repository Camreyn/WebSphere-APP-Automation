# Licensing and media boundary

## Runnable WebSphere Base target

The `was-base` service derives locally from IBM's official public traditional
WebSphere image, pinned as
`icr.io/appcafe/websphere-traditional:9.0.5.28`. The image reports offering ID
`BASE`, package `com.ibm.websphere.ILAN.v90`, and traditional WAS 9.0.5.28.
IBM's ILAN terms apply to use of that image; consult IBM's current
[traditional WAS product offerings](https://www.ibm.com/docs/en/was-nd/9.0.5?topic=ppi-product-offerings-supported-operating-systems)
and license documentation before using it outside this local lab.
This repository stores only a Dockerfile wrapper and does not copy IBM image
layers into source control.

## Network Deployment target

IBM WebSphere Application Server Network Deployment 9 is proprietary software.
This repository contains no IBM program binaries, repository packages, license
files, credentials, or download automation. A user with appropriate IBM
entitlement must supply Installation Manager and WebSphere ND repositories.

The image build passes IBM's `-acceptLicense` option only after those authorized
files are deliberately placed under `artifacts/ibm`. That action means the user
is accepting the terms applicable to their media; this project grants no IBM
license. The build rejects Base-only media, Liberty, a wrong product edition,
and a version other than the configured `9.0.5.28` maintenance level.

The `waslab.wasnd` collection contains automation code only. Its install role
discovers user-supplied repositories below `/was855` (configurable), invokes
IBM Installation Manager locally on the managed host, and validates the actual
installed edition and version. Building the collection does not bundle IBM
media or installed product files.

AWX is open source. This lab uses AWX because Red Hat Ansible Automation
Platform is a separately licensed commercial product. AWX is suitable for
learning controller workflows, but it is not a byte-for-byte AAP replacement.
