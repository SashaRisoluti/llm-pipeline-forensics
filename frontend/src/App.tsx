import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import TraceList from "./pages/TraceList";
import TraceView from "./pages/TraceView";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <span className="brand">Failure Forensics</span>
        <Link to="/">Traces</Link>
        <Link to="/dashboard">Dashboard</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<TraceList />} />
          <Route path="/traces/:traceId" element={<TraceView />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
