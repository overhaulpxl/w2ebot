from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase9ARouteTests(unittest.TestCase):
    def test_public_surface_and_legacy_tombstones(self):
        source = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertIn("app.router.add_get('/healthz', public_health)", source)
        self.assertIn("legacy_dashboard_read_disabled", source)
        self.assertIn("legacy_dashboard_write_disabled", source)
        self.assertNotIn("Access-Control-Allow-Origin'] = '*'", source)
        self.assertIn("/internal/phase9a/read/{resource:.+}", source)

    def test_no_legacy_mutation_proxy_files(self):
        admin = ROOT / "dashboard-example" / "app" / "api" / "admin"
        forbidden = {"coins", "xp", "give-item", "reset-all-players", "reset-player", "announce", "boss-spawn"}
        found = {path.parent.name for path in admin.rglob("route.ts")}
        self.assertFalse(found & forbidden)

    def test_deal_unchanged_by_phase9a_imports(self):
        source = (ROOT / "cogs" / "deal.py").read_text(encoding="utf-8")
        self.assertNotIn("phase9a", source.lower())

    def test_direct_aiohttp_public_and_protected_surfaces(self):
        handle, database = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        script = r'''
import asyncio, json
from aiohttp.test_utils import TestClient, TestServer
import core
from economy.phase9a_migrations import LEGACY_READ_ROUTES, LEGACY_WRITE_ROUTES
async def run():
    client = TestClient(TestServer(core.build_web_application()))
    await client.start_server()
    try:
        health = await client.get('/healthz')
        assert health.status == 200 and await health.json() == {'status': 'ok'}
        for template in LEGACY_READ_ROUTES:
            path = template.replace('{id}', '123456789012345678')
            response = await client.get(path)
            assert response.status == 410, (path, response.status)
        for template in LEGACY_WRITE_ROUTES:
            path = template.replace('{id}', '123456789012345678')
            response = await client.post(path, json={})
            assert response.status == 410, (path, response.status)
        response = await client.post('/internal/phase9a/health', json={})
        assert response.status in (401,503)
        internal_resources = {
            'server': {}, 'radar': {}, 'channels': {}, 'announce-config': {},
            'leaderboard': {}, 'user': {'params': {'id': '123456789012345678'}},
            'market': {}, 'treasury': {}, 'boss': {}, 'economy/stats': {},
            'economy/supply': {},
            'economy/profile': {'params': {'id': '123456789012345678'}},
            'economy/level-distribution': {}, 'economy/marketplace': {},
            'economy/casino': {}, 'economy/crypto': {}, 'economy/mining': {},
            'economy/phase8': {}, 'marriages': {}, 'stats/summary': {}, 'bot/stats': {},
        }
        for resource, payload in internal_resources.items():
            response = await client.post('/internal/phase9a/read/' + resource, json=payload)
            assert response.status in (401,503), (resource, response.status)
            response = await client.post('/internal/phase9a/read/' + resource, json=payload,
                                         headers={'Origin': 'https://dashboard.example'})
            assert response.status in (401,403,503), (resource, response.status)
    finally:
        await client.close()
asyncio.run(run())
'''
        env = os.environ.copy()
        env.update({"DATABASE_PATH": database, "DISCORD_TOKEN": "test", "GEMINI_API_KEY": "test",
                    "ECONOMY_V1_ENABLED": "false", "ECONOMY_PHASE2_ENABLED": "false",
                    "ECONOMY_PHASE3_ENABLED": "false", "ECONOMY_PHASE4_ENABLED": "false",
                    "ECONOMY_PHASE5_ENABLED": "false", "ECONOMY_PHASE6_ENABLED": "false",
                    "ECONOMY_PHASE7_ENABLED": "false", "ECONOMY_PHASE8_ENABLED": "false"})
        try:
            result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            os.remove(database)
