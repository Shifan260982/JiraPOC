import { describe, expect, it } from "vitest";
import { parentPages } from "./crawler";

describe("parentPages", () => {
  it("offers the open page, its folder and the home page once each", () => {
    expect(parentPages("http://localhost:5500/board.html")).toEqual(["http://localhost:5500/board.html", "http://localhost:5500/"]);
    expect(parentPages("https://tool.example.com/projects/p1/board?x=1")).toEqual([
      "https://tool.example.com/projects/p1/board?x=1", "https://tool.example.com/projects/p1", "https://tool.example.com/",
    ]);
    expect(parentPages("https://tool.example.com/")).toEqual(["https://tool.example.com/"]);
  });
  it("ignores pages that are not web pages", () => {
    expect(parentPages("chrome://extensions")).toEqual([]);
  });
});
