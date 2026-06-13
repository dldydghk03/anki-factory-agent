import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const schemaPath = path.join(root, "schemas", "review-event.schema.json");
const examplesDir = path.join(root, "examples");

const schema = JSON.parse(await readFile(schemaPath, "utf8"));
const required = schema.required ?? [];
const properties = schema.properties ?? {};
const allowAdditional = schema.additionalProperties !== false;

const jsonlFiles = (await readdir(examplesDir))
  .filter((file) => file.endsWith(".jsonl"))
  .map((file) => path.join(examplesDir, file));

if (jsonlFiles.length === 0) {
  throw new Error("No JSONL review-event files found in examples/");
}

let checked = 0;
const errors = [];

for (const file of jsonlFiles) {
  const text = await readFile(file, "utf8");
  const lines = text.split(/\r?\n/);

  lines.forEach((line, index) => {
    const lineNumber = index + 1;
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }

    let event;
    try {
      event = JSON.parse(trimmed);
    } catch (error) {
      errors.push(`${relative(file)}:${lineNumber} invalid JSON: ${error.message}`);
      return;
    }

    checked += 1;
    validateEvent(event, `${relative(file)}:${lineNumber}`);
  });
}

if (errors.length > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log(`Validated ${checked} review event${checked === 1 ? "" : "s"}.`);

function validateEvent(event, location) {
  if (!event || typeof event !== "object" || Array.isArray(event)) {
    errors.push(`${location} event must be an object`);
    return;
  }

  for (const field of required) {
    if (!(field in event)) {
      errors.push(`${location} missing required field "${field}"`);
    }
  }

  if (!allowAdditional) {
    for (const field of Object.keys(event)) {
      if (!(field in properties)) {
        errors.push(`${location} unexpected field "${field}"`);
      }
    }
  }

  for (const [field, value] of Object.entries(event)) {
    const spec = properties[field];
    if (!spec) {
      continue;
    }

    if (spec.type === "string" && typeof value !== "string") {
      errors.push(`${location} field "${field}" must be a string`);
      continue;
    }

    if (Array.isArray(spec.enum) && !spec.enum.includes(value)) {
      errors.push(`${location} field "${field}" must be one of: ${spec.enum.join(", ")}`);
    }
  }
}

function relative(file) {
  return path.relative(root, file);
}

