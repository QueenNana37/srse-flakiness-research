# Focal Method Finding Results

Using Jaccard similarity (steps 4 & 6 of the UTFix-based pipeline) to
identify the focal method (method under test) for each flaky test.
Devanshi's script (steps 1, 2, 3, 5) extracts candidate methods via
AST parsing; this scorer picks the best match by token overlap.

---

## Summary

### ID tests (10/10 focal method found)
| Project | Flaky test | Focal method | Score | Note |
|---------|-----------|--------------|-------|------|
| edn-java | testPrettyPrinting | prettyPrinterProtocol | 0.20 | wrong, real answer is printString (stemming gap) |
| hop | testProvidesModelerMeta | getRowMeta | 0.17 | correct, primary of 3 methods tested |
| apollo | testReleaseBuild | (none) | — | HTTP routing, real answer is publish |
| liquibase | testDropMultipleColumnsMySQL | generateSql | 0.14 | tie w/ toSql, correct after manual check |
| karate | testPojoConversion | (tie, 0.0) | 0.00 | scenario-named, 3 real methods tested |
| snakeyaml-engine | dumpToStringTwice | dumpToString | 0.75 | correct |
| common-kafka | nextRecord_manyRecords | nextRecord | 0.50 | correct |
| hbase | testClone | clone | 0.50 | correct |
| asset-share-commons | pack | (tie, 0.0) | 0.00 | scenario-named, real answer is execute |
| servicecomb-java-chassis | should_convert_unknown_client_exception... | convert | 0.14 | correct |

6/10 clean correct matches, 4/10 needed manual verification (1 wrong pick,
3 ties/scenario-named). Full root-cause breakdown for each below.

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

## hop — testProvidesModelerMeta (ID-flaky)

**Commit:** be70e6fa1d4bf180c2766edc4c21d10fc215118b (NOTE: differs from
CSV's Zenodo zip filename hash 96cfd6a — both exist in repo history,
used flaky_commit column, test file confirmed present there)
**Flaky test:** org.apache.hop.pipeline.transforms.databaselookup.DatabaseLookupMetaTest#testProvidesModelerMeta

### Pipeline result
Focal method: `getRowMeta` (score=0.167)

### Manual verification
Correct as primary answer. meta.getRowMeta(...) is directly checked
with assertEquals first, and shares the "meta" token with the test
name ("ModelerMeta"). However, this test also verifies getDatabaseFields
and getStreamFields afterward — similar multi-method scenario as
karate's testPojoConversion, though getRowMeta is clearly the strongest
single answer here given it's checked first and most directly.

### Notes
2/5 tests in this file tied at 0.0 (testXmlRoundTrip, testInjection) —
likely scenario-named tests, same recurring pattern.


## apollo — testReleaseBuild (ID-flaky)

**Commit:** 75f9950d5e1675dbb0617555c4502685ef4d4618
**Flaky test:** com.ctrip.framework.apollo.adminservice.controller.ReleaseControllerTest#testReleaseBuild

### Pipeline result
No candidates found.

### Manual verification
Confirmed the actual focal method is `publish` in ReleaseController.java —
matched by the @PostMapping URL pattern, which exactly matches the URL
the test hits via restTemplate.postForEntity(...).

### Root cause
Different limitation than edn-java's. This test is an integration test —
it calls the code under test via an HTTP request (restTemplate.postForEntity)
rather than a direct method call. Spring routes the HTTP request to the
correct controller method at runtime via annotations (@PostMapping), not
via a literal method invocation visible in the test's source code. Since
the tool only extracts direct method calls from the AST, it has no way to
see this connection — there's genuinely nothing to extract.

This is a structural blind spot for any Spring/REST-style integration test,
distinct from the tokenizing issue found in edn-java.

## liquibase — testDropMultipleColumnsMySQL (ID-flaky)

**Commit:** 31a22561423919b3875e0563a7bdcde3b9e457a9
**Flaky test:** liquibase.sqlgenerator.core.DropColumnGeneratorTest#testDropMultipleColumnsMySQL

### Pipeline result
Ambiguous tie: `generateSql` and `toSql`, both scoring 0.143.

### Manual verification
Correct answer is `generateSql`. `generatorUnderTest.generateSql(...)` is
the actual class-under-test call; `sql[0].toSql()` is called on the
*result* object, not the generator being tested.

### Root cause
Token collision from a compound word. "MySQL" (database vendor name)
contains "sql," which coincidentally matches both generateSql and toSql,
causing a tie unrelated to actual semantic relevance. Third distinct
failure mode found so far (tokenizer stemming gap, HTTP routing blind
spot, now token-collision from compound names).


## karate — testPojoConversion (ID-flaky)

**Commit:** 14807dbf8d7c45f709299574222dd498b1fa5e67
**Flaky test:** com.intuit.karate.JsonUtilsTest#testPojoConversion

### Pipeline result
Ambiguous tie at 0.0 among asList, toJson, fromJson, getName, size, toXml.

