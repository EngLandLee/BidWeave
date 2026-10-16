/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Generate notices for the packages that are imported by the browser bundle.
 * Package versions and license metadata come from package-lock.json; license
 * files are copied byte-for-byte from the installed package directories.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const lockPath = path.join(appRoot, "package-lock.json");
const sourceRoot = path.join(appRoot, "src");
const distRoot = path.join(appRoot, "dist");
const noticesPath = path.join(distRoot, "THIRD-PARTY-NOTICES.txt");
const licensesRoot = path.join(distRoot, "licenses");
const packagePrefix = "node_modules/";
const licenseFilePattern = /^(?:LICENSE|LICENCE|COPYING|NOTICE)(?:$|[._ -])/i;
const packageSpecifierPattern =
  /\b(?:from|import|require)\s*\(?\s*["']([^"']+)["']/g;
const cssImportPattern = /@import\s*["']([^"']+)["']/g;

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isWithin(parent, child) {
  const relative = path.relative(parent, child);
  return (
    relative === "" ||
    (relative !== ".." &&
      !relative.startsWith(`..${path.sep}`) &&
      !path.isAbsolute(relative))
  );
}

function guardedPath(parent, relative, description) {
  const resolved = path.resolve(parent, relative);
  if (!isWithin(parent, resolved))
    fail(`refusing ${description} outside ${parent}: ${relative}`);
  return resolved;
}

function assertDirectory(directory, description) {
  let stat;
  try {
    stat = fs.lstatSync(directory);
  } catch (error) {
    fail(`${description} is not available: ${error.message}`);
  }
  if (!stat.isDirectory() || stat.isSymbolicLink())
    fail(`${description} must be a real directory: ${directory}`);
}

function packageNameFromKey(key) {
  if (!key.startsWith(packagePrefix)) return null;
  const packageName = key.slice(
    key.lastIndexOf(packagePrefix) + packagePrefix.length,
  );
  if (
    !packageName ||
    packageName === "." ||
    packageName === ".." ||
    packageName.includes("/../") ||
    packageName.startsWith("../")
  )
    return null;
  const parts = packageName.split("/");
  if (parts[0].startsWith("@") ? parts.length !== 2 : parts.length !== 1)
    return null;
  return packageName;
}

function packageNameFromSpecifier(specifier) {
  if (
    specifier.startsWith(".") ||
    specifier.startsWith("/") ||
    specifier.startsWith("#")
  )
    return null;
  const parts = specifier.split("/");
  if (specifier.startsWith("@"))
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : null;
  return parts[0] || null;
}

function readJson(file, description) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    fail(`could not read ${description}: ${error.message}`);
  }
}

function collectSourceFiles(directory) {
  assertDirectory(directory, "source directory");
  const files = [];
  const walk = (current) => {
    const entries = fs
      .readdirSync(current, { withFileTypes: true })
      .sort((a, b) => compareText(a.name, b.name));
    for (const entry of entries) {
      if (entry.isSymbolicLink()) continue;
      const fullPath = guardedPath(
        appRoot,
        path.relative(appRoot, path.join(current, entry.name)),
        "source path",
      );
      if (entry.isDirectory()) walk(fullPath);
      else if (entry.isFile() && /\.(?:[cm]?[jt]sx?|css)$/i.test(entry.name))
        files.push(fullPath);
    }
  };
  walk(directory);
  return files;
}

function discoverRuntimeRoots() {
  const roots = new Set();
  for (const sourceFile of collectSourceFiles(sourceRoot)) {
    let source;
    try {
      source = fs.readFileSync(sourceFile, "utf8");
    } catch (error) {
      fail(`could not read source file ${sourceFile}: ${error.message}`);
    }
    for (const pattern of [packageSpecifierPattern, cssImportPattern]) {
      pattern.lastIndex = 0;
      for (const match of source.matchAll(pattern)) {
        const name = packageNameFromSpecifier(match[1]);
        if (name) roots.add(name);
      }
    }
  }
  if (roots.size === 0)
    fail("no package imports were found in the browser source");
  return [...roots].sort(compareText);
}

