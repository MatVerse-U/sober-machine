#!/usr/bin/env node
import { lstat, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { signTask, validateTask } from '../tools/matverse-sober-mcp.mjs';

function usage() {
  return [
    'Usage:',
    '  node scripts/approve-task.mjs --input task.json --output approved-task.json [--approver NAME] [--expires-in-minutes 30]',
    '',
    'Required environment:',
    '  MATVERSE_ALLOWED_REPOS=owner/repo[,owner/repo]',
    '  MATVERSE_APPROVAL_PRIVATE_KEY_FILE=/secure/local/approval-private-key.txt',
    '  MATVERSE_APPROVAL_PUBLIC_KEY_FILE=/secure/local/approval-public-key.txt',
    'Optional:',
    '  MATVERSE_BASE_BRANCH=main',
  ].join('\n');
}

function parseArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith('--')) {
      throw new Error(`unexpected argument: ${key}`);
    }
    const value = argv[index + 1];
    if (value === undefined || value.startsWith('--')) {
      throw new Error(`missing value for ${key}`);
    }
    options[key.slice(2)] = value;
    index += 1;
  }
  return options;
}

async function readLocalKeyFile(environmentName) {
  const configured = process.env[environmentName];
  if (typeof configured !== 'string' || !configured.trim()) {
    throw new Error(`${environmentName} is required`);
  }
  const filePath = resolve(configured);
  const metadata = await lstat(filePath);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error(`${environmentName} must reference a regular local file`);
  }
  const value = (await readFile(filePath, 'utf8')).trim();
  if (!value) {
    throw new Error(`${environmentName} is empty`);
  }
  return value;
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (!options.input || !options.output) {
    throw new Error(usage());
  }

  const privateKey = await readLocalKeyFile('MATVERSE_APPROVAL_PRIVATE_KEY_FILE');
  const publicKey = await readLocalKeyFile('MATVERSE_APPROVAL_PUBLIC_KEY_FILE');
  const approvalEnvironment = { ...process.env, MATVERSE_APPROVAL_PUBLIC_KEY: publicKey };

  const inputPath = resolve(options.input);
  const outputPath = resolve(options.output);
  if (inputPath === outputPath) {
    throw new Error('output must be a new file; input is never overwritten');
  }
  const task = JSON.parse(await readFile(inputPath, 'utf8'));
  const unsignedDecision = validateTask(task, approvalEnvironment);
  if (unsignedDecision.decision === 'BLOCK') {
    throw new Error(`task is invalid: ${unsignedDecision.reasons.join('; ')}`);
  }

  const approvedTask = signTask(task, privateKey, {
    approver: options.approver ?? 'human',
    expiresInMinutes: Number(options['expires-in-minutes'] ?? 30),
  });
  const decision = validateTask(approvedTask, approvalEnvironment);
  if (decision.decision !== 'ALLOW') {
    throw new Error(`signed task did not validate: ${decision.reasons.join('; ')}`);
  }

  await writeFile(outputPath, `${JSON.stringify(approvedTask, null, 2)}\n`, {
    encoding: 'utf8',
    mode: 0o600,
    flag: 'wx',
  });
  process.stdout.write(`Approved task written to ${outputPath}\nTask fingerprint: ${decision.task_fingerprint}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
