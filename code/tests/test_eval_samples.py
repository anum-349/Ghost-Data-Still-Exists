import scripts.eval_samples as eval_samples


def test_sample_runner_generates_then_evaluates_predictions(monkeypatch):
    calls = []

    def run_cli(arguments):
        calls.append(("run", arguments))
        return 0

    def evaluate_cli(arguments):
        calls.append(("evaluate", arguments))
        return 0

    monkeypatch.setattr(eval_samples, "run_cli", run_cli)
    monkeypatch.setattr(eval_samples, "evaluate_cli", evaluate_cli)

    assert eval_samples.main() == 0
    assert [name for name, _ in calls] == ["run", "evaluate"]
    run_arguments = calls[0][1]
    evaluation_arguments = calls[1][1]
    assert run_arguments[run_arguments.index("--input") + 1] == str(
        eval_samples.REPO_ROOT / "dataset" / "sample_deletion_requests.csv"
    )
    assert run_arguments[run_arguments.index("--output") + 1] == str(
        eval_samples.REPO_ROOT / "sample_predictions.csv"
    )
    assert evaluation_arguments[evaluation_arguments.index("--predictions") + 1] == str(
        eval_samples.REPO_ROOT / "sample_predictions.csv"
    )
    assert evaluation_arguments[evaluation_arguments.index("--reference") + 1] == str(
        eval_samples.REPO_ROOT / "dataset" / "sample_output.csv"
    )


def test_sample_runner_skips_evaluation_when_generation_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(eval_samples, "run_cli", lambda arguments: calls.append(arguments) or 1)
    monkeypatch.setattr(eval_samples, "evaluate_cli", lambda _arguments: 0)

    assert eval_samples.main() == 1
    assert len(calls) == 1
