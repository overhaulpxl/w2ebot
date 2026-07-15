export default function LoginPage() {
  return (
    <main className="login-shell">
      <section className="card card-pad login-panel">
        <span className="brand-mark" aria-hidden="true">W2</span>
        <h1>W2E Admin Dashboard</h1>
        <p className="muted">Masuk dengan akun Discord yang terotorisasi untuk server W2E.</p>
        <a className="btn btn-primary" href="/api/auth/login">Masuk dengan Discord</a>
      </section>
    </main>
  );
}
