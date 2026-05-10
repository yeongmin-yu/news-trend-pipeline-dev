import type { CompoundCandidateItem } from "../data";

export type DictionaryTabId =
  | "compound"
  | "stopword"
  | "candidates"
  | "stopword-candidates"
  | "history";

export const DICTIONARY_PAGE_SIZE = 50;

export const CANDIDATE_STATUS_LABEL: Record<string, string> = {
  needs_review: "검토필요",
  approved: "승인됨",
  rejected: "반려됨",
};

export const CANDIDATE_STATUS_CHIP: Record<string, string> = {
  needs_review: "warn",
  approved: "up",
  rejected: "muted",
};

export const AUTO_DECISION_LABEL: Record<string, string> = {
  high_confidence: "고신뢰",
  needs_manual_review: "수동검토",
  low_confidence: "낮은신뢰",
  api_error: "API오류",
  no_search_results: "검색결과없음",
  no_exact_match: "정확일치없음",
};

export const AUTO_DECISION_CHIP: Record<string, string> = {
  high_confidence: "up",
  needs_manual_review: "warn",
  low_confidence: "muted",
  api_error: "down",
  no_search_results: "down",
  no_exact_match: "down",
};

export const SW_CANDIDATE_STATUS_LABEL: Record<string, string> = {
  needs_review: "검토필요",
  approved: "승인됨",
  rejected: "반려됨",
};

export const SW_CANDIDATE_STATUS_CHIP: Record<string, string> = {
  needs_review: "warn",
  approved: "up",
  rejected: "muted",
};

export const DOMAIN_LABEL: Record<string, string> = { all: "전체" };

export interface DictionaryTabState<T> {
  data: { items: T[]; total: number; page: number; limit: number } | null;
  loading: boolean;
  error: string | null;
}

export function emptyDictionaryTabState<T>(): DictionaryTabState<T> {
  return { data: null, loading: false, error: null };
}

export interface HistoryItem {
  id: number;
  entity_type: string;
  entity_id: number | null;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  actor: string;
  acted_at: string;
}

export interface BackfillDialogState {
  word: string;
  domain: string;
  since: string;
  until: string;
  dryRun: boolean;
}

export function renderAutoEvidence(c: CompoundCandidateItem): string {
  const e = c.autoEvidenceSummary;
  if (!e) return "—";
  return [
    e.hasExactCompactMatch ? "exact" : "no exact",
    e.naverTotal != null ? `total ${e.naverTotal}` : null,
    e.frequencyPerDoc != null ? `f/d ${e.frequencyPerDoc}` : null,
    e.matchedField ? `${e.matchedField}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
