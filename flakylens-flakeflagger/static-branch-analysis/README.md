# Static branch analysis for FlakeFlagger's 799 tests

static analysis task: figure out what lines each test
could possibly execute, without compiling or running anything yet.

## Why no compiling

Compiling all 21 projects properly needs Docker and more setup than made
sense to do before checking if this was even worth building. So this phase
only reads each test's raw source code as text and works out its structure,
no build, no execution, no dependencies resolved.

## Checked if FlakeFlagger already did this first

Went through the FlakeFlagger paper's own feature set before writing
anything. Their static features are aggregate metrics per test, lines of
code, test smells, coverage percentage, and more. Nothing in
their feature set maps out branch points per test the way this task needed,
so this won't be a duplicate work.

## Tool: javalang

Considered Spoon and JavaParser first, since those are the standard Java
AST tools. Went with javalang instead, a pure Python Java parser, for one
main reason: this task only needs to look inside one test method at a time,
it doesn't need to trace calls into other classes. Spoon and JavaParser are
built for exactly that kind of cross-file resolution, which usually needs a
resolvable classpath (closer to needing a real build than we wanted for this
phase). javalang skips all of that. It's a straight pip install, works
directly with the raw method text already extracted in
`flaky_flakeflagger_with_project_info_with_method_bodies.csv`, and needs no
Java project setup at all.

One thing worth knowing: javalang can occasionally fail on very modern Java
syntax it doesn't support yet. Ran it against all 799 real tests and it
parsed every single one, 0 failures, so this hasn't been an issue on this
dataset.

## How the script works

`static_branch_analysis.py` takes each test's source code and looks for
every branch point: if/else, for, while, do-while, switch, try/catch/finally,
and ternary expressions. javalang needs a full Java file to parse, not a
bare method, so the script wraps each method in a minimal dummy class first
just to make it valid Java syntax, nothing about the wrapping affects the
analysis itself.

For each branch point found, it records the line number and what the
possible outcomes are, for example an if-statement either runs its
then-branch or it doesn't, a loop either runs zero times or one or more
times.

## Output structure

One `.txt` file per test, organized into 21 folders by project (matching
the same 21 projects from the error-log-analysis work). Each file lists
every branch point found in that test, or says it has none, meaning that
test always runs the same lines no matter what.

Example, for `Alluxio-alluxio/tachyon.DataServerTest#readPartialTest1.txt`:

```
Branch points found: 3

Line 18: if statement
    -> then-branch executes
    -> if-condition false, nothing in this if executes
Line 12: while statement
    -> loop body runs 0 times
    -> loop body runs 1+ times
Line 16: while statement
    -> loop body runs 0 times
    -> loop body runs 1+ times
```

This only tells you what's structurally possible, not what actually
happens when the test runs for real. That's the whole point of this phase,
and exactly what phase 2 (compiling and running with a coverage tool) is
for.

## Results

- 799 tests processed, 0 failed to parse
- 575 tests (72%) have zero branches, every line always executes the same way
- 224 tests (28%) have at least one branch point, 739 branch points total
  across them, about 3.3 per test on average

## Running it yourself

```
pip install javalang
python static_branch_analysis.py flaky_flakeflagger_with_project_info_with_method_bodies.csv branch_analysis_output
```

## What's next

Phase 2 needs actually compiling each project and running its tests for
real with a coverage tool attached (JaCoCo is the standard one for Java),
run multiple times per test. Then compare: does the real coverage match what
this static analysis said was possible, and does a test's real coverage
change between runs.

## Files

- `static_branch_analysis.py`, the analysis script
- `branch_analysis_output/`, 21 folders by project, one file per test inside each
