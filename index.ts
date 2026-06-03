#!/usr/bin/env bun

import { Command } from "commander";
import { runWakeup } from "./tui/wakeup";
import { runTelegramMode } from "./modes/telegram";
import { runAgentMode } from "./modes/agent/orchestrator";
import { runPlanMode } from "./modes/plan/orchestrator";
import { runAskMode } from "./modes/ask/orchestrator";

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

await program.parseAsync(process.argv);
