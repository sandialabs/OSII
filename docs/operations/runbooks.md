# What are you trying to do?

You do not need to learn every OSII deployment path. Pick one task below. Each
runbook is a short checklist; the longer operations pages explain *why*.

| I want to… | Follow this |
| --- | --- |
| Use an approved OSII release on a Mac | [Mac launcher](runbook-desktop.md#mac-launcher) |
| Use an approved OSII release on Windows | [Windows launcher](runbook-desktop.md#windows-launcher) |
| Work on OSII source without containers | [Host-Python development](runbook-development.md#host-python-development) |
| Build and run containers directly | [Direct Compose](runbook-development.md#direct-compose-development) |
| Pull a release without building anything, on Windows/Mac/Linux | [Published containers](runbook-development.md#use-published-containers-without-building) |
| Bring public changes into corporate GitLab | [Import public changes](runbook-releases.md#import-public-changes) |
| Release manually; there are no corporate runners yet | [Manual release checklist](runbook-releases.md) |
| Build only the component I changed | [Scope table](runbook-releases.md#choose-what-changed), then the same manual checklist |
| Create the first corporate release when imported tags are insufficient | [First corporate release](runbook-releases.md#first-corporate-release) |
| Understand signing or obtain the required identities | [Workstation signing](corporate-deployment.md#code-signing-on-workstations) |
| Decide which settings file to edit | [Configuration ownership](corporate-deployment.md#configuration-ownership-and-precedence) |
| Configure release automation later | [Future runner setup](corporate-deployment.md#configure-gitlab-once) |
| Recover from a failed release tag | [Failed-tag recovery](runbook-releases.md#failed-tag-recovery) |
| Point corporate Quay `:latest` at an approved release | [Promote latest](runbook-releases.md#promote-latest) |
| Return to a prior version | [Rollback](runbook-releases.md#rollback) |

**One release, two container architectures.** OSII's containers are Linux images
for AMD64 and ARM64. The Mac and Windows installers are launchers that pull the
appropriate Linux image through Podman; they are not separate container builds.
The launcher and deployment bundles use immutable version tags. Corporate
`:latest` is only a convenience alias after a tested release is approved.

**Today: manual publishing.** A tag does not produce a download when there are
no runners. The release maintainer builds only the scope's changed images,
copies unchanged images, builds signed launchers, uploads release files, and
reviews the catalog change. End users never need to perform these steps.

**Which configuration belongs where?** The reviewed launcher catalog defines
approved, digest-pinned Stack and Toolbox images. The launcher chooses a Stack,
document folder, and optional tools. Workbench **Setup** chooses model
connections and processing methods. Corporate deployment defaults live in a
private, non-secret `corporate/osii.toml`; passwords and API keys never belong
there.

For details beyond the checklist, see [corporate delivery](corporate-deployment.md),
[image publishing](publishing-images.md), [model connections](../reference/model-providers.md),
and [shared drives](shared-drives.md).
