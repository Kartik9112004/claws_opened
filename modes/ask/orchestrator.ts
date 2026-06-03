import chalk from "chalk";
import { confirm, isCancel, text, select } from "@clack/prompts";
import { ToolLoopAgent, stepCountIs, tool } from "ai";
import { z } from "zod";
import { getAgentModel } from "../../ai/ai.config.ts";
import { ActionTracker } from "../agent/action-tracker.ts";
import { ToolExecutor } from "../agent/tool-executor.ts";
import { defaultAgentConfig } from "../agent/types.ts";
import { renderTerminalMarkdown } from "../../tui/terminal-md.ts";
import { runApprovalFlow } from "../agent/approval.ts";
import { createWebTools } from "../plan/web-tools.ts";
import { loadChatHistory, saveMessage, listChats, createChat } from "../../db/supabase.ts";

function createAskTools(executor: ToolExecutor) {
  return {
    read_file: tool({
      description:
        "Read a text file from the workspace. Use a path relative to the project root.",
      inputSchema: z.object({
        path: z.string().describe("Relative file path"),
      }),
      execute: async ({ path: p }) => executor.readFile(p),
    }),

    list_files: tool({
      description: "List files and directories under a path.",
      inputSchema: z.object({
        path: z.string(),
        recursive: z.boolean().optional().default(false),
      }),
      execute: async ({ path: p, recursive }) =>
        executor.listFiles(p, recursive),
    }),

    search_files: tool({
      description:
        'Find files matching a glob pattern (e.g. "*.ts", "**/*.md"). Optional content substring filter.',
      inputSchema: z.object({
        root: z.string().describe("Directory to search, relative to root"),
        pattern: z
          .string()
          .describe("Glob-like pattern using * and ** (forward slashes)"),
        content_contains: z.string().optional(),
      }),
      execute: async ({ root, pattern, content_contains }) =>
        executor.searchFiles(root, pattern, content_contains),
    }),

    analyze_codebase: tool({
      description:
        "Summarize structure: file counts, size, extensions. Read-only.",
      inputSchema: z.object({
        path: z.string().default("."),
      }),
      execute: async ({ path: p }) => executor.analyzeCodebase(p),
    }),

    list_skills: tool({
      description:
        "List absolute paths to SKILL.md files under configured skill directories (Cursor / Claude).",
      inputSchema: z.object({}),
      execute: async () => executor.listSkills(),
    }),

    read_skill: tool({
      description:
        "Read a SKILL.md file. Path must be absolute and under skill roots, or use a path returned by list_skills.",
      inputSchema: z.object({
        path: z.string(),
      }),
      execute: async ({ path: p }) => executor.readSkill(p),
    }),
  };
}

function asMd(question: string, answer: string): string {
  return `# Ask Mode\n\n## Question\n\n${question.trim()}\n\n## Answer\n\n${answer.trim()}\n`;
}

