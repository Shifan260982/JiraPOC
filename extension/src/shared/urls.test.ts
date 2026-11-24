import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, requiredOrigins, validateSettings } from "./settings";
import { normaliseUrl, shouldFollow } from "./urls";

const settings = {
  ...DEFAULT_SETTINGS,
  startUrls: ["https://tool.example.com/projects"],
  includePatterns: ["https://tool.example.com/projects*", "https://tool.example.com/#/epic/*"],
};

describe("normaliseUrl", () => {
  it("drops plain fragments and trailing slashes but keeps hash routes", () => {
    expect(normaliseUrl("https://tool.example.com/projects/#top")).toBe("https://tool.example.com/projects");
    expect(normaliseUrl("https://tool.example.com/#/epic/1")).toBe("https://tool.example.com/#/epic/1");
    expect(normaliseUrl("/projects/2", "https://tool.example.com/x")).toBe("https://tool.example.com/projects/2");
  });
  it("rejects non-http URLs", () => {
    expect(normaliseUrl("javascript:alert(1)")).toBeNull();
    expect(normaliseUrl("mailto:a@b.c")).toBeNull();
    expect(normaliseUrl("not a url")).toBeNull();
  });
});

describe("shouldFollow", () => {
  it("follows included links on the tool origin only", () => {
    expect(shouldFollow("https://tool.example.com/projects/PRJ", settings)).toBe(true);
    expect(shouldFollow("https://tool.example.com/#/epic/7", settings)).toBe(true);
    expect(shouldFollow("https://tool.example.com/admin", settings)).toBe(false);
    expect(shouldFollow("https://evil.example.org/projects/PRJ", settings)).toBe(false);
  });
  it("never follows excluded links even when included", () => {
    expect(shouldFollow("https://tool.example.com/projects/logout", settings)).toBe(false);
    expect(shouldFollow("https://tool.example.com/projects/PRJ/delete", settings)).toBe(false);
  });
  it("treats regex characters in patterns literally", () => {
    const s = { ...settings, includePatterns: ["https://tool.example.com/projects?id=*"] };
    expect(shouldFollow("https://tool.example.com/projects?id=1", s)).toBe(true);
    expect(shouldFollow("https://tool.example.com/projectsXid=1", s)).toBe(false);
  });
});

describe("settings", () => {
  it("requires only the tool address", () => {
    expect(validateSettings(DEFAULT_SETTINGS)).toEqual(["Enter the address of the Foresight tool."]);
    expect(validateSettings({ ...DEFAULT_SETTINGS, startUrls: ["https://tool.example.com/"] })).toEqual([]);
  });
  it("rejects a link pattern typed as the tool address", () => {
    expect(validateSettings({ ...DEFAULT_SETTINGS, startUrls: ["localhost:5500/board.html/projects/*"] })[0]).toMatch(/not a pattern/);
  });
  it("follows the whole tool site when no include pattern is set", () => {
    const s = { ...DEFAULT_SETTINGS, startUrls: ["https://tool.example.com/"] };
    expect(shouldFollow("https://tool.example.com/board.html", s)).toBe(true);
    expect(shouldFollow("https://other.example.com/board.html", s)).toBe(false);
  });
  it("requests only the tool and backend origins", () => {
    expect(requiredOrigins(settings)).toEqual(["https://tool.example.com/*", "http://localhost:8001/*"]);
  });
});
