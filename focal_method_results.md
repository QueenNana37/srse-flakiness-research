# Focal Method Finding Results

Using Jaccard similarity (steps 4 & 6 of the UTFix-based pipeline) to
identify the focal method (method under test) for each flaky test.
Devanshi's script (steps 1, 2, 3, 5) extracts candidate methods via
AST parsing; this scorer picks the best match by token overlap.

---

## edn-java — testPrettyPrinting (ID-flaky)

**Commit:** 4cf29ffe2d063269cb09c9bf4f6fd5c1a3cb4e1b
**Flaky test:** us.bpsm.edn.printer.PrinterTest#testPrettyPrinting

### Pipeline result
Focal method picked: `prettyPrinterProtocol` (score=0.2)

### Manual verification
Incorrect. The actual method under test is `printString` — confirmed
by reading the source (Printers.printString(Printers.prettyPrinterProtocol(), list)).

### Root cause
Tokenizer limitation, not a logic bug. "testPrettyPrinting" tokenizes
to [pretty, printing, test]; "printString" tokenizes to [print, string].
No stemming, so "printing" and "print" don't match as tokens even
though they share a root word. printString scored 0.0 and lost to
prettyPrinterProtocol, which only won by coincidentally sharing "pretty".

### Other findings from this file
5/9 tests in PrinterTest.java returned "no candidates" — all five only
call a local helper method (assertRoundTrip) defined in the test class
itself, never touching src/main directly. Correct behavior given current
scope (only src/main methods count as candidates), but means the real
focal method is one level deeper than the tool currently looks.