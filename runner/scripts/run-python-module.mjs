#!/usr/bin/env node

import { spawn } from "node:child_process";
import process from "node:process";
import { pythonNotFoundMessage, resolvePythonCommand } from "./python-command.mjs";

const args = process.argv.slice(2);
if (!args.length) {
  console.error("Usage: node runner/scripts/run-python-module.mjs <python-module> [module-args...]");
  process.exit(1);
}

const python = resolvePythonCommand();
if (!python) {
  console.error(pythonNotFoundMessage());
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