function resolvePackageKey(packages, parentKey, dependencyName) {
  let current = parentKey;
  while (true) {
    const candidate = current
      ? `${current}/node_modules/${dependencyName}`
      : `${packagePrefix}${dependencyName}`;
    if (Object.hasOwn(packages, candidate)) return candidate;
    const marker = current.lastIndexOf(`/${packagePrefix}`);
    if (marker < 0) {
      if (!current) break;
      current = "";
    } else {
      current = current.slice(0, marker);
    }
  }

  // A package imported from source should normally be hoisted at the root.
  // This fallback handles a lockfile that records only a nested peer install.
  return (
    Object.keys(packages)
      .filter((key) => packageNameFromKey(key) === dependencyName)
      .sort((a, b) => a.length - b.length || compareText(a, b))[0] ?? null
  );
}

function dependencyNames(entry) {
  const names = new Set([
    ...Object.keys(entry.dependencies ?? {}),
    ...Object.keys(entry.optionalDependencies ?? {}),
    ...Object.keys(entry.peerDependencies ?? {}),
  ]);
  return [...names].sort(compareText);
}

function stableLicenseLabel(value) {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (Array.isArray(value) && value.length) return JSON.stringify(value);
  if (value && typeof value === "object") return JSON.stringify(value);
  return null;
}

function findLicenseFiles(packageDirectory) {
  const files = fs
    .readdirSync(packageDirectory, { withFileTypes: true })
    .filter(
      (entry) =>
        entry.isFile() &&
        !entry.isSymbolicLink() &&
        licenseFilePattern.test(entry.name),
    )
    .map((entry) => entry.name)
    .sort(compareText);
  for (const file of files) {
    const source = guardedPath(packageDirectory, file, "license source");
    const content = fs.readFileSync(source);
    if (
      content.length === 0 ||
      content.includes(0) ||
      content.toString("utf8").trim().length === 0
    ) {
      fail(`license candidate is not inspectable text: ${source}`);
    }
  }
  return files;
}

function packageSlug(name, version) {
  const slug = `${name}@${version}`
    .replaceAll("/", "__")
    .replace(/[^A-Za-z0-9._@+-]/g, "_");
  if (!slug || slug === "." || slug === "..")
    fail(`unsafe package license directory name for ${name}@${version}`);
  return slug;
}