### Manual verification
No single correct answer — this test genuinely exercises 3 real focal
methods in sequence: JsonUtils.toJson (object->JSON), JsonUtils.fromJson
(JSON->object, called twice), and XmlUtils.toXml (object->XML). asList,
getName, and size are JDK library calls used only to build test data,
not real candidates — worth checking why they weren't filtered out by
the src/main project-method check.

### Root cause
Scenario-named test (same category Devanshi found). "PojoConversion"
describes the concept under test, not any single method name, so no
candidate shares tokens with the test name — hence the 0.0 tie across
the board. This test also highlights that "one test = one focal method"
doesn't always hold; some tests legitimately verify multiple methods
in one round-trip scenario.

## snakeyaml-engine — dumpToStringTwice (ID-flaky)

**Commit:** 9d2bca887ad1be7575bae2e427d074e2c49ff109
**Flaky test:** org.snakeyaml.engine.issues.issue25.DumpToStringTest#dumpToStringTwice

### Pipeline result
Focal method: `dumpToString` (score=0.75)

### Manual verification
Correct. Confirmed by source — dump.dumpToString(data) is called twice
in the test (once inside a try/catch expecting failure, once after,
expecting success), which is exactly what the test name describes.

### Notes
Clean, high-confidence result — no failure mode found here.

## common-kafka — nextRecord_manyRecords (ID-flaky)

**Commit:** d7873514c1705575c642ed99d2fa501f9b319790
**Flaky test:** com.cerner.common.kafka.consumer.ProcessingPartitionTest#nextRecord_manyRecords

### Pipeline result
Focal method: `nextRecord` (score=0.5)

### Manual verification
Correct. partition.nextRecord() is called 3 times throughout the test,
matching "manyRecords" in the test name. Clean, unambiguous result.

### Notes
Whole test file (26 tests) scored very well overall — 24/26 clean
unambiguous matches, several at 1.0. Only 2 minor ties at the end
(getResetOffset tests, tied between getResetOffset and a legitimately
related helper method like getEarliestOffset) — genuinely close calls,
not a real failure mode.

## hbase — testClone (ID-flaky)

**Commit:** 07a3ffdd97 (NOTE: CSV's flaky_commit column, 6bb4b387a34..., 
does not exist anywhere in hbase's repo history — searched all branches,
no match. Used the short hash from the CSV's Zenodo zip filename instead,
which resolved correctly. Flagged to Suzzana, possible data error affecting
other rows too.)
**Flaky test:** org.apache.hadoop.hbase.monitoring.TestTaskMonitor#testClone

### Pipeline result
Focal method: `clone` (score=0.5)

### Manual verification
Correct. monitor.clone() is the exact call under test; everything after
(getDescription, getState, getStatus, toString, toMap, toJSON) are
comparison assertions checking the clone matches the original, not
additional focal methods.

### Notes
Whole file scored reasonably well — 6/8 tests got clean matches. 2 ties
(testTaskMonitorBasics, testTaskLimit) both landed at 0.0, likely
scenario-named tests (same category as karate's testPojoConversion).

## asset-share-commons — pack (ID-flaky)

**Commit:** ee3ef7051e3ea3eb7f5d904fac177bc56623c6ed (NOTE: differs from
CSV's Zenodo zip filename hash 79fcce8 — both exist in repo history,
used flaky_commit column since it's the more specific/intended value
and the test file confirmed present there)
**Flaky test:** com.adobe.aem.commons.assetshare.content.renditions.download.impl.AssetRenditionsZipperImplTest#pack

### Pipeline result
Ambiguous tie at 0.0 among getResource, execute, getContentType.

### Manual verification
Correct answer is `execute` — zipper.execute(...) called on
AssetRenditionsZipperImpl (the class under test) is the real action
being tested. getResource is test setup (fetching a mock resource),
getContentType is a post-call assertion.

### Root cause
Scenario-named test, single-word variant. "pack" describes the class's
conceptual purpose, not the specific method name ("execute"), so zero
token overlap despite execute being unambiguously correct given the
class name and file structure. Same category as karate's
testPojoConversion, but here the test name doesn't even hint at
multiple methods — it's abstracted one level further.

### Notes
Rest of file (8/9 tests) scored well, several strong single-word
matches at 0.6-1.0.

## servicecomb-java-chassis — should_convert_unknown_client_exception_to_invocation_exception (ID-flaky)

**Commit:** 9ba66ebc452db6aa5207e5cc7ebd03d48d358e9f
**Flaky test:** org.apache.servicecomb.core.exception.ExceptionsTest#should_convert_unknown_client_exception_to_invocation_exception

### Pipeline result
Focal method: `convert` (score=0.143)

### Manual verification
Correct. Exceptions.convert(null, exception, BAD_REQUEST) is the exact
call under test — matches the test name directly. getStatus() is a
post-call assertion, not the focal method.

### Notes
Whole file scored well — 3/4 tests correctly matched to `convert`.
1 tie (should_protect_when_converter_throw_exception) at 0.0, likely
scenario-named (describes a protective behavior, not a method call).

## ormlite-core — OD-flaky batch (7 tests, 1 polluter)

**Commit:** 632b87c2a455b8eab4a6c09324e1f166273588d8
**Module:** . (whole repo)
**Polluter (shared across all 7):** com.j256.ormlite.logger.LoggerFactoryTest#testSetLogFactory

| Flaky test (victim) | Focal method | Score | Verified |
|---|---|---|---|
| RuntimeExceptionDaoTest#testDeleteThrow | delete | 0.333 | ✓ correct (spot-checked) |
| RuntimeExceptionDaoTest#testQueryRawDateTypesThrow | queryRaw | 0.333 | ✓ correct (pattern match) |
| RuntimeExceptionDaoTest#testQueryForFirstPreparedThrow | queryForFirst | 0.5 | ✓ correct (pattern match) |
| QueryBuilderWithSchemaTest#testQueryRawColumnsNotQuery | query | 0.2 | ✓ correct (spot-checked) |
| RuntimeExceptionDaoTest#testStartThreadConnectionThrows | startThreadConnection | 0.6 | ✓ correct (pattern match) |
| RuntimeExceptionDaoTest#testUpdateRawThrow | updateRaw | 0.5 | ✓ correct (pattern match) |
| RuntimeExceptionDaoTest#testCloseLastIteratorThrow | closeLastIterator | 0.6 | ✓ correct (pattern match) |

### Notes
All 7 came back clean with no ties or missing candidates — genuinely
the best batch so far. RuntimeExceptionDaoTest is a thin wrapper class
(RuntimeExceptionDao) that converts checked SQLExceptions to unchecked
RuntimeExceptions; every test calls rtDao.<methodName>(...) with the
method name matching the test name exactly, which is exactly the ideal
case for this Jaccard-based approach. Spot-checked 2/7 directly against
source (testDeleteThrow, testQueryRawColumnsNotQuery), both confirmed
correct; the remaining 5 follow the identical wrapper pattern so treated
as high-confidence by consistency rather than individually re-verified.

### Note on pipeline run
Ran the pipeline on the whole test folder recursively (not just target
files) since one clone covers all 7 of these tests — picked up 1112
tests across 115 files total, most irrelevant to this batch but useful
as a large-scale sanity check on the tool's overall hit rate (see
separate note on aggregate stats below, if tracked).

