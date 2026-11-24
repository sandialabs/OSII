# OSII Standalone

## Install and start

Use the Windows x64 installer from the project's release artifacts. A build
labeled **pilot** is unsigned and has not yet passed every broad-release gate;
follow your organization's software approval policy. The delivered artifact's
`validation.json` records signing and clean-Windows acceptance status.

1. Run `OSII-Standalone-Setup.exe`. It installs for your Windows account without
   an administrator prompt. The full payload is included; installation and
   baseline operation do not require an internet connection.
2. Open **OSII Standalone** from the Start menu.
3. Choose **Create library**, enter a name and select the document folder.
   A connected mapped drive or UNC path is supported for documents.
4. Select **Create and open library**. Open **Intake & Setup**, connect and
   test a language model, then add documents. OSII tests the included
   EmbeddingGemma model when it opens the library.
5. Select **Process files** and open the run report. When processing finishes,
   choose **Semantic** in Search options to search by meaning.

On an Apple Silicon Mac with macOS 15 or newer, open the Mac pilot disk image
and drag **OSII Standalone** into Applications. The pilot is ad hoc signed and
has no Apple notarization. macOS can require [approval on first launch](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac).
The app stores libraries and settings in `~/Library/Application Support/OSII Standalone`.

The installer includes the text-only EmbeddingGemma 2 model and its CPU
runtime. For offline processing, choose **Advanced → Advanced intake**, then
**Text, keywords and semantic search** or **Text and keywords (offline)**.
An existing saved embedding connection keeps precedence and can be tested
from Intake & Setup.

Do not install Python, uv, Node, Java, Tesseract, Podman or Docker for this app.
Ollama is separately installed and managed only when you choose to use it.
The application does not mount shares or store their Windows credentials.

Close the window to stop OSII and its helpers. The Library menu returns to the
library chooser; only one library is open at a time.

## Continue an existing library

Stop OSII-local first, including its workers. Choose **Open existing library**,
select its `.osii` directory, and select the matching document folder. Optionally
choose its existing configuration directory to reuse model settings and
`secrets.env`; otherwise the desktop profile gets fresh settings. No `.env` is
imported. Existing library identities, provenance, collections, text edits and
inventory evidence are preserved.

The `.osii` directory and its SQLite files must be on local disk. Documents can
remain on a share. Unsupported inventory or job schemas are rejected with a
message; the app does not migrate or replace them. Use the matching source
version and its explicit backup/migration workflow before trying again.

This branch's source launcher and desktop app share a library ownership lock.
Older OSII-local versions do not understand that lock and must be stopped
manually before switching applications.

## Included capabilities

| Capability | Standalone behavior |
| --- | --- |
| Native extraction | Text-layer PDF, DOCX, PPTX, XLSX, RTF and common text/data files |
| OCR | Full-page Tesseract for PDF, PNG, JPEG and TIFF; English, French, German, Spanish, Japanese, Korean, Simplified Chinese and Arabic |
| Offline | Direct file selection, keyword and semantic search, extractive previews and grounded answers, statistics and keywords |
| With an optional endpoint | Alternate embedding models, model-backed synthesis/chat, and existing model-dependent workflows |
| Preserved product interfaces | Browsing, collections, editing, provenance, reports and exports; Topic Explorer retains its existing requirements |
| Not bundled | Java/Tika, PostgreSQL, Banyan, OpenCV region OCR, specialist dataset analysis, Haystack, Ollama and generative LLM weights |

Background discovery follows the shared beta workflow and is archived.
Existing inventory records stay readable in their original SQLite database.
Use direct Intake for new batches.

Existing external Processor API services can be registered in Setup. The
installer does not download or install their dependencies. MCP is not started
automatically. Existing MCP clients remain a source/integration workflow;
the desktop's per-run protected API is not a stable public MCP endpoint.

## Data, diagnostics and updates

New application data lives under `%LOCALAPPDATA%\OSII`:

- `libraries/<id>/.osii`: canonical library and local operational state.
- `profiles/<id>/config`: model/processor settings and separately stored keys.
- `profiles/<id>/uploads`: explicitly uploaded originals.
- `logs`: bounded structured lifecycle logs.

An explicitly opened existing library stays in its original location.
Configuration is plaintext local data; keep keys outside source control.
The application uses Windows system certificate trust for model connections.
Explicit corporate proxy/CA environment settings remain supported, while
loopback traffic always bypasses proxies.

Use **Help → Export diagnostics** for a JSON report containing product version,
platform and fixed lifecycle fields. Document text, model output, credentials,
source paths and arbitrary child-process output are excluded. Failures must
not require users to install developer tools or manually kill guessed processes.