function main() {
  assertDirectory(appRoot, "application root");
  assertDirectory(distRoot, "Vite output directory");
  if (fs.existsSync(noticesPath) && fs.lstatSync(noticesPath).isSymbolicLink())
    fail(`refusing to replace symlinked notices file: ${noticesPath}`);

  const lock = readJson(lockPath, "package-lock.json");
  const packages = lock.packages;
  if (!packages || typeof packages !== "object" || !packages[""])
    fail("package-lock.json has no package metadata");

  const selected = new Map();
  const visit = (key, importedBy) => {
    if (selected.has(key)) return;
    const entry = packages[key];
    const name = packageNameFromKey(key);
    if (!entry || !name)
      fail(
        `cannot resolve installed package metadata for ${importedBy}: ${key}`,
      );
    if (entry.dev === true)
      fail(
        `browser source resolves to dev-only package ${name}@${entry.version}`,
      );
    const packageDirectory = guardedPath(appRoot, key, "installed package");
    assertDirectory(packageDirectory, `installed package ${name}`);
    const packageJsonPath = guardedPath(
      packageDirectory,
      "package.json",
      "package metadata",
    );
    const packageJson = readJson(packageJsonPath, `${name}/package.json`);
    const version = entry.version ?? packageJson.version;
    const license = stableLicenseLabel(entry.license ?? packageJson.license);
    if (!version)
      fail(`installed package ${name} has no inspectable version metadata`);
    if (!license)
      fail(
        `installed package ${name}@${version} has no inspectable license metadata`,
      );
    const licenseFiles = findLicenseFiles(packageDirectory);
    if (licenseFiles.length === 0)
      fail(
        `installed package ${name}@${version} has no LICENSE, COPYING, or NOTICE text`,
      );
    selected.set(key, {
      key,
      name,
      version,
      license,
      packageDirectory,
      licenseFiles,
    });

    for (const dependencyName of dependencyNames(entry)) {
      const dependencyKey = resolvePackageKey(packages, key, dependencyName);
      if (!dependencyKey) {
        const optional =
          Object.hasOwn(entry.optionalDependencies ?? {}, dependencyName) ||
          entry.peerDependenciesMeta?.[dependencyName]?.optional === true;
        if (!optional)
          fail(
            `installed package ${name}@${version} has no lock entry for ${dependencyName}`,
          );
        continue;
      }
      const dependencyEntry = packages[dependencyKey];
      if (dependencyEntry.dev === true)
        fail(
          `production package ${name}@${version} depends on dev-only package ${dependencyName}`,
        );
      if (
        !fs.existsSync(
          guardedPath(appRoot, dependencyKey, "installed dependency"),
        )
      ) {
        const optional =
          Object.hasOwn(entry.optionalDependencies ?? {}, dependencyName) ||
          entry.peerDependenciesMeta?.[dependencyName]?.optional === true;
        if (!optional)
          fail(
            `required installed package is missing: ${dependencyName} (${dependencyKey})`,
          );
        continue;
      }
      visit(dependencyKey, `${name}@${version}`);
    }
  };

  for (const rootName of discoverRuntimeRoots()) {
    const rootKey = resolvePackageKey(packages, "", rootName);
    if (!rootKey)
      fail(
        `browser source imports ${rootName}, but package-lock.json has no installed entry`,
      );
    visit(rootKey, "browser source");
  }

  const records = [...selected.values()].sort(
    (a, b) =>
      compareText(a.name, b.name) ||
      compareText(a.version, b.version) ||
      compareText(a.key, b.key),
  );
  if (records.length === 0)
    fail("no installed production packages were selected");

  const outputFiles = records.map((record) => ({
    ...record,
    copied: record.licenseFiles.map((file) =>
      path.posix.join(
        "licenses",
        packageSlug(record.name, record.version),
        file,
      ),
    ),
  }));

  const lines = [
    "BidWeave third-party notices",
    "============================",
    "",
    "This index covers the installed production packages imported by the browser source. Each listed license file is copied verbatim from its package directory.",
    "",
  ];
  for (const record of outputFiles) {
    lines.push(
      `${record.name}@${record.version}`,
      `License metadata: ${record.license}`,
      "License files:",
    );
    for (const file of record.copied) lines.push(`- ${file}`);
    lines.push("");
  }

  fs.rmSync(licensesRoot, { recursive: true, force: true });
  for (const record of outputFiles) {
    const directory = guardedPath(
      licensesRoot,
      packageSlug(record.name, record.version),
      "license destination",
    );
    fs.mkdirSync(directory, { recursive: true });
    for (const file of record.licenseFiles) {
      const source = guardedPath(
        record.packageDirectory,
        file,
        "license source",
      );
      fs.copyFileSync(
        source,
        guardedPath(directory, file, "license destination"),
      );
    }
  }
  fs.writeFileSync(noticesPath, `${lines.join("\n")}\n`, "utf8");
  process.stdout.write(
    `[third-party-notices] wrote ${noticesPath} for ${records.length} package(s)\n`,
  );
}

try {
  main();
} catch (error) {
  process.stderr.write(
    `${error instanceof Error ? (error.stack ?? error.message) : String(error)}\n`,
  );
  process.exitCode = 1;
}
