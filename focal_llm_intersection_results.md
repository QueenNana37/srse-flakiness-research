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

## common-kafka, ProcessingPartitionTest.java (26 tests)

**Commit:** d7873514c1705575c642ed99d2fa501f9b319790
**Target flaky test:** com.cerner.common.kafka.consumer.ProcessingPartitionTest#nextRecord_manyRecords

**Result: 22/26 confirmed, including the target test (nextRecord_manyRecords).**

4 disagreements, checked each against real source:

- commitableOffsets: LLM picked getCommittableOffset (called 3 times in the test), Jaccard picked getCommittableOffsetsSize (called once). Both methods genuinely appear and get exercised, another case of a test legitimately checking multiple related methods rather than one clean answer.
- pause_moreRecordsLoaded: LLM's pick (partition.maybeUnpause) is the more central one, directly described in a code comment ("Un-pause the partition"). Jaccard's pick (getFailPauseTime) is just a helper call used to compute an argument value, not the real action being tested.
- pause_thenClosePartition: genuinely interesting one. The test body literally calls pause_thresholdMet(), which is a different @Test method in the same file being reused as shared setup. The LLM picked up on that literal call and named it as the focal method, but that's not meaningful since it's not a src/main method, just chained test setup. Jaccard's pick (close) is the better answer here, since partition.close() is the real new behavior being verified once the shared setup finishes.
- pause_thresholdMet: LLM's pick (partition.fail) is the more central one, the repeated fail() calls are what actually trigger the pausing behavior the test name describes. Jaccard's pick (getFailPauseTime) is a minor helper used only to compute an assertion bound.

Worth noting a new pattern found here: tests that call other @Test methods as shared setup helpers (pause_thenClosePartition calling pause_thresholdMet). Neither approach handles this cleanly, since a test method isn't a valid focal method candidate at all, but nothing currently filters that case out.

## hbase, TestTaskMonitor.java (8 tests)

**Commit:** 07a3ffdd97
**Target flaky test:** org.apache.hadoop.hbase.monitoring.TestTaskMonitor#testClone

**Result: 4/8 confirmed, including the target test (testClone).**

4 disagreements, checked each against real source. This file is a good contrast to earlier ones, Jaccard actually did better than the LLM here on 3 out of 4.

- testStatusJournal: Jaccard correct (getStatusJournal, checked repeatedly to verify journal entries). LLM picked setStatus, which is just the trigger action, not what's actually being verified.
- testTaskMonitorBasics: scenario named, multi-method test (getTasks called twice and checked, alongside markComplete and getState). Jaccard's pick (getTasks) is still the more central answer despite scoring 0.0, another stemming gap since "tasks" plural in the method doesn't match "task" singular in the test name. LLM picked createStatus, which is just setup, not the real focus of the test.
- testWarnStuckTasks: Jaccard correct (getWarnTime, checked 3 times to verify timing behavior). LLM picked setRPC, the one setup call that triggers the state being measured, not the thing actually being asserted on repeatedly.

Worth noting: in this file the LLM tended to latch onto the first setup or state changing call in the test rather than the method being repeatedly checked afterward, opposite of the pattern seen in edn-java where the LLM outperformed Jaccard by avoiding setup calls. Neither approach is consistently better, it depends on the shape of the individual test.

## asset-share-commons, AssetRenditionsZipperImplTest.java (9 tests)

**Commit:** ee3ef7051e3ea3eb7f5d904fac177bc56623c6ed
**Target flaky test:** com.adobe.aem.commons.assetshare.content.renditions.download.impl.AssetRenditionsZipperImplTest#pack

**Result: 8/9 confirmed. The one disagreement is the target test itself.**

pack: Jaccard picked getResource, LLM picked execute. Already manually verified earlier, execute is correct, zipper.execute(...) called on AssetRenditionsZipperImpl (the class under test) is the real action being tested, getResource is just test setup fetching a mock resource. The LLM correctly avoided the same scenario named trap that caught Jaccard here, "pack" describes what the class conceptually does rather than naming the specific method, so there was zero token overlap for Jaccard to work with, but the LLM read the actual body and picked the right one anyway.

Rest of the file (8/9) was a clean sweep, both approaches agreeing on every single-word method match.

## servicecomb-java-chassis, ExceptionsTest.java (4 tests)

**Commit:** 9ba66ebc452db6aa5207e5cc7ebd03d48d358e9f
**Target flaky test:** org.apache.servicecomb.core.exception.ExceptionsTest#should_convert_unknown_client_exception_to_invocation_exception

**Result: 3/4 confirmed, including the target test.**

should_protect_when_converter_throw_exception: LLM correct (processor.convert), the real call under test, whose result and resulting log message are what get asserted. Jaccard picked setConverters, which is just setup, configuring the processor with a converter designed to throw. Another likely stemming/pluralization mismatch behind the wrong pick (converter vs converters), similar to earlier cases.

This wraps up all 10 of the ID flaky tests for the LLM plus intersection step.