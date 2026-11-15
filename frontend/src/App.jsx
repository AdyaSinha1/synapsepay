import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell.jsx";
import { useApp } from "./context.jsx";
import Agents from "./pages/Agents.jsx";
import Arbiter from "./pages/Arbiter.jsx";
import Board from "./pages/Board.jsx";
import ContractDetail from "./pages/ContractDetail.jsx";
import Contracts from "./pages/Contracts.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import DemoStudio from "./pages/DemoStudio.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Payments from "./pages/Payments.jsx";
import Settings from "./pages/Settings.jsx";
import Wizard from "./pages/Wizard.jsx";
import Workspace from "./pages/Workspace.jsx";

function RequireAuth({ children, role }) {
  const { user } = useApp();
  if (!user) return <Navigate to="/login" replace />;
  if (role && user.role !== role) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Shell />}>
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/contracts" element={<RequireAuth><Contracts /></RequireAuth>} />
        <Route path="/contracts/new" element={<RequireAuth><Wizard /></RequireAuth>} />
        <Route path="/contracts/:id" element={<RequireAuth><ContractDetail /></RequireAuth>} />
        <Route path="/contracts/:id/workspace" element={<RequireAuth><Workspace /></RequireAuth>} />
        <Route path="/board" element={<RequireAuth><Board /></RequireAuth>} />
        <Route path="/studio" element={<DemoStudio />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/arbiter" element={<RequireAuth><Arbiter /></RequireAuth>} />
        <Route path="/payments" element={<RequireAuth><Payments /></RequireAuth>} />
        <Route
          path="/settings"
          element={
            <RequireAuth>
              <Settings />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
