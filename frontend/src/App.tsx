import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import { TabBar } from "./components/TabBar";
import BookDetail from "./pages/BookDetail";
import BookSearch from "./pages/BookSearch";
import Login from "./pages/Login";
import { InsightsPlaceholder, ProfilePlaceholder } from "./pages/Placeholder";
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
      <Route path="/books/:bookId/insights" element={<WithTabs><InsightsPlaceholder /></WithTabs>} />
      <Route path="/insights/*" element={<WithTabs><InsightsPlaceholder /></WithTabs>} />
      <Route path="/profile" element={<WithTabs><ProfilePlaceholder /></WithTabs>} />
      <Route path="/welcome" element={<Guest><Welcome /></Guest>} />
      <Route path="/login" element={<Guest><Login /></Guest>} />
      <Route path="/register" element={<Guest><Register /></Guest>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
