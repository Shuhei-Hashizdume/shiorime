import { Navigate, Route, Routes } from "react-router";

import { GuestOnly, RequireAuth } from "./auth/guards";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ShelfPlaceholder from "./pages/ShelfPlaceholder";
import Welcome from "./pages/Welcome";

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <ShelfPlaceholder />
          </RequireAuth>
        }
      />
      <Route
        path="/welcome"
        element={
          <GuestOnly>
            <Welcome />
          </GuestOnly>
        }
      />
      <Route
        path="/login"
        element={
          <GuestOnly>
            <Login />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <Register />
          </GuestOnly>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
