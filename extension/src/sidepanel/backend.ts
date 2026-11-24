import type { ScanResult, Settings } from "../shared/types";

export interface ProjectOverview {
  project: string;
  as_of: string;
  total_issues: number;
  by_status: Record<"todo" | "in_progress" | "done", number>;
  percent_complete: number | null;
  percent_basis: string;
  epics_total: number;
  epics_done: number;
  epics_delayed: number;
  overdue_issues: number;
  blocked_issues: number;
  missing_data: string[];
}

export interface BoardOverview {
  title: string | null;
  workstreams: number;
  groups: string[];
  people: number;
  outstanding_bugs: number;
  outstanding_stories: number;
  over_allocated_people_this_and_next_week: string[];
  milestones_next_2_weeks: number;
  snapshot: unknown;
}

export interface IngestResponse {
  dataset_id: string;
  projects: { key: string; name: string; overview: ProjectOverview; snapshot: unknown }[];
  board: BoardOverview | null;
  warnings: string[];
  stats: { tables_received: number; issue_tables: number; rows_received: number; issues: number; workstreams: number };
}

/** Sends the raw scan to the backend, which normalises it into the shared project format. */
export async function ingestScan(settings: Settings, scan: ScanResult): Promise<IngestResponse> {
  const body = {
    scanned_at: scan.finishedAt,
    date_order: settings.dateOrder,
    pages_visited: scan.pagesVisited,
    tables: scan.tables.map((t) => ({
      page_url: t.pageUrl,
      page_title: t.pageTitle,
      table_index: t.tableIndex,
      pagination_step: t.paginationStep,
      headers: t.headers,
      header_spans: t.headerSpans ?? [],
      context: t.context ?? [],
      rows: t.rows,
    })),
  };
  const url = new URL("/api/v1/sources/utility/ingest", settings.backendUrl).toString();
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Backend returned ${res.status}${detail ? `: ${detail.slice(0, 300)}` : ""}`);
  }
  return (await res.json()) as IngestResponse;
}

export function downloadJson(filename: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
