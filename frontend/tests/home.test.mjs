import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("landing page contains the product promise", async () => {
  const page = await readFile(new URL("../app/page.jsx", import.meta.url), "utf8");
  assert.match(page, /Give your words a voice/);
  assert.match(page, /Create an audio project/);
});

