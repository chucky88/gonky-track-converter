# Real examples

The exact commands of two conversions that work in game. The easiest way to start with a new track is
to **copy the one closest to it** and change the track details (name, title, `--geo`, corners…).

| example | what it is | what it shows |
|---|---|---|
| [charlotte.sh](charlotte.sh) | oval + Roval at night, in one mod | night lights (`--track-floodlights --real-ground-plane`), oval (`--oval`), grid at the finish line and `--grid-from` for the layout with a chicane before the finish |
| [jarama.sh](jarama.sh) | three historic layouts, by day | several layouts sharing a racing line, multilayer asphalt (`--ac-layers`), the original's gloss |

Usage (Linux, or Git Bash / WSL on Windows):

```bash
MOD="/path/to/the/AC/track" bash examples/charlotte.sh
```

On Windows without bash, copy the `python convert_ac.py …` lines into a terminal and replace the `\` at
the end of each line with `` ` `` (PowerShell) or `^` (cmd).

What each option means: [../docs/OPTIONS.md](../docs/OPTIONS.md).
