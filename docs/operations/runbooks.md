# What are you trying to do?

You do not need to learn every OSII deployment path. Pick one task below. Each
runbook is a short checklist; the longer operations pages explain *why*.

| I want to… | Follow this |
| --- | --- |
| Use an approved OSII release on a Mac | [Mac launcher](runbook-desktop.md#mac-launcher) |
| Use an approved OSII release on Windows | [Windows launcher](runbook-desktop.md#windows-launcher) |
| Work on OSII source without containers | [Host-Python development](runbook-development.md#host-python-development) |
| Build and run containers directly | [Direct Compose](runbook-development.md#direct-compose-development) |
| Bring public changes into corporate GitLab | [Import public changes](runbook-releases.md#import-public-changes) |
| Publish a complete corporate version | [Full release](runbook-releases.md#full-corporate-release) |
| Change only Core, UI, Launcher, or one Toolbox image | [Component update](runbook-releases.md#component-update) |
| Point corporate Quay `:latest` at an approved release | [Promote latest](runbook-releases.md#promote-latest) |
| Return to a prior version | [Rollback](runbook-releases.md#rollback) |

**One release, two container architectures.** OSII's containers are Linux images
for AMD64 and ARM64. The Mac and Windows installers are launchers that pull the
appropriate Linux image through Podman; they are not separate container builds.
The launcher and deployment bundles use immutable version tags. Corporate
`:latest` is only a convenience alias after a tested release is approved.

**Which configuration belongs where?** The launcher chooses the document folder,
Quay images, and optional tools. Workbench **Setup** chooses model connections
and processing methods. Corporate deployment defaults live in a private,
non-secret `corporate/osii.toml`; passwords and API keys never belong there.

For details beyond the checklist, see [corporate delivery](corporate-deployment.md),
[image publishing](publishing-images.md), [model connections](../reference/model-providers.md),
and [shared drives](shared-drives.md).
