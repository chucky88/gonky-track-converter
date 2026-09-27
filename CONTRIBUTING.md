# Contributing

The tool was built by converting **a handful of tracks**, test after test. Every new track has brought
something it didn't handle yet: another shader, another way of building the physics, lights declared
differently, a chicane before the finish line… **The more tracks go through it, the better it gets.**
All help counts, even if you don't write code.

## Without writing code

- **Tell us how it went.** Every conversion writes `<work folder>/<id>/REPORT.md`: what the tool found
  in the track (shaders, surfaces, lights, unclassified materials) and which gates passed. It contains
  nothing from the mod and no paths from your computer. Attach it to an issue:
  - **Working conversion** if it works → it goes into [the compatibility list](docs/COMPATIBILITY.md);
  - **New case** if the track does something the tool doesn't handle;
  - **Conversion problem** if something goes wrong.
- **Share what you know** with the **Lesson learned** template: why something fails, or a trick that
  works. Check [docs/LESSONS.md](docs/LESSONS.md) first, it may already be there.

## Writing code

1. **A gate is born from a real, measured failure.** If something went wrong in game without any gate
   noticing, the new gate must **fail on the broken case** before you trust it, and pass on a good one.
   A check that has never failed proves nothing.
2. **One change at a time.** If a change touches five things and something breaks, there's no way to
   know which.
3. **Compare the package before and after** (which files come in, go out and change): a change that
   shouldn't touch the lights can't change the `_lights.sgx`.
4. **Every parameter is read from the mod, never assumed**: that it's 1 on one track says nothing about
   the next.
5. **Document the why** in the code (what broke and how it showed) and, if it's a lesson of general
   interest, in [docs/LESSONS.md](docs/LESSONS.md).
6. Run the tests: `python3 -m unittest discover -s tests -t tests`.

Note: the code's identifiers (functions, variables, module names) are in Spanish — the tool started as
an in-house project. Comments, docs, messages and options are in English. Issues and pull requests are
welcome in English or Spanish.
