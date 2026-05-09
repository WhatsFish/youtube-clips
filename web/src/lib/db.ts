import { Client, type QueryResultRow } from "pg";

function config() {
  return {
    host: process.env.PG_HOST ?? "db",
    port: parseInt(process.env.PG_PORT ?? "5432", 10),
    user: process.env.PG_USER ?? "youtube_clips",
    password: process.env.PG_PASSWORD ?? "",
    database: process.env.PG_DB ?? "youtube_clips",
  };
}

/**
 * Ad-hoc query helper. Opens a connection per request — fine at the
 * volume this dashboard generates. Mirrors the pattern used elsewhere
 * in the fleet (stock-analyst, cost-tracker, status).
 */
export async function query<T extends QueryResultRow = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const c = new Client(config());
  await c.connect();
  try {
    const r = await c.query<T>(sql, params);
    return r.rows;
  } finally {
    await c.end();
  }
}
