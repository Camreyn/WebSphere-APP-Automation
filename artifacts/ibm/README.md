# IBM WebSphere ND installation media

This directory is an explicit licensed-media gate. It is ignored by Git except
for this README. Do not place employer-owned media here until the relevant IBM
entitlement owner has authorized its use in this local, nonproduction lab.

The image builder expects:

1. One Linux x86-64 IBM Installation Manager agent installer ZIP matching
   `agent.installer.linux.gtk.x86_64*.zip`.
2. Extracted IBM Installation Manager repositories somewhere below
   `artifacts/ibm/repositories/`. Each repository must contain a
   `repository.config` file.
3. Repositories that make these offerings available:
   - `com.ibm.websphere.ND.v90`
   - `com.ibm.java.jdk.v8`
4. The desired cumulative WebSphere fix-pack repository. The default lab target
   is 9.0.5.28, but matching the workplace fix pack is preferable.

Example layout:

```text
artifacts/ibm/
|-- agent.installer.linux.gtk.x86_64_1.9.x.zip
`-- repositories/
    |-- was-nd-base/repository.config
    |-- was-nd-fp-9.0.5.28/repository.config
    `-- java8/repository.config
```

The Docker build copies the media only into an intermediate builder stage. The
final runtime image contains the installed product but not the repository ZIPs.
The final image is still IBM-licensed software and must remain local/private.