export async function runAskMode() {
  const config = defaultAgentConfig();
  console.log(chalk.bold("\n❓ Ask Mode (Interactive Chat)"));
  console.log(chalk.blue(`📂 Workspace Root: ${config.codebasePath}`));

  config.tools.allowFileCreation = true;
  config.tools.allowFileModification = false;
  config.tools.allowFolderCreation = false;
  config.tools.allowShellExecution = false;

  const tracker = new ActionTracker();
  const executor = new ToolExecutor(tracker, config);

  const tools = {
    ...createAskTools(executor),
    ...createWebTools(tracker)
  };

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

  const chatHistory: { question: string; answer: string }[] = [];
  
  let chatId = "cli_ask_mode";
  let chatName = "Default CLI Chat";
  const hasSupabase = !!require("../../db/supabase").supabase;

  if (hasSupabase) {
    const existingChats = await listChats();
    let choice: any = "new";

    if (existingChats.length > 0) {
      choice = await select({
        message: "Would you like to start a new chat or resume an existing one?",
        options: [
          { value: "new", label: "Create a new named chat" },
          { value: "resume", label: "Resume an existing chat" }
        ]
      });

      if (isCancel(choice)) return;
    }

    if (choice === "resume") {
      const selected = await select({
        message: "Choose a chat to resume:",
        options: existingChats.map(c => ({ value: c.id, label: c.name }))
      });
      if (isCancel(selected)) return;
      
      chatId = selected as string;
      chatName = existingChats.find(c => c.id === chatId)?.name || chatId;
    } else {
      const nameInput = await text({
        message: "Enter a name for this new chat:",
        placeholder: "e.g., Codebase Architecture Discussion"
      });
      if (isCancel(nameInput)) return;

      chatName = (nameInput && nameInput.trim()) ? nameInput.trim() : `Chat - ${new Date().toLocaleDateString()}`;
      chatId = crypto.randomUUID();
      await createChat(chatId, chatName);
    }
  }

  // Load conversation context history from Supabase
  const messages: any[] = await loadChatHistory(chatId);
  if (messages.length > 0 && hasSupabase) {
    console.log(chalk.green(`📂 Resuming chat "${chatName}"`));
    console.log(chalk.green(`📂 Loaded ${messages.length} messages of context history from Supabase.\n`));
  } else if (hasSupabase) {
    console.log(chalk.green(`📂 Started new chat: "${chatName}"\n`));
  } else {
    console.log(chalk.dim("Supabase is not configured. Running in local-only mode.\n"));
  }

  console.log(chalk.dim("Type your questions below. Press Enter on an empty line or type 'exit' to finish.\n"));

  while (true) {
    const question = await text({ message: "What do you want to ask?" });
    if (isCancel(question) || !question.trim() || question.trim().toLowerCase() === "exit") {
      break;
    }

    const userQuestion = question.trim();
    messages.push({ role: "user", content: userQuestion });

    console.log(chalk.cyan("\n🤖 Thinking…"));

    try {
      const result = await agent.generate({
        messages,
        onStepFinish: ({ toolCalls }) => {
          for (const tc of toolCalls) {
            const preview = JSON.stringify(tc.input).slice(0, 160);
            console.log(
              chalk.green("  ✓"),
              chalk.bold(String(tc.toolName)),
              chalk.dim(preview + (preview.length >= 160 ? "..." : ""))
            );
          }
        },
      });
      const answer = result.text?.trim() || "(no answer)";
      console.log("\n" + renderTerminalMarkdown(answer) + "\n");

      chatHistory.push({ question: userQuestion, answer });

      // Save messages to Supabase database (non-blocking)
      void saveMessage(chatId, "user", userQuestion, chatName).catch(console.error);
      void saveMessage(chatId, "assistant", answer, chatName).catch(console.error);

      messages.push(...result.response.messages);
    } catch (error: any) {
      console.log(chalk.red(`\nError: ${error.message || error}\n`));
    }
  }

  if (chatHistory.length === 0) return;

  const wantsSave = await confirm({
    message: "Save this conversation to a .md file in the current directory?",
    initialValue: false,
  });
  if (isCancel(wantsSave) || !wantsSave) return;

  const filename = await text({
    message: "Filename",
    initialValue: "ask.md",
    validate: (v) => {
      const s = (v ?? '').trim();
      if (!s) return 'Required';
      if (s.includes('..') || s.includes('/') || s.includes('\\')) return 'No paths';
      if (!s.toLowerCase().endsWith('.md')) return 'Must end with .md';
    },
  });

  if (isCancel(filename)) return;

  let markdownContent = `# Ask Mode Conversation\n\n`;
  let i = 1;
  for (const turn of chatHistory) {
    markdownContent += `## Q${i}: ${turn.question}\n\n${turn.answer}\n\n---\n\n`;
    i++;
  }

  config.tools.allowFileModification = true;
  const fs = require("node:fs");
  const absPath = executor.resolveSafe(filename);
  if (fs.existsSync(absPath)) {
    executor.deleteFile(filename);
  }
  executor.createFile(filename, markdownContent);
  const ok = await runApprovalFlow(tracker);
  if (!ok) return executor.clearStaging();

  executor.applyApprovedFromTracker();
  executor.clearStaging();
}
