export interface Settings {
  /** Pages the scan starts from. All must be on the utility tool's origin. */
  startUrls: string[];
  /** Only links matching one of these (`*` wildcard) are followed. Required, so the crawl never wanders. */
  includePatterns: string[];
  /** Links matching any of these are never visited, even if included. */
  excludePatterns: string[];
  maxPages: number;
  /** Optional CSS selector of the tool's "next page" button for paginated tables. */
  nextPageSelector: string;
  maxPaginationClicks: number;
  backendUrl: string;
  dateOrder: "DMY" | "MDY";
}

/** A styled piece inside a cell, e.g. an allocation chip; cls carries meaning such as "over" or "fs-emp-contract". */
export interface CellPart {
  text: string;
  cls: string;
}

export interface Cell {
  text: string;
  href?: string;
  /** colspan, only when > 1 */
  span?: number;
  /** only when the cell holds classed elements */
  parts?: CellPart[];
}

export interface ExtractedTable {
  pageUrl: string;
  pageTitle: string;
  /** Position of this table on the page, and which pagination step it came from. */
  tableIndex: number;
  paginationStep: number;
  headers: string[];
  /** colspan per header, only when some header spans several columns */
  headerSpans?: number[];
  /** Headings and notes that apply to this table (outermost first), e.g. group and workstream titles. */
  context?: CellPart[];
  rows: Cell[][];
}

export interface PageResult {
  title: string;
  tables: Omit<ExtractedTable, "pageUrl" | "pageTitle">[];
  links: string[];
  timedOut: boolean;
}

export interface ScanResult {
  startedAt: string;
  finishedAt: string;
  pagesVisited: string[];
  pagesFailed: { url: string; error: string }[];
  tables: ExtractedTable[];
  cancelled: boolean;
  hitPageLimit: boolean;
}

/** Messages on the "scan" port between side panel and service worker. */
export type ScanRequest = { type: "start"; settings: Settings } | { type: "cancel" };

export type ScanEvent =
  | { type: "progress"; visited: number; queued: number; url: string; tablesFound: number; rowsFound: number }
  | { type: "pageError"; url: string; error: string }
  | { type: "done"; result: ScanResult }
  | { type: "fatal"; error: string };
