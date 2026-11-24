# Optional OSII processor modules

This branch is a download catalog, not a standalone OSII installation.

| Module | What it does |
| --- | --- |
| [whisper](whisper/README.md) | Transcribes local audio into timestamped text |
| [vlm-endpoint](vlm-endpoint/README.md) | Reads images and short PDFs using your OpenAI-compatible vision endpoint |
| [ocria](ocria/README.md) | Reads scans on the CPU using separately licensed OCRia-nano-1 weights |

## Install one module

1. [Download the ZIP](https://github.com/sandialabs/OSII/archive/refs/heads/osii-processor-modules.zip)
   and extract it outside your OSII checkout.
2. Copy the whole module directory you want from `osii-processor-modules/`
   into the same directory in your OSII checkout. For example, copy
   `osii-processor-modules/whisper/` to
   `<your-osii-checkout>/osii-processor-modules/whisper/`.
3. Follow that module's README to configure and enable it. No models,
   credentials, or shared dependency lockfiles are included.

**Copy folders; don't Git-merge this branch into your application.** This
catalog deliberately omits Core, the dashboard, and the rest of the application.

If your checkout reports that `enabled_by_default` is an unknown manifest
field, keep the module outside automatic discovery: copy it to
`<your-osii-checkout>/optional-processors/<module-name>/` instead. The same
directory depth preserves its reference to Core. Then use the module README's
manual start and Setup registration instructions.

### Fetch only one directory with Git

```sh
git clone --depth 1 --single-branch --branch osii-processor-modules --filter=blob:none --sparse https://github.com/sandialabs/OSII.git osii-module-download
git -C osii-module-download sparse-checkout set osii-processor-modules/whisper
```

Replace `whisper` with `vlm-endpoint` or `ocria` to fetch that module instead.
