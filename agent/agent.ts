import { defineAgent } from "eve";

const editorModel =
  process.env.AI_GATEWAY_MODEL?.trim() || "openai/gpt-6.1-sol";

export default defineAgent({
  model: editorModel,
  reasoning: "medium",
  defaultTools: false,
});
