import json
import os
import tempfile
import unittest

from smart_recovery.toolkit.seeds import (
    SeedCatalog,
    build_seed_catalog,
    load_note_seed_payload,
)


class SeedCatalogTests(unittest.TestCase):
    def test_extracts_wallet_labels_and_recent_wallets_and_filters_stopwords(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_root = os.path.join(temp_dir, "recovery")
            shared_prefs = os.path.join(recovery_root, "shared_prefs")
            os.makedirs(shared_prefs)

            with open(os.path.join(shared_prefs, "Wallet sample.xml"), "w", encoding="utf-8") as handle:
                handle.write(
                    """
                    <map>
                      <string name="wallet_name_key">Wallet sample</string>
                    </map>
                    """
                )

            with open(os.path.join(shared_prefs, "f_Tron_3.8.0.xml"), "w", encoding="utf-8") as handle:
                handle.write(
                    """
                    <map>
                      <string name="key_recently_wallet">["alex orbit 204","alexorbit204","Wallet sample#1"]</string>
                    </map>
                    """
                )

            note_payload = {
                "labels": ["usuario alex orbit", "alex orbit 204"],
                "names": ["Marina", "Alex"],
                "numbers": ["204", "1"],
                "symbols": ["#", "."],
            }
            note_file = os.path.join(temp_dir, "note_seeds.json")
            with open(note_file, "w", encoding="utf-8") as handle:
                json.dump(note_payload, handle)

            catalog = build_seed_catalog(recovery_root=recovery_root, note_seed_file=note_file)

        self.assertIn("alexorbit204", catalog.labels)
        self.assertIn("alex orbit 204", catalog.labels)
        self.assertIn("wallet sample", catalog.labels)
        self.assertIn("wallet sample#1", catalog.labels)
        self.assertNotIn("usuario", catalog.names)
        self.assertIn("marina", catalog.names)
        self.assertIn("alex", catalog.names)
        self.assertIn("orbit", catalog.extensions)
        self.assertIn("204", catalog.numbers)
        self.assertIn("#", catalog.symbols)

    def test_load_note_seed_payload_defaults_to_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = load_note_seed_payload(os.path.join(temp_dir, "missing.json"))

        self.assertEqual(payload, {})

    def test_seed_fingerprint_changes_with_note_content(self):
        left = SeedCatalog(
            names=("alex",),
            extensions=("orbit",),
            labels=("alex orbit 204",),
            numbers=("204",),
            symbols=("#",),
            source_tags=("artifact:wallet",),
        )
        right = SeedCatalog(
            names=("alex", "marina"),
            extensions=("orbit",),
            labels=("alex orbit 204",),
            numbers=("204",),
            symbols=("#",),
            source_tags=("artifact:wallet", "note:name"),
        )

        self.assertNotEqual(left.fingerprint(), right.fingerprint())


if __name__ == "__main__":
    unittest.main()
