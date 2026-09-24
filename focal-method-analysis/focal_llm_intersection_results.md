## Overall Summary (20 tests)

| Project | Target flaky test | Jaccard focal | LLM focal | Status | Manual verdict |
|---|---|---|---|---|---|
| edn-java | testPrettyPrinting | prettyPrinterProtocol | Printers.printString | disagreed | ✅ LLM correct |
| hop | testProvidesModelerMeta | getRowMeta | meta.getRowMeta | agreed | ✅ confirmed |
| apollo | testReleaseBuild | (none) | restTemplate.postForEntity | llm only | ❌ neither correct |
| liquibase | testDropMultipleColumnsMySQL | generateSql | generatorUnderTest.generateSql | agreed | ✅ confirmed |
| karate | testPojoConversion | asList | JsonUtils.toJson | disagreed | ⚠️ llm partially correct (1 of 3 real methods) |
| snakeyaml-engine | dumpToStringTwice | dumpToString | dump.dumpToString | agreed | ✅ confirmed |
| common-kafka | nextRecord_manyRecords | nextRecord | partition.nextRecord | agreed | ✅ confirmed |
| hbase | testClone | clone | clone | agreed | ✅ confirmed |
| asset-share-commons | pack | getResource | execute | disagreed | ✅ LLM correct |
| servicecomb-java-chassis | should_convert_unknown_client_exception... | convert | Exceptions.convert | agreed | ✅ confirmed |
| ormlite-core | testDeleteThrow | delete | delete | agreed | ✅ confirmed |
| ormlite-core | testQueryRawDateTypesThrow | queryRaw | queryRaw | agreed | ✅ confirmed |
| ormlite-core | testQueryForFirstPreparedThrow | queryForFirst | queryForFirst | agreed | ✅ confirmed |
| ormlite-core | testQueryRawColumnsNotQuery | query | dao.query | agreed | ✅ confirmed |
| ormlite-core | testStartThreadConnectionThrows | startThreadConnection | rtDao.startThreadConnection | agreed | ✅ confirmed |
| ormlite-core | testUpdateRawThrow | updateRaw | updateRaw | agreed | ✅ confirmed |
| ormlite-core | testCloseLastIteratorThrow | closeLastIterator | closeLastIterator | agreed | ✅ confirmed |
| wikidata-toolkit | createDirectoryManagerIoException | createDirectoryManager | DirectoryManagerFactory.createDirectoryManager | agreed | ✅ confirmed |
| accumulo | testSetInstance_HdfsZooInstance_Implicit | (none) | testSetInstance_HdfsZooInstance (local helper) | llm only | ✅ LLM correct |
| wildfly | testJavaContext | getName | lookup | disagreed | ✅ LLM correct |

**14/20 confirmed (both agreed). Of the remaining 6: 4 were correct via the LLM alone (Jaccard had a structural blind spot), 1 was partial credit (genuine multi-method test), 1 was a true miss for both approaches (HTTP routing, would need extra context fed to the LLM to catch).**


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

## hop, DatabaseLookupMetaTest.java (5 tests)

**Commit:** be70e6fa1d4bf180c2766edc4c21d10fc215118b
**Target flaky test:** org.apache.hop.pipeline.transforms.databaselookup.DatabaseLookupMetaTest#testProvidesModelerMeta

**Result: 2/5 confirmed, including the target test (testProvidesModelerMeta).**

3 disagreements, LLM correct on all 3 after checking source:

- getFieldWithValueUsedTwice: LLM correct (databaseLookupMeta.getFields), the real call checked right after with assertions on the resulting row. Jaccard picked get, too generic and only matched by coincidence.
- testInjection: LLM correct (injector.setProperty), called 8 times throughout the test, each followed by an assertion checking the injected value landed correctly. Jaccard picked build, likely from RowMetaBuilder().build(), which is just setup for test data.
- testXmlRoundTrip: LLM correct (XmlMetadataUtil.deSerializeFromXml), the actual method being tested. Jaccard picked get again, same generic mismatch as above.

This wraps up all 10 ID flaky tests for the LLM plus intersection step.

## ormlite-core, RuntimeExceptionDaoTest.java (81 tests, 6 are OD targets)

**Commit:** 632b87c2a455b8eab4a6c09324e1f166273588d8
**Target flaky tests:** testDeleteThrow, testQueryRawDateTypesThrow, testQueryForFirstPreparedThrow, testStartThreadConnectionThrows, testUpdateRawThrow, testCloseLastIteratorThrow (testQueryRawColumnsNotQuery, the 7th OD target, lives in QueryBuilderWithSchemaTest.java instead)

**Result: 76/81 confirmed, all 6 target OD tests from this file confirmed clean.**

Note: originally ran this intersection against the full 1112 test Jaccard file from the big recursive pipeline run, which produced a meaningless 76/981 comparison since the LLM only ran on this one file. Filtered the Jaccard results down to just RuntimeExceptionDaoTest.java's 81 tests first, then re-ran the intersection properly.

5 issues found, checked against source:

