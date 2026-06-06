import postgres from "postgres";
import crypto from "node:crypto";

const databaseUrl = process.env.DATABASE_URL;
const openRouterApiKey = process.env.OPENROUTER_API_KEY;

if (!databaseUrl) {
  console.warn("⚠️ DATABASE_URL is not set. Database operations will fail.");
}

if (!openRouterApiKey) {
  console.warn("⚠️ OPENROUTER_API_KEY is not set. Embedding generation will fail.");
}

// Helper to URL-encode password in database URL to prevent connection string parsing errors
function safePostgresClient() {
  if (!databaseUrl) return null;
  
  if (!databaseUrl.startsWith("postgresql://") && !databaseUrl.startsWith("postgres://")) {
    return postgres(databaseUrl);
  }
  
  const prefix = databaseUrl.startsWith("postgresql://") ? "postgresql://" : "postgres://";
  const rest = databaseUrl.slice(prefix.length);
  const lastAtIndex = rest.lastIndexOf("@");
  if (lastAtIndex === -1) return postgres(databaseUrl);
  
  const creds = rest.slice(0, lastAtIndex);
  const hostPart = rest.slice(lastAtIndex + 1);
  
  const colonIndex = creds.indexOf(":");
  if (colonIndex === -1) return postgres(databaseUrl);
  
  const user = creds.slice(0, colonIndex);
  const pass = creds.slice(colonIndex + 1);
  
  const safeUrl = `${prefix}${encodeURIComponent(user)}:${encodeURIComponent(pass)}@${hostPart}`;
  return postgres(safeUrl);
}

const sql = safePostgresClient();

/**
 * Generate vector embeddings for a batch of text strings using OpenRouter API.
 */
export async function generateEmbeddings(texts: string[]): Promise<number[][]> {
  if (!openRouterApiKey) {
    throw new Error("OPENROUTER_API_KEY is missing");
  }

  const response = await fetch("https://openrouter.ai/api/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${openRouterApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "openai/text-embedding-3-small",
      input: texts,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenRouter Embeddings API error: ${response.status} - ${errorText}`);
  }

  const json = await response.json() as any;
  if (!json.data || !Array.isArray(json.data)) {
    throw new Error("Unexpected embeddings API response structure");
  }

  // OpenRouter returns data sorted by index matching input array
  return json.data
    .sort((a: any, b: any) => (a.index ?? 0) - (b.index ?? 0))
    .map((item: any) => item.embedding as number[]);
}

/**
 * Split text into chunks of ~1000 characters with 200 characters overlap.
 * Tries to align chunk boundaries with newlines to keep code blocks readable.
 */
export function chunkText(text: string, maxChunkSize = 1000, overlap = 200): string[] {
  const chunks: string[] = [];
  if (text.length <= maxChunkSize) {
    return [text.trim()];
  }

  let start = 0;
  while (start < text.length) {
    let end = start + maxChunkSize;
    if (end < text.length) {
      // Find the last newline within the overlap window to avoid splitting in the middle of a line
      const nextNewline = text.lastIndexOf("\n", end);
      if (nextNewline > start + overlap) {
        end = nextNewline;
      }
    }

    const chunk = text.slice(start, end).trim();
    if (chunk) {
      chunks.push(chunk);
    }

    start = end - overlap;
    if (start < 0) start = 0;
    if (end >= text.length) break;
  }

  return chunks;
}

/**
 * Computes SHA-256 hash of a string.
 */
export function computeHash(content: string): string {
  return crypto.createHash("sha256").update(content).digest("hex");
}

export interface SearchResult {
  file_path: string;
  content: string;
  similarity: number;
}

/**
 * Performs semantic similarity search on code chunks stored in Supabase.
 */
export async function semanticSearch(query: string, limit = 5, minSimilarity = 0.3): Promise<SearchResult[]> {
  if (!sql) {
    console.error("❌ Database client is not initialized.");
    return [];
  }

  try {
    const [queryEmbedding] = await generateEmbeddings([query]);
    if (!queryEmbedding) {
      throw new Error("Failed to generate embedding for search query");
    }

    // Format embedding array to postgres vector representation [val1, val2, ...]
    const vectorStr = `[${queryEmbedding.join(",")}]`;

    // Query chunks sorted by cosine similarity
    const results = await sql`
      SELECT file_path, content, 1 - (embedding <=> ${vectorStr}::vector) AS similarity
      FROM code_chunks
      WHERE 1 - (embedding <=> ${vectorStr}::vector) > ${minSimilarity}
      ORDER BY embedding <=> ${vectorStr}::vector
      LIMIT ${limit}
    `;

    return results.map((r: any) => ({
      file_path: r.file_path,
      content: r.content,
      similarity: Number(r.similarity),
    }));
  } catch (error) {
    console.error("❌ Semantic search query failed:", error);
    return [];
  }
}

/**
 * Closes the direct database connection pool.
 */
export async function closeDatabasePool() {
  if (sql) {
    await sql.end();
  }
}
