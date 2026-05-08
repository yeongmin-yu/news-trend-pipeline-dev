import type { CompoundNounItem, DomainOption } from "../data";
import { Icon } from "../ui";
import type { BackfillDialogState } from "./types";

interface Props {
  item: CompoundNounItem;
  state: BackfillDialogState;
  setState: (next: BackfillDialogState) => void;
  domains: DomainOption[];
  busy: string | null;
  onClose: () => void;
  onSubmit: () => void;
}

export function BackfillDialog({ item, state, setState, domains, busy, onClose, onSubmit }: Props) {
  const submitDisabled = busy === "compound-backfill" || !state.word.trim() || !state.since || !state.until;
  return (
    <div className="dialog-backdrop" style={{ zIndex: 330 }} onClick={onClose}>
      <div className="compact-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="compact-dialog__header">
          <div>
            <div className="compact-dialog__title">과거 데이터 재처리</div>
            <div className="compact-dialog__subtitle">{item.word}</div>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="닫기">
            <Icon.Close size={15} />
          </button>
        </div>
        <div className="compact-dialog__body">
          <label>
            복합명사
            <input value={state.word} onChange={(e) => setState({ ...state, word: e.target.value })} />
          </label>
          <label>
            도메인
            <select value={state.domain} onChange={(e) => setState({ ...state, domain: e.target.value })}>
              <option value="all">전체</option>
              {domains.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            시작
            <input
              type="datetime-local"
              value={state.since}
              onChange={(e) => setState({ ...state, since: e.target.value })}
            />
          </label>
          <label>
            종료
            <input
              type="datetime-local"
              value={state.until}
              onChange={(e) => setState({ ...state, until: e.target.value })}
            />
          </label>
          <label className="compact-dialog__check">
            <input
              type="checkbox"
              checked={state.dryRun}
              onChange={(e) => setState({ ...state, dryRun: e.target.checked })}
            />
            실행 전 영향 범위만 확인
          </label>
        </div>
        <div className="compact-dialog__footer">
          <button className="secondary-button" onClick={onClose}>
            취소
          </button>
          <button className="primary-button" disabled={submitDisabled} onClick={onSubmit}>
            {busy === "compound-backfill" ? "실행 중..." : "DAG 실행"}
          </button>
        </div>
      </div>
    </div>
  );
}
