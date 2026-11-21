import { createBrowserRouter, Navigate, RouterProvider, useParams } from "react-router-dom";
import { Layout } from "./Layout";
import { WorkspacePage } from "./workspace/WorkspacePage";
import { ResourcePage } from "./pages/ResourcePage";
import { TagsPage, TagPage } from "./pages/TagsPage";
import { QuizListPage, QuizRunPage, QuizBuildPage } from "./pages/QuizPage";
import { AdminPage } from "./pages/AdminPage";
import { SearchPage, ProfilePage, MemberPage } from "./pages/MiscPages";
import { SignInPage } from "./pages/SignInPage";
import { StatusPage } from "./pages/StatusPage";
import { RegisterPage } from "./pages/RegisterPage";

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
      /* The workspace is the only place a question is opened. These addresses are kept
         because they are in every bookmark and every link the site has issued, and they
         now carry the reader into /app with the right panel already open. */
      { path: "/problem-sets", element: <Navigate to="/app?panel=problems" replace /> },
      { path: "/problem-sets/:topicId", element: <TopicRedirect /> },
      { path: "/problem-sets/:topicId/:questionId", element: <QuestionRedirect /> },
      /* The first React build put questions under /library/<topic>/<question>, and
         every link and bookmark made since then carries that shape. They are
         redirected rather than dropped: a question that used to open and now lands
         on a sign-in page is indistinguishable from lost work. */
      { path: "/library", element: <Navigate to="/problem-sets" replace /> },
      { path: "/library/:topicId", element: <LibraryRedirect /> },
      { path: "/library/:topicId/:questionId", element: <LibraryRedirect /> },
      { path: "/app", element: <WorkspacePage /> },
      { path: "/tags", element: <TagsPage /> },
      { path: "/tags/:name", element: <TagPage /> },
      { path: "/quiz", element: <QuizListPage /> },
      { path: "/quiz/new", element: <QuizBuildPage /> },
      { path: "/quiz/:uid", element: <QuizRunPage /> },
      { path: "/admin", element: <AdminPage /> },
      /* Writing and editing live in the workspace. These addresses are kept for links
         already issued, and carry the reader there with the editor open. */
      { path: "/questions/new", element: <Navigate to="/app?panel=questionedit" replace /> },
      { path: "/questions/:questionId/edit", element: <QuestionEditRedirect /> },
      { path: "/library/:topicId/pages/:kind/edit", element: <PageEditRedirect /> },
      { path: "/search", element: <SearchPage /> },
      { path: "/status", element: <StatusPage /> },
      { path: "/register", element: <RegisterPage /> },
      { path: "/me", element: <ProfilePage /> },
      { path: "/users/:username", element: <MemberPage /> },
      { path: "*", element: <SignInPage /> },
    ],
  },
]);

/** A topic, opened in the workspace. */
function TopicRedirect() {
  const { topicId } = useParams();
  return <Navigate to={`/app?panel=problems&topicId=${topicId}`} replace />;
}

/** A question, opened in the workspace with its own panel. */
function QuestionRedirect() {
  const { topicId, questionId } = useParams();
  return (
    <Navigate
      to={`/app?panel=question&questionId=${questionId}&topicId=${topicId}`}
      replace
    />
  );
}

/** A question, opened for editing. */
function QuestionEditRedirect() {
  const { questionId } = useParams();
  return <Navigate to={`/app?panel=questionedit&questionId=${questionId}`} replace />;
}

/** One of a topic's resource sheets, opened for editing. */
function PageEditRedirect() {
  const { topicId, kind } = useParams();
  return <Navigate to={`/app?panel=pageedit&topicId=${topicId}&kind=${kind}`} replace />;
}

/** An old /library address, carried to the problem set it now belongs to. */
function LibraryRedirect() {
  const { topicId, questionId } = useParams();
  const target = questionId
    ? `/problem-sets/${topicId}/${questionId}`
    : `/problem-sets/${topicId}`;
  return <Navigate to={target} replace />;
}

export function Router() {
  return <RouterProvider router={router} />;
}
