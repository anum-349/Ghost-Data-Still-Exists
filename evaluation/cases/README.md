# Synthetic evaluation cases

`scenarios.json` describes four distinct stress scenarios. `expected_outputs.json` contains their expected behavior checks; the harness creates fresh case, user, evidence, resource, and email identifiers at runtime, then loads policy from `dataset/deletion_rules.csv`.

Run the cases together with the sample-output evaluator:

```bash
python evaluation/run_eval.py --predictions output.csv
```

The prompt-injection text in `evidence/prompt_injection.txt` is untrusted fixture data. The harness parses it as content and exercises policy/planning code without executing it or passing it as model instructions.
