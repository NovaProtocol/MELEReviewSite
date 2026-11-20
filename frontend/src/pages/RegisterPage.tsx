import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post } from "../api";

/* Creating an account.

   Registration needs an invitation code; that is how the review group stays a group. The
   code can arrive in the address, so a link from an existing member fills it in. */

export function RegisterPage() {
  const navigate = useNavigate();
  const [query] = useSearchParams();
  const [code, setCode] = useState(query.get("code") ?? "");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setProblem("");
    setBusy(true);
    try {
      await post("/api/auth/register", {
        invite_code: code.trim(),
        username: username.trim(),
        email: email.trim(),
        password,
      });
      // The server sets the session on register, so the workspace is the next step.
      navigate("/app", { replace: true });
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anon">
      <form className="anon__card" onSubmit={submit}>
        <h1>Create your account</h1>
        <p className="muted">
          Registration needs an invitation code from an existing member.
        </p>

        <label className="field">
          <span>Invitation code</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="16 characters"
            autoComplete="off"
            spellCheck={false}
            required
          />
          <span className="muted field-note">It can only be used once.</span>
        </label>

        <label className="field">
          <span>Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            minLength={3}
            maxLength={32}
            required
          />
          <span className="muted field-note">Visible on what you post. You can change it later.</span>
        </label>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            maxLength={254}
            required
          />
          <span className="muted field-note">Used to sign in. Never shown to other members.</span>
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          <span className="muted field-note">At least 8 characters.</span>
        </label>

        {problem && <p className="form-error">{problem}</p>}

        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? "Creating..." : "Create account"}
        </button>

        <Link className="btn btn--quiet" to="/">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
