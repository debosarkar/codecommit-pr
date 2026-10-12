import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "score_review", Path(__file__).resolve().parents[1] / "scripts" / "score_review.py")
score_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_review)

EXPECTED = [
    {"id": "py-sqli", "file": "orders.py", "lines": [10, 12]},
    {"id": "ts-float", "file": "userService.ts", "lines": [20, 20]},
]


def test_score_counts_found_missed_and_noise():
    comments = [
        {"file": "orders.py", "line": 11},
        {"file": "orders.py", "line": 11},  # second hit on the same issue is not noise
        {"file": "orders.py", "line": 40},  # unplanted -> noise
    ]
    result = score_review.score(EXPECTED, comments)
    assert result == {"found": ["py-sqli"], "missed": ["ts-float"], "noise": 1, "recall": 0.5}
