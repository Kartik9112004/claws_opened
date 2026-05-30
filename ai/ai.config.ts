import { createOpenRouter } from "@openrouter/ai-sdk-provider";
import { wrapLanguageModel } from "ai";

export function getAgentModel() {
  const provider = createOpenRouter({ apiKey: process.env.OPENROUTER_API_KEY });

  const modelId = process.env.OPENROUTER_DEFAULT_MODEL || "google/gemini-2.5-flash";

  const model = provider(modelId);

  return wrapLanguageModel({
    model,
    middleware: {
      specificationVersion: "v3",
      transformParams: async ({ params }) => {
        return {
          ...params,
          maxOutputTokens: params.maxOutputTokens !== undefined ? Math.min(params.maxOutputTokens, 4000) : 4000,
        };
      },
    },
  });
}

