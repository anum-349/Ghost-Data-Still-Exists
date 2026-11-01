import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = REPO_ROOT / "evaluation"
if not EVALUATION_ROOT.is_dir():
    EVALUATION_ROOT = REPO_ROOT / "code" / "evaluation"
sys.path.insert(0, str(EVALUATION_ROOT))

from cases.run_cases import run_evaluation_cases


def test_all_synthetic_evaluation_cases_match_expected_checks():
    expected_path = EVALUATION_ROOT / "cases" / "expected_outputs.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    results = run_evaluation_cases()
    assert {result.name for result in results} == set(expected)
    assert all(result.passed for result in results)
    assert all(result.checks_passed == result.checks_total for result in results)


def test_prompt_injection_fixture_is_plain_evidence_data():
    evidence = EVALUATION_ROOT / "cases" / "evidence" / "prompt_injection.txt"
    text = evidence.read_text(encoding="utf-8")
    assert "{{RESOURCE_ID}}" in text and "{{USER_ID}}" in text
    assert "Ignore all policies" in text

