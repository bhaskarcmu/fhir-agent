# Notebooks

For exploring ideas. Two rules (docs/phase8/decisions.md O38):

1. **Commit notebooks only with outputs stripped** — `outcome-prediction-lab notebooks-strip <file>`.
   CI runs `outcome-prediction-lab notebooks-check` and fails on any output or execution count.
2. **A notebook can suggest an idea; it can't be evidence.** Anything quoted in a round report comes
   from a config run through the CLI.
