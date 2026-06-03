# Package Layout

The package is grouped by responsibility:

- `core/`: task/run schemas, scoring, judging, and token utilities
- `datasets/`: loaders for BABILong, OOLONG, LongMemEval, SWE-chat, and CLB-style rows
- `memory/`: compression and context-access methods
  - offline compression
  - paged context
  - virtual context / search + notes
  - hierarchical memory
  - BABILong state extraction
- `runners/`: Codex and Claude execution harnesses
- `taskgen/`: synthetic task generators for controlled experiments
- `cli.py`: Typer CLI entry point used by `cbench`
