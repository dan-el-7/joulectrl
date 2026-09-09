"""tests/unit/test_explain.py — Tests for explanation layer (facts, templates, providers)."""

import json
from pathlib import Path
import unittest

from core.models import Configuration, Profile, Selection, ValidationPair
from explain.facts import extract_explanation_facts
from explain.providers import BasicProvider, LocalLlamaProvider, CloudOpenAIProvider, get_provider
from explain.templates import generate_explanation

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "synthetic"


class TestExplanationLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load synthetic fixtures
        with open(FIXTURES_DIR / "synthetic_profile.json", "r", encoding="utf-8") as f:
            cls.profile = Profile.from_dict(json.load(f))
        with open(FIXTURES_DIR / "synthetic_selection.json", "r", encoding="utf-8") as f:
            cls.selection = Selection.from_dict(json.load(f))
        with open(FIXTURES_DIR / "synthetic_validation_pairs.json", "r", encoding="utf-8") as f:
            cls.val_pairs = [ValidationPair.from_dict(p) for p in json.load(f)]

    def test_extract_facts(self):
        facts = extract_explanation_facts(
            selection=self.selection,
            profile=self.profile,
            validation_pairs=self.val_pairs,
        )
        self.assertEqual(facts["objective_mode"], "deadline")
        self.assertEqual(facts["status"], "selected")
        self.assertEqual(facts["selected_config"]["id"], "cfg_zen5c_4c_3000")
        self.assertEqual(facts["baseline_config"]["id"], "cfg_stock_all")
        self.assertAlmostEqual(facts["energy_reduction_pct"], 44.6, places=1)
        self.assertAlmostEqual(facts["runtime_increase_pct"], 55.4, places=1)

        # Lowest energy overall was cfg_zen5c_4c_2000 (810J) and exceeded budget (62.8s > 48.0s)
        lowest = facts["lowest_energy_overall"]
        self.assertIsNotNone(lowest)
        self.assertEqual(lowest["id"], "cfg_zen5c_4c_2000")
        self.assertFalse(lowest["was_selected"])
        self.assertTrue(lowest["exceeded_budget"])

        # Validation summary
        val = facts["validation"]
        self.assertIsNotNone(val)
        self.assertEqual(val["total_pairs"], 3)
        self.assertEqual(val["met_budget_count"], 3)
        self.assertTrue(val["validation_passed"])

    def test_deadline_template_explanation(self):
        facts = extract_explanation_facts(
            selection=self.selection,
            profile=self.profile,
            validation_pairs=self.val_pairs,
        )
        text = generate_explanation(facts)
        self.assertIn("cfg_zen5c_4c_3000", text)
        self.assertIn("875.2 J", text)
        self.assertIn("48.0s runtime rule", text)
        self.assertIn("44.6%", text)
        self.assertIn("cfg_stock_all", text)
        self.assertIn("excluded because its guarded runtime", text)
        self.assertIn("3 of 3 validation runs finished within the budget", text)

    def test_preference_template_explanation(self):
        pref_sel = Selection(
            experiment_id="exp-pref",
            objective_mode="preference",
            status="selected",
            status_message="Selected",
            selected_config_id="cfg_zen5c_4c_3000",
            selected_configuration=self.selection.selected_configuration,
            selected_median_energy_j=875.2,
            selected_median_runtime_s=44.3,
            baseline_config_id="cfg_stock_all",
            baseline_median_energy_j=1580.0,
            baseline_median_runtime_s=28.5,
            energy_reduction_pct=44.6,
            runtime_increase_pct=55.4,
            energy_target_pct=70.0,
            perf_floor_pct=60.0,
            preference_outcome_state="both_met",
        )
        facts = extract_explanation_facts(pref_sel, self.profile, self.val_pairs)
        text = generate_explanation(facts)
        self.assertIn("Preference Mode targets", text)
        self.assertIn("energy ≤ 70.0%", text)
        self.assertIn("performance ≥ 60.0%", text)
        self.assertIn("satisfies both targets", text)
        self.assertIn("44.6% energy reduction", text)

    def test_edge_states(self):
        # 1. No feasible point
        no_feas = Selection(
            experiment_id="exp-edge",
            objective_mode="deadline",
            status="no_feasible_point",
            status_message="No configuration met deadline",
            deadline_s=25.0,
        )
        facts = extract_explanation_facts(no_feas)
        text = generate_explanation(facts)
        self.assertIn("No feasible configuration found meeting your runtime budget of 25.0s", text)

        # 2. Baseline already optimal
        base_opt = Selection(
            experiment_id="exp-edge",
            objective_mode="deadline",
            status="baseline_already_optimal",
            status_message="Baseline already best",
            deadline_s=40.0,
        )
        facts = extract_explanation_facts(base_opt)
        text = generate_explanation(facts)
        self.assertIn("baseline configuration is already the lowest-energy", text)

        # 3. Within noise
        noise = Selection(
            experiment_id="exp-edge",
            objective_mode="deadline",
            status="within_noise",
            status_message="Within noise",
            deadline_s=40.0,
        )
        facts = extract_explanation_facts(noise)
        text = generate_explanation(facts)
        self.assertIn("within observed measurement variation", text)

    def test_provider_fallback(self):
        facts = extract_explanation_facts(self.selection, self.profile, self.val_pairs)
        
        # Basic provider
        basic = BasicProvider()
        res_basic = basic.explain(facts)
        self.assertTrue(len(res_basic) > 50)

        # Local Llama fallback when offline
        llama = LocalLlamaProvider(endpoint_url="http://127.0.0.1:9999/v1/chat/completions", timeout_s=0.5)
        res_llama = llama.explain(facts)
        # Should gracefully fall back to basic template!
        self.assertEqual(res_llama, res_basic)

        # Cloud fallback when invalid key / endpoint
        cloud = CloudOpenAIProvider(api_key="", base_url="http://127.0.0.1:9999/v1")
        res_cloud = cloud.explain(facts)
        self.assertEqual(res_cloud, res_basic)

        # Factory
        prov = get_provider("basic")
        self.assertIsInstance(prov, BasicProvider)


if __name__ == "__main__":
    unittest.main()
