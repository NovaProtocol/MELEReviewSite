import { Outlet } from "react-router-dom";
import { TopBar } from "./Chrome";

/* One layout for every route: the header, then the page. Pages differ in shape,
   not in chrome, which is why there is exactly one header component. */
export function Layout() {
  return (
    <div className="app">
      <TopBar />
      <Outlet />
    </div>
  );
}
