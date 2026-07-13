import unittest

from ghost_master_recovery import resolve_target_account


class ResolveTargetAccountTests(unittest.TestCase):
    def test_handles_typo(self):
        available = ['Francis_Architect', 'ghost_admin']
        self.assertEqual(
            resolve_target_account('Francis_Arhitect', available),
            'Francis_Architect',
        )

    def test_returns_default_when_available(self):
        available = ['ghost_admin', 'Francis_Architect']
        self.assertEqual(
            resolve_target_account('', available, default_username='ghost_admin'),
            'ghost_admin',
        )


if __name__ == '__main__':
    unittest.main()
