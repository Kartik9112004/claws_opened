import { tool, ToolLoopAgent, stepCountIs } from "ai";
import { z } from "zod";
import { getAgentModel } from "../../ai/ai.config.ts";
import { ActionTracker } from "../agent/action-tracker.ts";
import { ToolExecutor } from "../agent/tool-executor.ts";
import { createAgentTools } from "../agent/agent-tools.ts";
import { defaultAgentConfig, type AgentConfig } from "../agent/types.ts";
import { createWebTools } from "../plan/web-tools.ts";
import type { Plan, PlanStep } from "../plan/types.ts";
import { replyMd } from "./text.ts";
import { finishOrApprove } from "./approval-session.ts";
import { loadChatHistory, saveMessage } from "../../db/supabase.ts";
import { semanticSearch } from "../../db/rag-service.ts";

function readOnlyConfig(): AgentConfig {
  const c = defaultAgentConfig();
  c.tools.allowFileCreation = false;
  c.tools.allowFileModification = false;
  c.tools.allowFolderCreation = false;
  c.tools.allowShellExecution = false;
  return c;
}

function agentOptions(config: AgentConfig, maxSteps: number) {
  return {
    model: getAgentModel(),
    stopWhen: stepCountIs(maxSteps),
    instructions: `Workspace root: ${config.codebasePath}`,
  };
}

function createReadOnlyTools(executor: ToolExecutor) {
  return {
    semantic_search_codebase: tool({
      description:
        "Perform a semantic search across the codebase using vector embeddings. " +
        "Returns the most relevant code chunks and files matching your natural language query.",
      inputSchema: z.object({
        query: z.string().describe("Semantic natural language search query"),
        limit: z.number().int().min(1).max(10).optional().default(5),
      }),
      execute: async ({ query, limit }) => {
        const results = await semanticSearch(query, limit);
        if (results.length === 0) {
          return "No relevant code snippets found matching the query.";
        }
        return results
          .map(
            (r, i) =>
              `Match #${i + 1} in File: ${r.file_path} (Similarity: ${(r.similarity * 100).toFixed(1)}%)\n\`\`\`\n${r.content}\n\`\`\``
          )
          .join("\n\n");
      },
    }),

    read_file: tool({
      description: "Read a workspace file (relative path).",
      inputSchema: z.object({ path: z.string() }),
      execute: async ({ path: p }) => executor.readFile(p),
    }),
    list_files: tool({
      description: "List files/dirs at a path.",
      inputSchema: z.object({
        path: z.string(),
        recursive: z.boolean().optional().default(false),
      }),
      execute: async ({ path: p, recursive }) =>
        executor.listFiles(p, recursive),
    }),
    search_files: tool({
      description:
        "Find files matching a glob pattern; optional content filter.",
      inputSchema: z.object({
        root: z.string(),
        pattern: z.string(),
        content_contains: z.string().optional(),
      }),
      execute: async ({ root, pattern, content_contains }) =>
        executor.searchFiles(root, pattern, content_contains),
    }),
    analyze_codebase: tool({
      description: "Summarize the codebase structure.",
      inputSchema: z.object({ path: z.string().default(".") }),
      execute: async ({ path: p }) => executor.analyzeCodebase(p),
    }),
  };
}

function extraWebTools(tracker: ActionTracker) {
  return process.env.FIRECRAWL_API_KEY ? createWebTools(tracker) : {};
}


export async function runAsk(ctx: any, question: string) {
  const config = readOnlyConfig();
  const tracker = new ActionTracker();
  const executor = new ToolExecutor(tracker, config);
  const tools = { ...createReadOnlyTools(executor), ...extraWebTools(tracker) };
  
  const agent = new ToolLoopAgent({
    model: getAgentModel(),
    stopWhen: stepCountIs(20),
    instructions: [
      "You are in Ask Mode. You have read-only access to the workspace.",
      `Workspace root: ${config.codebasePath}`,
      "You MUST use the provided tools (like list_files, read_file, search_files) to inspect the workspace and answer any questions about files, folders, code, or directories.",
      "If the user asks about a directory or file (for example, 'travel_agent'), you must call list_files with the relative path to inspect it.",
      "Do NOT refuse to access files or say you cannot access the local file system. You have tools specifically for this purpose and must use them.",
    ].join("\n"),
    tools,
  });

  const chatId = ctx.chat?.id || "telegram_ask";
  const chat = ctx.chat;
  let chatName = "Telegram Chat";
  if (chat) {
    if (chat.type === "private") {
      chatName = [chat.first_name, chat.last_name].filter(Boolean).join(" ") || chat.username || `User ${chat.id}`;
    } else {
      chatName = chat.title || `Group ${chat.id}`;
    }
  }

  const messages = await loadChatHistory(chatId);
  messages.push({ role: "user", content: question });

  const { text } = await agent.generate({ messages });
  const answer = text || "no answer";

  await replyMd(ctx, answer);

  void saveMessage(chatId, "user", question, chatName).catch(console.error);
  void saveMessage(chatId, "assistant", answer, chatName).catch(console.error);
}

export async function runAgent(ctx: { reply: (t: string, o?: object) => Promise<unknown> }, chatId: number, goal: string) {
  const config = defaultAgentConfig();
  const tracker = new ActionTracker();
  const executor = new ToolExecutor(tracker, config);
  const tools = createAgentTools(executor);
  const agent = new ToolLoopAgent({
    ...agentOptions(config, 40),
    tools,
  });
  const { text } = await agent.generate({ prompt: goal });
  if (text?.trim()) await replyMd(ctx, text.trim());
 await finishOrApprove(ctx, chatId, tracker, executor, '✅ Done. No file changes were needed.');
}

export async function runPlanSteps(
  ctx: { reply: (t: string, o?: object) => Promise<unknown> },
  chatId: number,
  plan: Plan,
  steps: PlanStep[],
) {
  const config = defaultAgentConfig();
  const tracker = new ActionTracker();
  const executor = new ToolExecutor(tracker, config);
  const tools = { ...createAgentTools(executor), ...extraWebTools(tracker) };

  for (const step of steps) {
    await ctx.reply(`🔧 Executing: *${step.title}*`, { parse_mode: 'Markdown' });
    const prompt = [`Goal: ${plan.goal}`, `Step: ${step.title}`, step.description].join('\n');
    const agent = new ToolLoopAgent({
      ...agentOptions(config, 30),
      tools,
    });
    const { text } = await agent.generate({ prompt });
    if (text?.trim()) await replyMd(ctx, text.trim());
  }

 await finishOrApprove(ctx, chatId, tracker, executor, '✅ All steps done. No file changes needed.');
}
