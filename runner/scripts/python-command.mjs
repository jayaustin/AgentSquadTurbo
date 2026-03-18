#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import process from "node:process";

export function resolvePythonCommand() {
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

export function pythonNotFoundMessage() {
  return "Python 3 was not found on PATH. Install Python 3 or set PYTHON to an executable path.";
}
