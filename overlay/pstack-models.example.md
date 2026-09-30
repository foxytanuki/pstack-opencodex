# pstack model configuration for Codex through opencodex. One line per role. Delete a line to fall back to the skill default.
# Values are <Codex catalog slug>-<effort>. `inherit-parent` or `auto` runs the role on the parent chat model.
# Upstream uses grok-4.7-xhigh-fast for code roles. Grok is not in this Codex catalog, so gpt-6.1-sol takes those roles.
# budget: unlimited (max)
feature, refactoring: gpt-6.1-sol-xhigh
bug-fix: gpt-6.1-sol-xhigh
perf-issue: gpt-6.1-sol-xhigh
hillclimb: gpt-6.1-sol-xhigh
judgment and prose: anthropic/claude-opus-5-5-max
hardest tasks: anthropic/claude-opus-5-5-max
how explorer: gpt-6.1-sol-xhigh
how explainer: anthropic/claude-opus-5-5-max
why investigators: gpt-6.1-sol-xhigh
why synthesizer: anthropic/claude-opus-5-5-max
reflect tooling: gpt-6.1-sol-max
reflect judgment, divergent, synthesizer: anthropic/claude-opus-5-5-max
arena runners: anthropic/claude-opus-5-5-max, gpt-6.1-sol-max, anthropic/claude-fable-5-1-max
arena cross-judge pool: anthropic/claude-opus-5-5-max, gpt-6.1-sol-max, anthropic/claude-fable-5-1-max
swarm workers: gpt-6.1-sol-xhigh
architect runners: anthropic/claude-opus-5-5-max, gpt-6.1-sol-max, anthropic/claude-fable-5-1-max
interrogate reviewers: anthropic/claude-opus-5-5-max, gpt-6.1-sol-max, anthropic/claude-fable-5-1-max
