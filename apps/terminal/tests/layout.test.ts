import {expect, test} from "bun:test";

import {computeTerminalLayout} from "../src/layout.ts";

test("Yoga produces bounded terminal regions", () => {
  const layout = computeTerminalLayout(120, 40);
  expect(layout.contentWidth).toBeGreaterThan(20);
  expect(layout.contentWidth).toBeLessThanOrEqual(120);
  expect(layout.transcriptHeight).toBeGreaterThan(4);
  expect(layout.inputWidth).toBeGreaterThan(20);
});
