import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { TabBar } from "./components/TabBar";
import AiProposal from "./pages/AiProposal";
import BookDetail from "./pages/BookDetail";
import BookSearch from "./pages/BookSearch";
import Login from "./pages/Login";
import BookInsights from "./pages/BookInsights";
import InsightDetail from "./pages/InsightDetail";
import InsightEditor from "./pages/InsightEditor";
import InsightGroups from "./pages/InsightGroups";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Shelf from "./pages/Shelf";
import Welcome from "./pages/Welcome";

/** ログインが必要で、画面下に共通メニューを出す画面 */
function WithTabs({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      {children}
      <TabBar />
    </RequireAuth>
  );
}

function Guest({ children }: { children: ReactNode }) {
  return <GuestOnly>{children}</GuestOnly>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WithTabs><Shelf /></WithTabs>} />
      <Route path="/books/add" element={<WithTabs><BookSearch /></WithTabs>} />
      <Route path="/books/:bookId" element={<WithTabs><BookDetail /></WithTabs>} />
      <Route path="/insights" element={<WithTabs><InsightGroups /></WithTabs>} />
      <Route path="/insight-groups/:groupId" element={<WithTabs><BookInsights /></WithTabs>} />
      <Route path="/insights/new" element={<RequireAuth><InsightEditor /></RequireAuth>} />
      <Route path="/insights/:insightId" element={<WithTabs><InsightDetail /></WithTabs>} />
      <Route path="/insights/:insightId/edit" element={<RequireAuth><InsightEditor /></RequireAuth>} />
      {/* AI提案は共通メニューを出さない（要件定義書 9章の例外） */}
      <Route path="/ai-proposals/:proposalId" element={<RequireAuth><AiProposal /></RequireAuth>} />
      <Route path="/profile" element={<WithTabs><Profile /></WithTabs>} />
      <Route path="/welcome" element={<Guest><Welcome /></Guest>} />
      <Route path="/login" element={<Guest><Login /></Guest>} />
      <Route path="/register" element={<Guest><Register /></Guest>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
