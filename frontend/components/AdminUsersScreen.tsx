"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { consentLabel, pageCount } from "@/lib/adminLabels";
import { dateTimeKSTLabel } from "@/lib/week";

type AdminUser = {
  user_id_masked: string;
  user_type: string;
  consented: boolean;
  consent_version: string | null;
  active_goal_count: number;
  last_active_at: string | null;
  status: "active" | "dormant";
};
type UserList = { items: AdminUser[]; total: number; page: number; page_size: number };
type Filter = "all" | "active" | "dormant";
type LoadStatus = "loading" | "ready" | "error";

/** Read-only user overview (Phase 5E). The server never sends full UIDs or learning content. */
export function AdminUsersScreen() {
  const { session } = useAuth();
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<UserList | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    (async () => {
      setStatus("loading");
      setError(null);
      try {
        const token = await session.getToken();
        const result = await apiRequest<UserList>(`/api/admin/users?status=${filter}&page=${page}`, { token });
        if (cancelled) return;
        setData(result);
        setStatus("ready");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "사용자 목록을 불러오지 못했습니다.");
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, filter, page, reloadKey]);

  const pages = data ? pageCount(data.total, data.page_size) : 1;

  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">ADMIN · USERS</p>
          <h1>사용자 관리</h1>
          <p>동의 여부, 진행 중 학습 수, 활성 상태를 확인합니다. 학습 내용과 개인 식별 정보는 표시하지 않습니다.</p>
        </div>
        <select
          className="weekday-select"
          aria-label="상태 필터"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value as Filter);
            setPage(1);
          }}
        >
          <option value="all">전체</option>
          <option value="active">활성</option>
          <option value="dormant">휴면</option>
        </select>
      </div>
      <div className="admin-banner">읽기 전용 화면입니다. 사용자 데이터를 수정하거나 삭제할 수 없어요.</div>

      {status === "loading" && (
        <section className="card">
          <p className="description">불러오는 중…</p>
        </section>
      )}
      {status === "error" && (
        <section className="card">
          <p className="error" role="alert">
            {error}
          </p>
          <button type="button" className="btn" onClick={() => setReloadKey((k) => k + 1)}>
            다시 시도
          </button>
        </section>
      )}
      {status === "ready" && data && (
        <section className="card table-wrap">
          {data.items.length === 0 ? (
            <p className="description">조건에 맞는 사용자가 없어요.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>사용자 ID</th>
                  <th>유형</th>
                  <th>동의</th>
                  <th>진행 중 학습</th>
                  <th>최근 활동</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u, i) => (
                  <tr key={`${u.user_id_masked}-${i}`}>
                    <td>{u.user_id_masked}</td>
                    <td>{u.user_type}</td>
                    <td>{consentLabel(u.consented, u.consent_version)}</td>
                    <td>{u.active_goal_count}개</td>
                    <td>{u.last_active_at ? dateTimeKSTLabel(u.last_active_at) : "–"}</td>
                    <td>
                      <span className={`pill${u.status === "active" ? "" : " gray"}`}>{u.status === "active" ? "활성" : "휴면"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {pages > 1 && (
            <div className="week-nav" style={{ marginTop: 12 }}>
              <button type="button" className="btn secondary small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ← 이전
              </button>
              <span className="small muted" style={{ alignSelf: "center" }}>
                {page} / {pages} 쪽 · 전체 {data.total}명
              </span>
              <button type="button" className="btn secondary small" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                다음 →
              </button>
            </div>
          )}
        </section>
      )}
    </>
  );
}
