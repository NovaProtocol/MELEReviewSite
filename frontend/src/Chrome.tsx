/* The shared chrome. One header for the whole site, built from the fleet's theme
   tokens so it looks like every other page and follows the light/dark toggle.

   Pages are not all the same shape: a library page is a document, the question
   page is a workspace. What they share is this header, the rail when they need
   one, and the token set. */

import { NavLink, useNavigate } from "react-router-dom";
import { bootstrap } from "./tools";

const ICONS: Record<string, string> = {
  library: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5Zm0 0V21M8 7h8M8 11h6",
  calculator:
    "M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 4v3h6V7Zm0 6h2v2H9Zm4 0h2v2h-2Zm-4 4h2v2H9Zm4 0h2v2h-2Z",
  converter: "M4 7h11l-2.5-2.5M20 17H9l2.5 2.5",
  formula: "M5 5h9M9 5c-1.8 0-2.6 1-2.6 3v8c0 2-.8 3-2.6 3M14 9l5 6m0-6-5 6",
  tools: "M14 4l6 6-9 9H5v-6Z",
  quiz: "M9 3h6a1 1 0 0 1 1 1v1h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2V4a1 1 0 0 1 1-1Zm-1 8h8M8 15h5",
  tags: "M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9Zm5-5.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
  admin: "M12 3l8 4v6c0 4-3.4 7.3-8 8-4.6-.7-8-4-8-8V7Z",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm6 13-4-4",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m11.4 0 1.4 1.4M4.9 4.9l1.4 1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0",
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path
        d={ICONS[name] ?? ""}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function RailButton({
  icon,
  label,
  onClick,
  active,
  title,
}: {
  icon: string;
  label: string;
  onClick?: () => void;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      className={`rail__btn${active ? " is-active" : ""}`}
      onClick={onClick}
      title={title ?? label}
    >
      <Icon name={icon} />
      <span>{label}</span>
    </button>
  );
}

export function ThemeToggle() {
  return (
    <button
      type="button"
      className="ui-theme-toggle"
      aria-label="Toggle light and dark"
      title="Light / dark"
      onClick={() => {
        const next =
          document.documentElement.dataset.theme === "light" ? "dark" : "light";
        document.documentElement.dataset.theme = next;
        localStorage.setItem("ui-theme", next);
      }}
    >
      <Icon name="sun" size={16} />
    </button>
  );
}

const LINKS = [{ to: "/app", label: "Workspace" }];

export function TopBar() {
  const navigate = useNavigate();
  const viewer = bootstrap.viewer;

  return (
    <header className="topbar">
      <NavLink className="topbar__brand" to="/app">
        ~/<span>melereview</span>
      </NavLink>

      <nav className="topbar__nav">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => `topbar__link${isActive ? " is-active" : ""}`}
          >
            {link.label}
          </NavLink>
        ))}
        {viewer.is_admin && (
          <NavLink to="/admin" className="topbar__link">
            Admin
          </NavLink>
        )}
      </nav>

      <div className="topbar__spacer" />

      <button
        type="button"
        className="topbar__action"
        onClick={() => navigate("/search")}
        title="Search"
        aria-label="Search"
      >
        <Icon name="search" size={16} />
      </button>

      <ThemeToggle />

      <NavLink to="/me" className="topbar__user" title="Your page">
        <span className="topbar__avatar">
          {viewer.avatar ? <img src={viewer.avatar} alt="" /> : viewer.username.slice(0, 1).toUpperCase()}
        </span>
        <span className="topbar__name">{viewer.username}</span>
      </NavLink>

      <button
        type="button"
        className="topbar__action"
        title="Sign out"
        aria-label="Sign out"
        onClick={async () => {
          await fetch("/api/auth/logout", {
            method: "POST",
            headers: {
              "X-CSRF-Token": document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "",
            },
            credentials: "include",
          });
          window.location.href = "/";
        }}
      >
        →
      </button>
    </header>
  );
}
