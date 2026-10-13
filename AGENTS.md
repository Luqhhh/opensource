# Project instructions

- Keep user-owned repositories, documents and source files read-only during checks; export patches for review.
- Execute snippets only with the fail-closed isolated runner. Never add an automatic host-execution fallback.
- Preserve evaluator-owned assertions, checks and expected outputs. Do not classify model-added assertions as independent evidence.
- Distinguish recorded-candidate replay, synthetic fixtures, historical compatibility reproductions, and live-model results in reports and documentation.
- Runtime dependencies should stay minimal. Document any new third-party dependency, model, dataset or copied resource in docs/resources.md.
- Run core tests with `python3 -m unittest discover -s tests -v`; for runner changes also run `EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v` where Bubblewrap is permitted.
- Do not claim contest submission or evaluation results before they are completed and verified.
