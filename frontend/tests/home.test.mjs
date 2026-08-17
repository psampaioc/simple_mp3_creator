import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("landing page contains the product promise", async () => {
  const page = await readFile(new URL("../app/page.jsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.jsx", import.meta.url), "utf8");
  assert.match(page, /Make listening out of reading/);
  assert.match(page, /Generate audio/);
  assert.match(page, /v1\/projects/);
  assert.match(page, /role="dialog"/);
  assert.match(page, /aria-modal="true"/);
  assert.match(page, /Sign in to create audio/);
  assert.match(page, /temporarily unavailable/);
  assert.doesNotMatch(page, /Start the local API/);
  assert.doesNotMatch(page, /localhost:8000/);
  assert.match(layout, /@vercel\/analytics\/next/);
  assert.match(layout, /<Analytics \/>/);
});
