'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');

module.exports = async context => {
  if (process.platform !== 'win32' || process.arch !== 'x64' || context.electronPlatformName !== 'win32') {
    throw new Error('Build the Windows x64 installer on Windows x64, using scripts/build_standalone.py or GitHub CI.');
  }
  const root = path.join(__dirname, 'resources/runtime/osii-runtime');
  const executable = await fs.readFile(path.join(root, 'osii-runtime.exe'));
  if (executable.subarray(0, 2).toString() !== 'MZ' || executable.readUInt16LE(executable.readUInt32LE(0x3c) + 4) !== 0x8664) {
    throw new Error('The bundled Python executable is not a Windows x64 binary.');
  }
  const manifest = JSON.parse(await fs.readFile(path.join(root, '_internal/release.json'), 'utf8'));
  if (manifest.version !== require('./package.json').version || manifest.target !== 'windows-x64') {
    throw new Error('Rebuild the frozen runtime: its release version or platform does not match the installer.');
  }
  await fs.access(path.join(root, '_internal/dashboard/index.html'));
  await fs.access(path.join(root, '_internal/ocr/tesseract.exe'));
  for (const name of ['model.gguf', 'llama-server.exe', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'NOTICE.txt']) {
    await fs.access(path.join(root, '_internal/embedding', name));
  }
};
