import type { Metadata } from "next";

import { PromptHistoryWorkspace } from "@/app/_components/prompt-history-workspace";

export const metadata: Metadata = { title: "Prompt history", description: "Review original prompts and revision requests across GM Studio jobs." };

export default function PromptsPage() {
  return <PromptHistoryWorkspace />;
}