- testCoverage, testCoverage2, testCoverage3: these are deliberately broad tests exercising many wrapper methods for coverage purposes, not testing one single method. LLM picked create (the first substantial DAO action after setup), Jaccard picked createDao (just the setup call that builds the underlying real DAO). Neither is fully wrong since these tests intentionally touch dozens of methods, there isn't really one correct single focal method here.
- testDeletes: similarly multi-method, matching the plural in the name, both deleteById and delete(collection) get tested. LLM's pick (dao.deleteById) is a genuine one of the two real answers. Jaccard's pick (createDao) is just setup, clearly wrong.
- testIfAllMethodsAreThere: a structural, reflection based test. It checks that RuntimeExceptionDao implements every method from Dao, CloseableIterable, and Iterable by comparing method lists via reflection (getDeclaredMethods()). There's no real business logic focal method here at all. Jaccard picked addAll, which turned out to be a plain JDK List.addAll call, not defined anywhere in the project, meaning it leaked past the src/main only candidate filter. Worth flagging to Devanshi as a possible bug in focal_extract.py's filtering. The LLM correctly returned no candidates for this one, which is actually the more honest answer, since this test doesn't exercise any single method under test in the usual sense.

## ormlite-core, QueryBuilderWithSchemaTest.java (4 tests, 1 is the 7th OD target)

**Commit:** 632b87c2a455b8eab4a6c09324e1f166273588d8
**Target flaky test:** com.j256.ormlite.stmt.QueryBuilderWithSchemaTest#testQueryRawColumnsNotQuery

**Result: 1/4 confirmed, target test confirmed clean (query).**

3 disagreements, LLM correct on all 3 after checking source:

- testAlias: ends with assertEquals(sb.toString(), qb.prepareStatementString()), so prepareStatementString is the real assertion target. LLM correct. Jaccard picked setAlias, which is just one configuration call feeding into the final generated string, not the thing directly verified.
- testClear: qb.reset() is the action matching "Clear" in the name, its effect then verified through prepareStatementString(). LLM correct (qb.reset). Jaccard picked createDao, just setup, clearly wrong.
- testSelectAll: same pattern, prepareStatementString() is what gets asserted against a manually built expected string. LLM correct. Jaccard picked appendEscapedEntityName, a helper call used to build the comparison string, not the actual method under test.

This completes all 7 ormlite-core OD targets across both files.

## wikidata-toolkit, DirectoryManagerFactoryTest.java (4 tests)

**Commit:** 20de6f7f12319f54eb962ff6e8357b3f5695d54d
**Target flaky test:** org.wikidata.wdtk.util.DirectoryManagerFactoryTest#createDirectoryManagerIoException

**Result: 4/4 confirmed, including the target test.**

Clean sweep, both approaches agreed on createDirectoryManager for every single test in this file. Nothing to dig into here, straightforward result.

## accumulo, ShellSetInstanceTest.java (7 tests)

**Commit:** a573f96d434fb5ef3016b8f7d3d9904e4fd88d65
**Target flaky test:** org.apache.accumulo.core.util.shell.ShellSetInstanceTest#testSetInstance_HdfsZooInstance_Implicit

**Result: 1/7 confirmed (agreed). 6/7 llm only, matching the same indirection pattern found earlier.**

Same story as edn-java's assertRoundTrip case. The LLM correctly identified that all 6 testSetInstance_* variants call one of two shared private helper methods (testSetInstance_HdfsZooInstance or testSetInstance_ZKInstance), both defined inside the test class itself, not src/main. Jaccard's filter correctly excludes these by design, since they're not project methods, so it comes back with nothing for any of them. The LLM has no such restriction and just reports what's literally called in the body.

Worth noting for the methodology itself: under the strict "confirmed only when both agree" rule, none of these 6 count as confirmed, even though the LLM's answer is correct and matches manual verification. That's a real limitation of the intersection approach as currently defined, a correct LLM answer gets zero credit whenever Jaccard has a structural blind spot rather than a wrong guess, since there's nothing for it to agree with.

## wildfly, InitialContextFactoryTestCase.java (2 tests)

**Commit:** b19048b72669fc0e96665b1b125dc1fda21f5993
**Target flaky test:** org.jboss.as.naming.InitialContextFactoryTestCase#testJavaContext

**Result: 0/2 confirmed, but the LLM is correct on both after manual verification.**

testJavaContext: LLM correct (lookup), exactly matching what was manually verified earlier. initialContext.lookup("java:") is the real call under test, getName (InitialContextFactory.class.getName()) is just setup used to configure a system property, not the thing being tested. Jaccard's tie between getName and lookup (both scoring 0.0 due to zero token overlap with the test name) is fully resolved by the LLM, which reads the body semantically instead of relying on shared words.

testInitialFactory: same pattern, LLM picked InitialContext.lookup, consistent with the other test in this file.

This is the last of the 20 original tests for the LLM plus intersection step. Overall, the LLM was especially good at resolving cases where Jaccard's tokenizer had zero signal to work with (scenario named tests, zero overlap ties), since it reads the test body's actual logic instead of comparing word lists.