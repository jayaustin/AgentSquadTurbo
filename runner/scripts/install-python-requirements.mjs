#!/usr/bin/env node

import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import process from "node:process";

import { pythonNotFoundMessage, resolvePythonCommand } from "./python-command.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, "..", "..");
const requirementsPath = resolve(repoRoot, "requirements.txt");
const args = new Set(process.argv.slice(2));
const checkOnly = args.has("--check");

if (process.env.SKIP_PYTHON_REQUIREMENTS_INSTALL === "1") {
  console.log("Skipping Python requirements install because SKIP_PYTHON_REQUIREMENTS_INSTALL=1.");
  process.exit(0);
}

if (!existsSync(requirementsPath)) {
  console.error(`requirements.txt was not found at ${requirementsPath}.`);
  process.exit(1);
}

const python = resolvePythonCommand();
if (!python) {
  console.error(pythonNotFoundMessage());
  process.exit(1);
}

const [pythonCommand, ...pythonBaseArgs] = python;
const pipCheck = spawnSync(
  pythonCommand,
  [...pythonBaseArgs, "-m", "pip", "--version"],
  {
    stdio: "ignore",
    windowsHide: true,
    cwd: repoRoot,
  }
);
if (pipCheck.status !== 0) {
  console.error(
    "pip is not available for the resolved Python interpreter. Install pip or point PYTHON to an interpreter with pip."
  );
  process.exit(1);
}

if (checkOnly) {
  console.log(
    JSON.stringify(
      {
        python_command: [pythonCommand, ...pythonBaseArgs],
        requirements_path: requirementsPath,
      },
      null,
      2
    )
  );
  process.exit(0);
}

const child = spawn(
  pythonCommand,
  [
    ...pythonBaseArgs,
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--requirement",
    requirementsPath,
  ],
  {
    stdio: "inherit",
    windowsHide: false,
    cwd: repoRoot,
  }
);

child.on("exit", code => {
  process.exit(code ?? 1);
});
