# Bundled PDF samples

## Standard text-layer sample

`nist-cloud-computing.pdf` is the unmodified seven-page publication:

Peter Mell and Timothy Grance (2011), *The NIST Definition of Cloud Computing*,
NIST Special Publication 800-145, National Institute of Standards and Technology.
[DOI](https://doi.org/10.6028/NIST.SP.800-145) ·
[Original PDF](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-145.pdf)

Republished courtesy of the National Institute of Standards and Technology.
See [NIST's technical-series publication reuse terms](https://www.nist.gov/open/license).
The publication itself states on printed page 1 that it is not subject to
copyright and requests attribution. This is a test fixture, not current security
or deployment guidance.

- SHA-256: `7b0c1a9fdfc67218b8ba2098f448c100c27070db91736b3c87fed63bfa21d418`
- Size: 85,781 bytes; seven pages, all with extractable text.
- Setup sample tests use physical PDF page 6 (printed page 2), which contains
  the cloud-computing definition and its characteristics. It has substantial
  text for both text-layer extraction and rendered-image OCR tests.
- `make demo-data` copies the full PDF into `example-documents` without a download.

## OCR sample

`purcell.pdf` remains available as the existing scanned/image-only example.
Use it for OCR testing, not as evidence that a text-layer-only reader is working.
It is no longer the default Setup or demo-data PDF. Existing imported copies
are not deleted or modified.
