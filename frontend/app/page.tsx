const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  return (
    <main className="shell">
      <section className="card">
        <p className="eyebrow">PACEMATE · MVP</p>
        <h1>나에게 맞는 학습 페이스를 찾아보세요.</h1>
        <p className="description">학습 계획과 기록을 연결하는 PaceMate 개발 골격입니다.</p>
        <div className="status">
          <span className="dot" aria-hidden="true" />
          <span>Backend API 설정: <code>{apiBase}</code></span>
        </div>
      </section>
    </main>
  );
}
