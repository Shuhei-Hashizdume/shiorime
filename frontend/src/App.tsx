import { useEffect, useState } from "react";

// 土台の確認用の空の画面。API（GET /api/v1/health）につながるかだけを表示する。
export default function App() {
  const [status, setStatus] = useState("確認中…");

  useEffect(() => {
    fetch("/api/v1/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { status: string }) => setStatus(data.status))
      .catch(() => setStatus("つながりません"));
  }, []);

  return (
    <main>
      <h1>SHIORIME</h1>
      <p>API: {status}</p>
    </main>
  );
}
