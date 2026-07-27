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


## apollo, ReleaseControllerTest.java (2 tests)

**Commit:** 75f9950d5e1675dbb0617555c4502685ef4d4618
**Target flaky test:** com.ctrip.framework.apollo.adminservice.controller.ReleaseControllerTest#testReleaseBuild

| Test | Jaccard focal | LLM focal | Status |
|---|---|---|---|
| testMessageSendAfterBuildRelease | publish | publish | agreed |
| testReleaseBuild (target) | (none) | restTemplate.postForEntity | llm only |

**Result: 1/2 confirmed. Target test still not correctly resolved by either approach.**

testReleaseBuild is the same HTTP routing case found earlier with Jaccard,
but this time the LLM also got it wrong, just differently. It picked
restTemplate.postForEntity, the visible call in the test body, instead
of the real answer (publish in ReleaseController.java, confirmed earlier
by matching the @PostMapping URL). This shows the HTTP routing blind
spot isn't unique to Jaccard's word matching approach, it's a limitation
of reading the test file in isolation. Neither approach can trace an
HTTP request through Spring's routing to find the actual handler method
without also being given the controller's source code as context. Would
need a smarter prompt (e.g. also feeding the controller class to the
LLM) or a different technique entirely to catch this kind of test.

## liquibase, DropColumnGeneratorTest.java (1 test)

**Commit:** 31a22561423919b3875e0563a7bdcde3b9e457a9
**Target flaky test:** liquibase.sqlgenerator.core.DropColumnGeneratorTest#testDropMultipleColumnsMySQL

| Test | Jaccard focal | LLM focal | Status |
|---|---|---|---|
| testDropMultipleColumnsMySQL (target) | generateSql | generatorUnderTest.generateSql | agreed |

**Result: 1/1 confirmed.**

Both approaches landed on generateSql, matching what was manually
verified earlier. Worth noting the LLM completely avoided the token
collision problem that caused Jaccard to tie generateSql against toSql
(both scored equally due to sharing "sql" from "MySQL" in the test
name). The LLM read the actual method calls and correctly understood
generatorUnderTest.generateSql as the real call under test and
sql[0].toSql() as just operating on the result, so toSql was never
even considered a real candidate.

## karate, JsonUtilsTest.java (7 tests)

**Commit:** 14807dbf8d7c45f709299574222dd498b1fa5e67
**Target flaky test:** com.intuit.karate.JsonUtilsTest#testPojoConversion

| Test | Jaccard focal | LLM focal | Status |
|---|---|---|---|
| fromJsonStrictRetainsKeyOrder | fromJsonStrict | JsonUtils.fromJsonStrict | agreed |
| testBeanConversion | toJson | JsonUtils.toJson | agreed |
| testDeepCopy | deepCopy | JsonUtils.deepCopy | agreed |
| testParse | toStrictJson | JsonUtils.toStrictJson | agreed |
| testDetect | assertTrue | JsonUtils.isJson | disagreed |
| testMalformed | toString | JsonUtils.fromJsonStrict | disagreed |
| testPojoConversion (target) | asList | JsonUtils.toJson | disagreed |

**Result: 4/7 confirmed. Target test still not fully resolved by either approach.**

Checked the 3 disagreements against real source:

- testDetect: LLM correct (isJson), matches every assertion in the test. Jaccard picked assertTrue, a plain JUnit assertion method with no real testing logic behind it, should have been filtered out as a library call but wasn't.
- testMalformed: LLM correct (fromJsonStrict), the call inside the try/catch expecting failure. Jaccard picked toString, which comes from FileUtils.toString(...), just loading test data from a file, not the actual focal method.
- testPojoConversion (the target): this is the scenario named, multi-method test found earlier (real answer involves 3 methods: toJson, fromJson called twice, and toXml). The LLM picked toJson, genuinely one of the 3 correct answers, but only at 0.4 confidence, honestly reflecting the uncertainty rather than confidently committing. Jaccard picked asList, a plain JDK library call, clearly wrong. Neither approach fully captures that this test legitimately checks 3 separate methods in one round trip, but the LLM at least landed on a real one with appropriately low confidence, while Jaccard missed entirely.

## snakeyaml-engine, DumpToStringTest.java (1 test)

**Commit:** 9d2bca887ad1be7575bae2e427d074e2c49ff109
**Target flaky test:** org.snakeyaml.engine.issues.issue25.DumpToStringTest#dumpToStringTwice

| Test | Jaccard focal | LLM focal | Status |
|---|---|---|---|
| dumpToStringTwice (target) | dumpToString | dump.dumpToString | agreed |

**Result: 1/1 confirmed.**

Both approaches agreed on dumpToString, matching what was manually verified earlier (dump.dumpToString(data) is called twice in the test, once expecting failure and once expecting success). Clean confirmed result, nothing more to dig into here.