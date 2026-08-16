import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("landing page contains the product promise", async () => {
  const page = await readFile(new URL("../app/page.jsx", import.meta.url), "utf8");
  assert.match(page, /Make listening out of reading/);
  assert.match(page, /Generate audio/);
  assert.match(page, /v1\/projects/);
});
