import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Layout } from "./Layout";
import { WorkspacePage } from "./pages/WorkspacePage";
import { ResourcePage } from "./pages/ResourcePage";
import { ProblemSetsPage } from "./pages/ProblemSetsPage";
import { TagsPage, TagPage } from "./pages/TagsPage";
import { QuizListPage, QuizRunPage, QuizBuildPage } from "./pages/QuizPage";
import { AdminPage } from "./pages/AdminPage";
import { SearchPage, ProfilePage, MemberPage } from "./pages/MiscPages";
import { SignInPage } from "./pages/SignInPage";

/* Every route the server hands to this client.

   /resource/<topic>     learning material and nothing else
   /problem-sets[/<t>[/<q>]]  the explorer: a topic tab, a problem tab with notes
   /app                  the tool workspace, where arranging panels is the job
   everything else       a document, which is the right shape for browsing */
const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <SignInPage /> },
      { path: "/resource/:topicId", element: <ResourcePage /> },
      { path: "/problem-sets", element: <ProblemSetsPage /> },
      { path: "/problem-sets/:topicId", element: <ProblemSetsPage /> },
      { path: "/problem-sets/:topicId/:questionId", element: <ProblemSetsPage /> },
      { path: "/app", element: <WorkspacePage /> },
      { path: "/tags", element: <TagsPage /> },
      { path: "/tags/:name", element: <TagPage /> },
      { path: "/quiz", element: <QuizListPage /> },
      { path: "/quiz/new", element: <QuizBuildPage /> },
      { path: "/quiz/:uid", element: <QuizRunPage /> },
      { path: "/admin", element: <AdminPage /> },
      { path: "/search", element: <SearchPage /> },
      { path: "/me", element: <ProfilePage /> },
      { path: "/users/:username", element: <MemberPage /> },
      { path: "*", element: <SignInPage /> },
    ],
  },
]);

export function Router() {
  return <RouterProvider router={router} />;
}
