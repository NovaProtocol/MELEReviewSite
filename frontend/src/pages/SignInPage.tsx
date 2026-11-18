import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

/* The front door, as it was: what this is on the left, a compact sign-in card on
   the right. It is a landing page, not a login screen that happens to have words
   on it, and the card stays small. */
export function SignInPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "",
        },
        credentials: "include",
        body: JSON.stringify({ identifier, password }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail ?? "Wrong username or password");
      // Back where they were going, which is what a login interrupted.
      navigate(params.get("next") ?? "/app");
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="landing">
      <section className="landing__hero">
        <p className="eyebrow">Philippine mechanical engineering licensure</p>
        <h1 className="landing__title">Review by subject and topic.</h1>
        <p className="landing__lede">A shared question bank with worked solutions.</p>

        <div className="landing__stats">
          <div className="landing__stat">
            <span className="landing__value">3</span>
            <span className="landing__label">subjects</span>
          </div>
          <div className="landing__stat">
            <span className="landing__value">58</span>
            <span className="landing__label">topics</span>
          </div>
          <div className="landing__stat">
            <span className="landing__value">7</span>
            <span className="landing__label">study tools</span>
          </div>
        </div>

        <div className="landing__subjects">
          {[
            "Mathematics",
            "Power & Industrial Plant Engineering",
            "Machine Design & Shop Practice",
          ].map((name) => (
            <div className="landing__subject" key={name}>
              <h2>{name}</h2>
            </div>
          ))}
        </div>
      </section>

      <section className="landing__auth">
        <div className="auth-card">
          <h2 className="auth-card__title">Sign in</h2>
          <p className="auth-card__sub">Username or email.</p>

          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="identifier">Username or email</label>
              <input
                id="identifier"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? "Signing in..." : "Log in"}
            </button>
          </form>

          <p className="auth-card__foot">Invitation only. You need a code from a member.</p>
        </div>
      </section>
    </div>
  );
}
