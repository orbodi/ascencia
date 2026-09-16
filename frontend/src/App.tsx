import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./lib/auth";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/Login";
import { DashboardPage } from "./pages/Dashboard";
import { LevelsPage } from "./pages/Levels";
import { TeachersPage } from "./pages/Teachers";
import { GroupsPage } from "./pages/Groups";
import { RoomsPage } from "./pages/Rooms";
import { CoursesPage } from "./pages/Courses";
import { SchedulePage } from "./pages/Schedule";
import { ChangesPage } from "./pages/Changes";
import { HistoryPage } from "./pages/History";
import { ConfigPage } from "./pages/Config";
import { ChatPage } from "./pages/Chat";
import { CurriculumPage } from "./pages/Curriculum";
import { PublicationsPage } from "./pages/Publications";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter basename="/backoffice">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="levels" element={<LevelsPage />} />
              <Route path="curriculum" element={<CurriculumPage />} />
              <Route path="teachers" element={<TeachersPage />} />
              <Route path="groups" element={<GroupsPage />} />
              <Route path="rooms" element={<RoomsPage />} />
              <Route path="courses" element={<CoursesPage />} />
              <Route path="schedule" element={<SchedulePage />} />
              <Route path="publications" element={<PublicationsPage />} />
              <Route path="changes" element={<ChangesPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="config" element={<ConfigPage />} />
              <Route path="chat" element={<ChatPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
