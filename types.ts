export interface XmlFile {
  name: string;
  content: string;
}

export interface Prompt {
  key: string;
  prompt: string;
  // Raw Proposed LinkName(s) from CSV; may be comma-separated
  linknames?: string;
  // Optional Quick Text Data Point used for labels/heuristics
  quick?: string;
}

// Map of normalized prompt text -> Options Allowed text
export type OptionsByPrompt = { [promptText: string]: string };

export interface ResultRow {
  promptKey: string;
  promptText: string;
  values: { [fileName: string]: string };
}
