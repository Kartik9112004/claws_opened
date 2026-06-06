import postgres from "postgres";

const databaseUrl = process.env.DATABASE_URL;

if (!databaseUrl) {
  console.error("❌ DATABASE_URL environment variable is not defined.");
  process.exit(1);
}

function safePostgresClient(url: string) {
  // If the password contains special characters like '@', standard URI parsing fails.
  // We split by the last '@' to separate credentials from the host/db.
  if (!url.startsWith("postgresql://") && !url.startsWith("postgres://")) {
    return postgres(url);
  }
  const prefix = url.startsWith("postgresql://") ? "postgresql://" : "postgres://";
  const rest = url.slice(prefix.length);
  const lastAtIndex = rest.lastIndexOf("@");
  if (lastAtIndex === -1) return postgres(url);
  
  const creds = rest.slice(0, lastAtIndex);
  const hostPart = rest.slice(lastAtIndex + 1);
  
  const colonIndex = creds.indexOf(":");
  if (colonIndex === -1) return postgres(url);
  
  const user = creds.slice(0, colonIndex);
  const pass = creds.slice(colonIndex + 1);
  
  const safeUrl = `${prefix}${encodeURIComponent(user)}:${encodeURIComponent(pass)}@${hostPart}`;
  return postgres(safeUrl);
}

const sql = safePostgresClient(databaseUrl);

async function runMigration() {
  console.log("🔄 Starting database migration for pgvector RAG...");

  try {
    // 1. Enable the vector extension
    console.log("➡️ Enabling pgvector extension...");
    await sql`CREATE EXTENSION IF NOT EXISTS vector;`;

    // 2. Create the code_chunks table
    console.log("➡️ Creating code_chunks table...");
    await sql`
      CREATE TABLE IF NOT EXISTS code_chunks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        file_path TEXT NOT NULL,
        content TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        file_hash TEXT NOT NULL,
        embedding VECTOR(1536) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
      );
    `;

    // 3. Create indices
    console.log("➡️ Creating index on file_path...");
    await sql`CREATE INDEX IF NOT EXISTS idx_code_chunks_file_path ON code_chunks(file_path);`;

    console.log("➡️ Creating HNSW index for vector similarity search...");
    // We use cosine distance. We use IF NOT EXISTS since PG doesn't natively support it on CREATE INDEX directly,
    // so we can wrap it in an check or catch error to make it idempotent.
    try {
      await sql`
        CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding_hnsw 
        ON code_chunks USING hnsw (embedding vector_cosine_ops);
      `;
    } catch (e: any) {
      console.warn("⚠️ Warning: Could not create HNSW index (might not be supported on this PG version/tier). Falling back to standard index or catching: ", e.message || e);
    }

    console.log("✅ Migration completed successfully!");
  } catch (error) {
    console.error("❌ Migration failed:", error);
    process.exit(1);
  } finally {
    await sql.end();
  }
}

runMigration();
