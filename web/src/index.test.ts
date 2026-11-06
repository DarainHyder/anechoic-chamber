import { ENGINE_VERSION } from "@anechoic-chamber/engine";
import { describe, expect, it } from "vitest";
import { engineVersion } from "./index";

describe("web package", () => {
  it("resolves the engine through the workspace", () => {
    expect(engineVersion).toBe(ENGINE_VERSION);
  });
});
