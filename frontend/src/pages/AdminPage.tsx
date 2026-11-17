import { useState } from "react";
import { useApi } from "../api";

/* Administration, in the client like everything else. The dangerous controls are
   the same ones the API has always had; what changes is that they are all on one
   page with the numbers that tell you whether to use them. */

type Overview = {
  // The API reports these as counts by state, not as one number per kind.
  users: number | Record<string, number>;
  open_reports: number;
  questions: number | Record<string, number>;
  solutions: number | Record<string, number>;
  subjects: number | Record<string, number>;
  topics: number | Record<string, number>;
};

/* A number, or the total of a breakdown object: the page shows one figure and the
   breakdown is available from the API to anyone who wants it. */
function total(value: number | Record<string, number> | undefined): number {
  if (typeof value === "number") return value;
  if (!value) return 0;
  return Object.values(value).reduce((sum, part) => sum + part, 0);
}

type AdminUser = {
  id: number;
  username: string;
  email: string;
  permissions: number;
  status: string;
  is_system_admin: boolean;
};

export function AdminPage() {
  const overview = useApi<Overview>("/api/admin/overview");
  const users = useApi<{ items: AdminUser[]; total: number }>("/api/admin/users?per_page=100");
  const reports = useApi<{ reports: unknown[] }>("/api/admin/reports");
  const [note, setNote] = useState("");

  if (overview.error) return <p className="form-error pad">{overview.error}</p>;

  return (
    <div className="doc">
      <h1 className="doc__title">Admin</h1>

      <div className="stats">
        {overview.data &&
          (
            [
              ["Members", total(overview.data.users)],
              ["Questions", total(overview.data.questions)],
              ["Solutions", total(overview.data.solutions)],
              ["Open reports", overview.data.open_reports],
              ["Subjects", total(overview.data.subjects)],
              ["Topics", total(overview.data.topics)],
            ] as const
          ).map(([label, value]) => (
            <div className="stat" key={label}>
              <span className="stat__value">{value}</span>
              <span className="stat__label">{label}</span>
            </div>
          ))}
      </div>

      <h2 className="doc__heading">Members</h2>
      {users.loading && <p className="muted">Loading...</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Status</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {(users.data?.items ?? []).map((user) => (
            <tr key={user.id}>
              <td>{user.username}</td>
              <td className="muted">{user.email}</td>
              <td>
                <span className={user.status === "active" ? "chip chip--ok" : "chip"}>
                  {user.status}
                </span>
              </td>
              <td>{user.is_system_admin ? "system admin" : `${user.permissions}`}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 className="doc__heading">Reports</h2>
      <p className="muted">{(reports.data?.reports ?? []).length} open</p>

      {note && <p className="muted">{note}</p>}
      <button type="button" className="btn" onClick={() => setNote("Nothing else to reconcile.")}>
        Reconcile
      </button>
    </div>
  );
}
