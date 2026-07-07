#!/usr/bin/env node
import { generateKeyPairSync } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

function usage() {
  return 'Usage: node scripts/generate-approval-keypair.mjs --output-dir /secure/local/directory';
}

function parseArguments(argv) {
  if (argv.length !== 2 || argv[0] !== '--output-dir' || !argv[1]) {
    throw new Error(usage());
  }
  return { outputDir: argv[1] };
}

async function main() {
  const { outputDir } = parseArguments(process.argv.slice(2));
  const directory = resolve(outputDir);
  await mkdir(directory, { recursive: true, mode: 0o700 });

  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const privateEncoded = privateKey.export({ format: 'der', type: 'pkcs8' }).toString('base64url');
  const publicEncoded = publicKey.export({ format: 'der', type: 'spki' }).toString('base64url');

  const privatePath = resolve(directory, 'approval-private-key.txt');
  const publicPath = resolve(directory, 'approval-public-key.txt');
  await writeFile(privatePath, `${privateEncoded}\n`, { encoding: 'utf8', mode: 0o600, flag: 'wx' });
  await writeFile(publicPath, `${publicEncoded}\n`, { encoding: 'utf8', mode: 0o644, flag: 'wx' });

  process.stdout.write([
    `Private signing key: ${privatePath}`,
    `Public verification key: ${publicPath}`,
    'Keep the private signing key outside Kilo, GitHub, chat, and the repository.',
  ].join('\n') + '\n');
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
