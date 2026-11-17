import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Layout } from "./Layout";
import { WorkspacePage } from "./pages/WorkspacePage";
import { LibraryPage, TopicPage } from "./pages/LibraryPage";
import { QuestionPage } from "./pages/QuestionPage";

/* The whole site is this client. Each route is a shape, not a widget: browsing is
   a document, a question is a workspace. All of them share one layout. */
const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/library", element: <LibraryPage /> },
      { path: "/library/:topicId", element: <TopicPage /> },
      { path: "/library/:topicId/:questionId", element: <QuestionPage /> },
      { path: "/app", element: <WorkspacePage /> },
      { path: "*", element: <LibraryPage /> },
    ],
  },
]);

export function Router() {
  return <RouterProvider router={router} />;
}
