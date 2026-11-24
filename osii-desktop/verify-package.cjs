'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { promisify } = require('node:util');
const execFile = promisify(require('node:child_process').execFile);
const { Arch } = require('builder-util');

module.exports = async context => {
  const windows = process.platform === 'win32' && process.arch === 'x64'
    && context.electronPlatformName === 'win32' && context.arch === Arch.x64;
  const mac = process.platform === 'darwin' && process.arch === 'arm64'
    && context.electronPlatformName === 'darwin' && context.arch === Arch.arm64;
  if (!windows && !mac) throw new Error('Build Standalone on Windows x64 or Apple Silicon for the matching native target.');
  const root = path.join(__dirname, 'resources/runtime/osii-runtime');
  if (windows) {
    const executable = await fs.readFile(path.join(root, 'osii-runtime.exe'));
    if (executable.subarray(0, 2).toString() !== 'MZ' || executable.readUInt16LE(executable.readUInt32LE(0x3c) + 4) !== 0x8664) {
      throw new Error('The bundled Python executable is not a Windows x64 binary.');
    }
  } else {
    for (const executable of ['osii-runtime', '_internal/ocr/tesseract', '_internal/embedding/llama-server']) {
      await execFile('/usr/bin/lipo', ['-verify_arch', 'arm64', path.join(root, executable)]);
    }
  }
  const manifest = JSON.parse(await fs.readFile(path.join(root, '_internal/release.json'), 'utf8'));
  if (manifest.version !== require('./package.json').version || manifest.target !== (windows ? 'windows-x64' : 'macos-arm64')) {
    throw new Error('Rebuild the frozen runtime: its release version or platform does not match the installer.');
  }
  await fs.access(path.join(root, '_internal/dashboard/index.html'));
  const platformFiles = windows
    ? ['llama-server.exe', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll']
    : ['llama-server', 'libllama-server-impl.dylib', 'libggml-cpu.1.dylib'];
  await fs.access(path.join(root, '_internal/ocr', windows ? 'tesseract.exe' : 'tesseract'));
  for (const name of ['model.gguf', 'NOTICE.txt', ...platformFiles]) {
    await fs.access(path.join(root, '_internal/embedding', name));
  }
};
