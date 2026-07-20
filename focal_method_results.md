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