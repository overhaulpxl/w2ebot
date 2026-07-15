from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "dashboard-example"


class Phase9ADashboardContractTests(unittest.TestCase):
    def test_pages_and_routes_use_session_boundary(self):
        self.assertIn("requireDashboardSession", (ROOT / "app" / "page.tsx").read_text(encoding="utf-8"))
        self.assertIn("SESSION_COOKIE", (ROOT / "middleware.ts").read_text(encoding="utf-8"))
        public_auth = {
            ROOT / "app" / "api" / "auth" / "login" / "route.ts",
            ROOT / "app" / "api" / "auth" / "callback" / "route.ts",
        }
        for path in (ROOT / "app" / "api").rglob("route.ts"):
            if path in public_auth:
                continue
            self.assertIn("getDashboardSession", path.read_text(encoding="utf-8"), str(path))

    def test_browser_never_uses_bot_api_or_dashboard_token(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "components").glob("*.tsx"))
        self.assertNotIn("NEXT_PUBLIC_BOT_API_URL", source)
        self.assertNotIn("DASHBOARD_TOKEN", source)
        self.assertNotIn("/api/admin/coins", source)

    def test_secure_cookie_and_signing_contract(self):
        auth = (ROOT / "lib" / "dashboardAuth.ts").read_text(encoding="utf-8")
        signing = (ROOT / "lib" / "internalRequest.ts").read_text(encoding="utf-8")
        self.assertIn('__Host-w2e_admin_session', auth)
        for value in ("httpOnly: true", "secure: true", 'sameSite: "lax"'):
            self.assertIn(value, auth)
        self.assertIn('"W2E-P9A"', signing)
        self.assertNotIn("DASHBOARD_TOKEN", signing)
