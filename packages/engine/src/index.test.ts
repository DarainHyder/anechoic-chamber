import { describe, expect, it } from "vitest";
import { ENGINE_VERSION } from "./index";

describe("engine package", () => {
  it("exports a semantic version", () => {
    expect(ENGINE_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