## wikidata-toolkit — createDirectoryManagerIoException (OD-flaky)

**Commit:** 20de6f7f12319f54eb962ff6e8357b3f5695d54d
**Module:** wdtk-util
**Polluter:** DirectoryManagerFactoryTest#createDirectoryManagerNoConstructor
**Flaky test (victim):** org.wikidata.wdtk.util.DirectoryManagerFactoryTest#createDirectoryManagerIoException

### Pipeline result
Focal method: `createDirectoryManager` (score=0.6)

### Manual verification
Correct. DirectoryManagerFactory.createDirectoryManager(...) is the
exact call under test — clean direct match, no complications.

### Notes
Clean result, no failure mode found. Note: polluter and victim test
are both in the same file/class, unlike the ormlite-core batch where
the polluter lived in a completely separate class (LoggerFactoryTest).

## accumulo — testSetInstance_HdfsZooInstance_Implicit (OD-flaky)

**Commit:** a573f96d434fb5ef3016b8f7d3d9904e4fd88d65
**Module:** core
**Polluter:** ShellSetInstanceTest#testSetInstance_HdfsZooInstance_InstanceGiven
**Flaky test (victim):** org.apache.accumulo.core.util.shell.ShellSetInstanceTest#testSetInstance_HdfsZooInstance_Implicit

### Pipeline result
No candidates found.

### Manual verification
Test calls testSetInstance_HdfsZooInstance(false, false, false) — a
private helper method defined inside the same test class, not in
src/main. The helper itself does the real mocking/testing work
(ShellOptionsJC expectations, etc.), but since it's not a project
method, it gets filtered out. No true single focal method exists in
src/main for this specific test — the closest equivalent would require
following the private helper's own body.

### Root cause
Same indirection pattern first found in edn-java (assertRoundTrip
helper). All 6 of the "no candidates" results in this file follow this
same structure — each testSetInstance_* variant is a thin wrapper
calling one shared private helper with different boolean flags.

### Notes
Only testSetInstance_Fake in this file got a clean result (setInstance,
0.5) since it doesn't use the shared helper pattern.

## wildfly — testJavaContext (OD-flaky)

**Commit:** b19048b72669fc0e96665b1b125dc1fda21f5993
**Module:** naming
**Polluter:** WritableServiceBasedNamingStoreTestCase#testPermissions
**Flaky test (victim):** org.jboss.as.naming.InitialContextFactoryTestCase#testJavaContext

### Pipeline result
Ambiguous tie at 0.0 between getName and lookup.

### Manual verification
Correct answer is `lookup`. initialContext.lookup("java:") is the real
call under test — verifying the "java:" namespace resolves correctly.
getName (InitialContextFactory.class.getName()) is just setup, used to
set a system property, not the thing being tested.

### Root cause
Scenario-named test with zero token overlap on either candidate.
"testJavaContext" shares no words with "lookup" or "getName" — both
tied at 0.0 by coincidence rather than genuine ambiguity. A case where
the tokenizer has literally nothing to work with, distinct from the
karate/asset-share-commons ties which at least shared partial words.