import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

/* Why this member cannot use the site.

   A banned or revoked member is signed in but not active, so the shell sends them here
   instead of the front door. This is the same message the server-rendered page carried:
   what happened, and that their work is on record rather than deleted. It reads
   /api/auth/me because that endpoint answers for any signed-in member, whatever their
   status. */

type State = {
  status?: string;
  username?: string;
  /** Whose action removed access: an administrator's ban, or a revoked chain. */
  invited_by?: string | null;
  inviter_status?: string | null;
};

export function StatusPage() {
  const [me, setMe] = useState<State | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    let live = true;
    void api<State>("/api/auth/status")
      .then((data) => {
        if (live) setMe(data);
      })
      .catch(() => {
        // No session at all: there is nothing to explain, so offer the way in.
        if (live) setGone(true);
      });
    return () => {
      live = false;
    };
  }, []);

  if (gone) {
    return (
      <div className="anon">
        <div className="anon__card">
          <p className="eyebrow">Not signed in</p>
          <h1>There is no session to explain.</h1>
          <Link className="btn btn--primary" to="/">
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  if (!me) return <p className="muted pad">Loading...</p>;

  const banned = me.status === "banned";
  // A revoked member was not banned themselves: the chain above them was cut.
  const byBan = me.inviter_status === "banned";

  return (
    <div className="anon">
      <div className="anon__card">
        <p className="eyebrow">{banned ? "Account banned" : "Access revoked"}</p>
        <h1>
          {banned
            ? `@${me.username} was banned by the system administrator.`
            : me.invited_by
              ? byBan
                ? `@${me.invited_by} was banned, so your access went with it.`
                : `@${me.invited_by} revoked the invitations under them.`
              : `@${me.username} no longer has access.`}
        </h1>
        <p className="muted">
          Your account and everything you posted are hidden from the review group. The
          questions and solutions themselves stay on record, so nothing was deleted.
        </p>
        <p className="muted">
          Access has to come from a new invitation from another person.
        </p>
        <Link className="btn" to="/">
          Back to the front door
        </Link>
      </div>
    </div>
  );
}