To update, close OSII and run the newer full installer. Uninstall removes the
application and preserves library/configuration data. Keep backups and older
installers. Binary rollback is supported only while data formats remain
compatible; it never reverses a migration.

## Build a Windows installer

These requirements apply to the **maintainer's build machine only**: Windows
11 x64, uv, Node.js 22.18+, 7-Zip, and Visual Studio C++ x64 build tools with
the app-local redistributable files. Use a checkout of `osii-standalone`.
GitHub's **Standalone Windows** workflow performs the same build and tests.

```powershell
uv sync --frozen --python 3.12 --all-packages --extra standalone-build --extra dev
uv run --no-sync python scripts/build_standalone.py --pilot
```

The output is `release/standalone/OSII-Standalone-Setup.exe`. An unsigned pilot
is suitable for controlled validation; it must not be labeled a signed release.
For a signed build, omit `--pilot` and supply `CSC_LINK` and `CSC_KEY_PASSWORD`
through the build machine's secret mechanism. CI uses the repository secrets
`OSII_WINDOWS_CERTIFICATE` and `OSII_WINDOWS_CERTIFICATE_PASSWORD`. Signed
packaging fails when signing is unavailable. Validate the signatures on the
installer, Electron executable and maintained Python executable.

Python dependencies are pinned in `uv.lock`, desktop/dashboard dependencies in
their npm lockfiles, and Windows OCR assets in `osii-desktop/ocr-lock.json`.
The latter pins the upstream installer archive and language data by SHA-256.
7-Zip extracts the verified runtime without installing Tesseract on the builder.
Do not replace a failed dependency fetch with an unverified download.

The processor source lives in `osii-processor-modules/embeddinggemma`.
The Standalone build fetches its pinned CPU engine and
quantized text weights using `osii-desktop/embedding-lock.json`. The packaged
payload includes the model and engine licenses and the app-local Visual C++
DLLs from the build tools. No weights are fetched at application startup.

For a version change, update Core and workspace service versions, the dashboard
and desktop package versions, and both dependency locks before building.
The asset-preparation step rejects mismatched product versions. The delivered
runtime contains dependency notices and Electron includes its own notices.

## Build a Mac pilot

Use Apple Silicon, macOS 15 or newer, Xcode Command Line Tools, uv, and Node.js
22.18 or newer. The **Standalone macOS** workflow builds on macOS 15.

```bash
uv sync --frozen --python 3.12 --all-packages --extra standalone-build --extra dev
uv run --no-sync --with cmake==4.3.2 python scripts/build_standalone.py --pilot
```

The result is `release/standalone/OSII-Standalone-macOS-arm64.dmg`. The build
compiles Tesseract with its pinned image libraries, packages the same OCR
languages and CPU EmbeddingGemma model as Windows, and tests the app copied
from the disk image. Intel Macs need a separate build.

## Validation and release gates

CI builds and tests the actual frozen distribution and installs the resulting
NSIS artifact. It checks native formats/OCR/FAISS, archived inventory preservation,
the offline processing flow and its sample, optional endpoint behavior, private API
and IPC boundaries, shutdown/restart, and data-preserving reinstall/uninstall.
It also checks that a fresh installed library ranks a relevant document for a
paraphrased query using the bundled model and can reopen its semantic index.
Windows Firewall blocks external traffic for the installer, the installed app,
and its model helpers. The runner stays connected so it can record results.
Clean, standard-user Windows acceptance remains a separate release gate.

Before broad distribution, record a run on a clean Windows 11 x64 VM with a
standard user, no developer tools, no separate OCR/model runtime, and networking
disabled after copying the installer:

- Install and open from the Start menu without elevation or downloads.
- Process the supported document/image formats; inspect PDF, mathematics and
  reports offline, then export artifacts.
- Open an existing compatible library and verify identity, collections, edits,
  provenance and canonical inventory. Reject concurrent ownership and invalid
  schemas without deleting evidence.
- Exercise Unicode/space paths, read-only originals, mapped/UNC documents and
  a disconnected share. Verify originals remain unchanged.
- Test a configured model endpoint on a separate connected run; disconnect it
  and verify baseline workflows remain usable.
- Terminate the app during OCR and queued processing; verify helpers stop and
  the library reopens with recoverable jobs and preserved results.
- Reinstall/update/uninstall and verify library/configuration preservation.
- Inspect exported diagnostics for sensitive content and verify publisher
  signatures under the target organization's Windows policy.

Record installer SHA-256, Git commit, Windows build, user privilege, results,
cold/warm startup times and idle memory. Signing and this acceptance record are
required before publishing a broad-release artifact. Pilots remain clearly
labeled. Publish the full installer, `SHA256SUMS.txt` and `validation.json` as
versioned GitHub Release assets; the identical files can be copied to an
approved internal file share. No automatic updater or registry is involved.
