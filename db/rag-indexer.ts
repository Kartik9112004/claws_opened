import fs from "node:fs";
import path from "node:path";
import postgres from "postgres";
import { chunkText, computeHash, generateEmbeddings } from "./rag-service";

const databaseUrl = process.env.DATABASE_URL;

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

// Files and folders to ignore during indexing
const EXCLUDE_DIRS = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".bun",
  "todo-app",
  "todo-list-app",
]);

const INCLUDE_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".json",
  ".md",
  ".css",
  ".html",
  ".yaml",
  ".yml",
]);

interface PendingChunk {
  filePath: string;
  content: string;
  index: number;
  hash: string;
}

export async function indexCodebase(codebasePath: string) {
  if (!sql) {
    console.error("❌ Database is not connected.");
    return;
  }

  console.log(`\n🔍 Scanning codebase for files in: ${codebasePath}`);
  const filesToIndex: string[] = [];

  function walk(dir: string) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const ent of entries) {
      const fullPath = path.join(dir, ent.name);
      const relPath = path.relative(codebasePath, fullPath);

      if (ent.isDirectory()) {
        if (EXCLUDE_DIRS.has(ent.name)) continue;
        walk(fullPath);
      } else {
        const ext = path.extname(ent.name).toLowerCase();
        if (INCLUDE_EXTENSIONS.has(ext)) {
          filesToIndex.push(relPath);
        }
      }
    }
  }

  walk(codebasePath);
  console.log(`📂 Found ${filesToIndex.length} code files to check.`);

  let skippedCount = 0;
  let updatedCount = 0;
  const pendingChunks: PendingChunk[] = [];

  for (const relPath of filesToIndex) {
    const absPath = path.resolve(codebasePath, relPath);
    const content = fs.readFileSync(absPath, "utf8");
    const fileHash = computeHash(content);

    // 1. Check if the file hash is already indexed and matches
    const existing = await sql`
      SELECT id FROM code_chunks 
      WHERE file_path = ${relPath} AND file_hash = ${fileHash} 
      LIMIT 1
    `;

    if (existing.length > 0) {
      skippedCount++;
      continue;
    }

    updatedCount++;
    // File changed, delete old chunks from the database
    await sql`
      DELETE FROM code_chunks WHERE file_path = ${relPath}
    `;

    const chunks = chunkText(content);
    chunks.forEach((chunkContent, idx) => {
      pendingChunks.push({
        filePath: relPath,
        content: chunkContent,
        index: idx,
        hash: fileHash,
      });
    });
  }

  console.log(`⏭️  Unchanged files skipped: ${skippedCount}`);
  console.log(`📝 Files to index/update: ${updatedCount} (${pendingChunks.length} total chunks)`);

  if (pendingChunks.length === 0) {
    console.log("✨ Codebase is already up to date. No indexing required.");
    await sql.end();
    return;
  }

  // 2. Batch embedding calls and database insertions
  const BATCH_SIZE = 40;
  let processedChunks = 0;

  console.log(`🚀 Starting batch indexing (Batch size: ${BATCH_SIZE})...`);

  for (let i = 0; i < pendingChunks.length; i += BATCH_SIZE) {
    const batch = pendingChunks.slice(i, i + BATCH_SIZE);
    const batchTexts = batch.map((c) => c.content);

    try {
      console.log(`  ⚡ Generating embeddings for chunks ${i + 1} to ${Math.min(i + BATCH_SIZE, pendingChunks.length)}...`);
      const embeddings = await generateEmbeddings(batchTexts);

      console.log(`  💾 Inserting chunks into database...`);
      // Insert in a transaction to be safe and fast
      await sql.begin(async (tx) => {
        for (let j = 0; j < batch.length; j++) {
          const chunk = batch[j]!;
          const embedding = embeddings[j]!;
          const vectorStr = `[${embedding.join(",")}]`;

          await tx`
            INSERT INTO code_chunks (file_path, content, chunk_index, file_hash, embedding)
            VALUES (${chunk.filePath}, ${chunk.content}, ${chunk.index}, ${chunk.hash}, ${vectorStr}::vector)
          `;
        }
      });

      processedChunks += batch.length;
    } catch (err) {
      console.error(`❌ Error indexing batch starting at index ${i}:`, err);
    }
  }

  console.log(`\n🎉 Indexing finished successfully!`);
  console.log(`   Processed ${processedChunks}/${pendingChunks.length} chunks across ${updatedCount} files.`);
  console.log(`   Skipped ${skippedCount} unchanged files.`);

  await sql.end();
}
