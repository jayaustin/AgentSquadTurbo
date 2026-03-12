#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import process from "node:process";

function resolvePythonCommand() {
  const explicit = process.env.PYTHON;
  const candidates = [];
  if (explicit) {
    candidates.push([explicit]);
  }
  candidates.push(["py", "-3"], ["python"], ["python3"]);

  for (const candidate of candidates) {
    const [command, ...baseArgs] = candidate;
    const check = spawnSync(command, [...baseArgs, "--version"], {
      stdio: "ignore",
      windowsHide: true,
    });
    if (check.status === 0) {
      return candidate;
    }
  }
  return null;
}

const args = process.argv.slice(2);
if (!args.length) {
  console.error("Usage: node runner/scripts/run-python-module.mjs <python-module> [module-args...]");
  process.exit(1);
}

const python = resolvePythonCommand();
if (!python) {
  console.error(
    "Python 3 was not found on PATH. Install Python 3 or set PYTHON to an executable path."
  );
  process.exit(1);
}

const [moduleName, ...moduleArgs] = args;
const [pythonCommand, ...pythonBaseArgs] = python;
const child = spawn(
  pythonCommand,
  [...pythonBaseArgs, "-m", moduleName, ...moduleArgs],
  {
    stdio: "inherit",
    windowsHide: false,
  }
);

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

