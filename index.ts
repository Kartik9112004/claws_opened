#!/usr/bin/env bun

import { Command } from "commander";
import { runWakeup } from "./tui/wakeup";
import { runTelegramMode } from "./modes/telegram";
import { runAgentMode } from "./modes/agent/orchestrator";
import { runPlanMode } from "./modes/plan/orchestrator";
import { runAskMode } from "./modes/ask/orchestrator";
import { indexCodebase } from "./db/rag-indexer";
import { semanticSearch, closeDatabasePool } from "./db/rag-service";

const program = new Command();

program
  .name("claws_opened")
  .description("Claws Opened CLI")
  .version("0.0.1");

program
  .command("wakeup")
  .description("Show the banner and pick cli or telegram mode")
  .action(async () => {
    await runWakeup()
  });

program
  .command("telegram")
  .description("Run the Telegram bot directly")
  .action(async () => {
    await runTelegramMode();
  });

program
  .command("agent")
  .description("Run the Agent mode directly")
  .action(async () => {
    await runAgentMode();
  });

program
  .command("plan")
  .description("Run the Plan mode directly")
  .action(async () => {
    await runPlanMode();
  });

program
  .command("ask")
  .description("Run the Ask mode directly")
  .action(async () => {
    await runAskMode();
  });

program
  .command("index")
  .description("Crawl local files and index them into the Supabase vector database")
  .action(async () => {
    const codebasePath = process.env.CODEBASE_PATH || process.cwd();
    await indexCodebase(codebasePath);
  });

program
  .command("search <query>")
  .description("Run a semantic search query against the codebase")
  .action(async (query: string) => {
    console.log(`🔍 Searching semantically for: "${query}"...\n`);
    const results = await semanticSearch(query);
    if (results.length === 0) {
      console.log("❌ No relevant code chunks found.");
    } else {
      results.forEach((r, idx) => {
        console.log(`\x1b[32m[Match #${idx + 1}] File: ${r.file_path} (Similarity: ${(r.similarity * 100).toFixed(1)}%)\x1b[0m`);
        console.log("----------------------------------------");
        console.log(r.content);
        console.log("----------------------------------------\n");
      });
    }
    await closeDatabasePool();
  });

await program.parseAsync(process.argv);
