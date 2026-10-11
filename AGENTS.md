# Orpheus development

- Keep the program small: Codex handles research leadership and collaboration; Skills describe research and independent review.
- Preserve immutable candidates, bound cold reviews, append-only Fact versions and dependency invalidation. Never directly edit accepted Facts.
- Keep this source checkout separate from installed research data. Tests use temporary repositories and synthetic inputs.
- Do not commit runtime Facts, candidates, reviews, research notes, credentials, local paths or inherited research history to the public repository.
- User-facing Markdown must be UTF-8 and Obsidian compatible, with `$...$` and `$$...$$` math delimiters.
- Run relevant tests and distinguish configuration validation from actual mathematical or model-behavior validation.
