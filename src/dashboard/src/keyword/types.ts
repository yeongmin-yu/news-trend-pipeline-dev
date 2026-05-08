export type KeywordTabId = "keywords" | "metrics" | "logs";

export interface KeywordFormState {
  id: number | null;
  domainId: string;
  query: string;
  sortOrder: number;
  isActive: boolean;
}

export const EMPTY_KEYWORD_FORM: KeywordFormState = {
  id: null,
  domainId: "tech_science",
  query: "",
  sortOrder: 1,
  isActive: true,
};
