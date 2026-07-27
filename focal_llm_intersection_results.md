# Focal Method: LLM + Jaccard Intersection Results

Running both approaches from the UTFix paper on the same tests: Jaccard similarity (already built, word overlap based) and an LLM based approach (feeds the test body to GPT, asks it directly which method is under test). A focal method only counts as "confirmed" when both approaches agree on the exact same method.

Scripts used: `llm_focal.py` (runs the LLM approach) and `intersect_focal.py` (compares Jaccard output against LLM output and marks agreement).

---

## edn-java, PrinterTest.java (9 tests)

**Commit:** 4cf29ffe2d063269cb09c9bf4f6fd5c1a3cb4e1b
**Target flaky test:** us.bpsm.edn.printer.PrinterTest#testPrettyPrinting

| Test | Jaccard focal | LLM focal | Status |
|---|---|---|---|
| testSingleValues | (none) | assertRoundTrip | llm only |
| testRoundTripCommaCharacterLiteralIssue45 | (none) | assertRoundTrip | llm only |
| testSymbolAsMapKeyWithSetAsValue | (none) | assertRoundTrip | llm only |
| testTaggedSymbol | (none) | assertRoundTrip | llm only |
| testComplexValue | (none) | assertRoundTrip | llm only |
| testDefaultPrinter | newPrinter | p.printValue | disagreed |
| issue31 | newPrinter | Printers.printString | disagreed |
| testPrettyPrinting (target) | prettyPrinterProtocol | Printers.printString | disagreed |
| testLoosePrinter | newLoosePrinter | p.printValue | disagreed |

**Result: 0/9 confirmed (agreed), but the LLM was actually correct on all 9 after manual verification.**

This one's worth digging into properly rather than just reading the confirmed count at face value. I checked every disagreement against the real source:

- **testDefaultPrinter, issue31, testLoosePrinter**: in all three, Jaccard picked the constructor or setup method (newPrinter, newLoosePrinter), while the LLM correctly picked the actual method being exercised and asserted on (p.printValue or Printers.printString). Confirmed by reading the source, the setup calls just build an object, the picked LLM methods are what the assertions actually check.
- **testPrettyPrinting**: same story, already found this one earlier. printString is the real method, prettyPrinterProtocol only won on Jaccard by coincidence (shared the word "pretty").
- **The 5 assertRoundTrip cases**: these are "llm only" rather than "disagreed" because Jaccard filters out assertRoundTrip entirely, since it's a private helper method inside the test class, not something defined in src/main. So Jaccard doesn't even offer a candidate here, it's not that it disagreed, it just has nothing to say. The LLM doesn't apply that same filter, it reads the test body and answers based on what's actually called, regardless of where that method lives.

**Why Jaccard lost across the whole file:** there's one consistent root cause behind almost every miss here. newPrinter and newLoosePrinter both share the word "printer" with the test class name, so Jaccard's word overlap scoring favors them. Meanwhile printValue only shares the word "print", which doesn't match "printer" as a token since there's no stemming (this is the same tokenizer limitation found earlier on testPrettyPrinting, just showing up again in a different form across the rest of the file). The LLM doesn't have this blind spot since it reads the full method body semantically instead of just comparing word lists, so it picks the real action method every time instead of getting distracted by a setup call that happens to share a partial word with the class name.

