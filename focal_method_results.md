# Focal Method Finding Results

This uses Jaccard similarity (steps 4 & 6 of the UTFix based pipeline) to find the focal method (the actual method under test) for each flaky test. Devanshi's script (steps 1, 2, 3, 5) pulls out candidate methods via AST parsing, and my scorer picks the best match based on how many words overlap between the test name and each candidate.

---

## Summary

### ID tests (10/10 focal method found)

| Project | Flaky test | Focal method | Score | Note |
|---------|-----------|--------------|-------|------|
| edn-java | testPrettyPrinting | prettyPrinterProtocol | 0.20 | ❌ wrong, real answer is printString (stemming gap) |
| hop | testProvidesModelerMeta | getRowMeta | 0.17 | ✅ correct, main one of 3 methods tested |
| apollo | testReleaseBuild | (none) | — | 🔍 HTTP routing, real answer is publish |
| liquibase | testDropMultipleColumnsMySQL | generateSql | 0.14 | ⚠️ tied with toSql, correct after checking manually |
| karate | testPojoConversion | (tie, 0.0) | 0.00 | ⚠️ scenario named test, 3 real methods tested |
| snakeyaml engine | dumpToStringTwice | dumpToString | 0.75 | ✅ correct |
| common kafka | nextRecord_manyRecords | nextRecord | 0.50 | ✅ correct |
| hbase | testClone | clone | 0.50 | ✅ correct |
| asset share commons | pack | (tie, 0.0) | 0.00 | ⚠️ scenario named, real answer is execute |
| servicecomb java chassis | should_convert_unknown_client_exception... | convert | 0.14 | ✅ correct |

6 out of 10 were clean correct matches right away. The other 4 needed me to check manually (1 wrong pick, 3 ties or scenario named tests). Full breakdown for each is below.

### OD tests (10/10 focal method found)

| Project | Flaky test | Focal method | Score | Note |
|---------|-----------|--------------|-------|------|
| ormlite core | testDeleteThrow | delete | 0.33 | ✅ correct |
| ormlite core | testQueryRawDateTypesThrow | queryRaw | 0.33 | ✅ correct |
| ormlite core | testQueryForFirstPreparedThrow | queryForFirst | 0.50 | ✅ correct |
| ormlite core | testQueryRawColumnsNotQuery | query | 0.20 | ✅ correct |
| ormlite core | testStartThreadConnectionThrows | startThreadConnection | 0.60 | ✅ correct |
| ormlite core | testUpdateRawThrow | updateRaw | 0.50 | ✅ correct |
| ormlite core | testCloseLastIteratorThrow | closeLastIterator | 0.60 | ✅ correct |
| wikidata toolkit | createDirectoryManagerIoException | createDirectoryManager | 0.60 | ✅ correct |
| accumulo | testSetInstance_HdfsZooInstance_Implicit | (none) | — | 🔍 indirection, real call is hidden behind a private helper |
| wildfly | testJavaContext | (tie, 0.0) | 0.00 | ⚠️ scenario named, real answer is lookup |

8 out of 10 clean matches here. Only 2 needed manual digging (1 indirection miss, 1 zero overlap tie).

---

## ID flaky tests

### edn-java, testPrettyPrinting

**Commit:** 4cf29ffe2d063269cb09c9bf4f6fd5c1a3cb4e1b
**Flaky test:** us.bpsm.edn.printer.PrinterTest#testPrettyPrinting

**Pipeline result:** picked `prettyPrinterProtocol` (score 0.2)

**Manual check:** wrong. The real method under test is `printString`, confirmed by reading the source (Printers.printString(Printers.prettyPrinterProtocol(), list)).

**Why it got it wrong:** this is a tokenizer thing, not a logic bug. "testPrettyPrinting" splits into [pretty, printing, test], and "printString" splits into [print, string]. There's no stemming, so "printing" and "print" don't count as matching even though they're obviously the same root word. printString scored a flat 0.0 and lost to prettyPrinterProtocol, which only won because it happened to share the word "pretty."

**Other stuff I noticed in this file:** 5 out of 9 tests in PrinterTest.java came back with no candidates at all. Turns out all five only call a local helper method (assertRoundTrip) that's defined inside the test class itself, never touching src/main directly. That's actually correct behavior given the tool only looks at src/main methods, but it does mean the real focal method sits one level deeper than the tool currently checks.

### hop, testProvidesModelerMeta

**Commit:** be70e6fa1d4bf180c2766edc4c21d10fc215118b (note: this is different from the CSV's Zenodo zip filename hash, 96cfd6a. both commits exist in the repo's history, I used the flaky_commit column value since the test file was confirmed present there)
**Flaky test:** org.apache.hop.pipeline.transforms.databaselookup.DatabaseLookupMetaTest#testProvidesModelerMeta

**Pipeline result:** `getRowMeta` (score 0.167)

**Manual check:** correct as the main answer. meta.getRowMeta(...) gets checked directly with assertEquals first, and it shares the word "meta" with the test name ("ModelerMeta"). That said, this test also checks getDatabaseFields and getStreamFields right after, kind of similar to karate's testPojoConversion below, but getRowMeta is clearly the strongest single pick here since it's checked first and most directly.

**Also noticed:** 2 out of 5 tests in this file tied at 0.0 (testXmlRoundTrip, testInjection), likely the same scenario named pattern showing up again.

### apollo, testReleaseBuild

**Commit:** 75f9950d5e1675dbb0617555c4502685ef4d4618
**Flaky test:** com.ctrip.framework.apollo.adminservice.controller.ReleaseControllerTest#testReleaseBuild

**Pipeline result:** no candidates found

**Manual check:** the real focal method is `publish` in ReleaseController.java. Found it by matching the @PostMapping URL pattern, which lines up exactly with the URL the test hits via restTemplate.postForEntity(...).

**Why it missed it:** this is a totally different kind of limitation than edn-java's. This test is an integration test, meaning it calls the code under test through an actual HTTP request instead of a direct method call. Spring routes that request to the right controller method at runtime using the @PostMapping annotation, but there's no literal method invocation anywhere in the test's source code for the AST to grab onto. So there's genuinely nothing there to extract. This is a real structural blind spot for any Spring or REST style integration test, separate from the tokenizing issue in edn-java.

### liquibase, testDropMultipleColumnsMySQL

**Commit:** 31a22561423919b3875e0563a7bdcde3b9e457a9
**Flaky test:** liquibase.sqlgenerator.core.DropColumnGeneratorTest#testDropMultipleColumnsMySQL

**Pipeline result:** tied between `generateSql` and `toSql`, both at 0.143

**Manual check:** correct answer is `generateSql`. generatorUnderTest.generateSql(...) is the actual class under test being called, while sql[0].toSql() is called on the result object, not the generator itself.

**Why they tied:** token collision from a compound word. "MySQL" (the database vendor name) contains "sql" inside it, which happens to match both generateSql and toSql, causing a tie that has nothing to do with actual relevance. This is the third distinct failure type found so far (tokenizer stemming gap, HTTP routing blind spot, and now this token collision one).

### karate, testPojoConversion

**Commit:** 14807dbf8d7c45f709299574222dd498b1fa5e67
**Flaky test:** com.intuit.karate.JsonUtilsTest#testPojoConversion

**Pipeline result:** tied at 0.0 among asList, toJson, fromJson, getName, size, toXml

**Manual check:** there's no single correct answer here. This test genuinely exercises 3 real focal methods back to back: JsonUtils.toJson (object to JSON), JsonUtils.fromJson (JSON back to object, called twice), and XmlUtils.toXml (object to XML). asList, getName, and size are just JDK library calls used to build test data, not real candidates at all, worth checking why those weren't filtered out by the src/main project method check.

**Why it happened:** scenario named test (same category Devanshi found on her end). "PojoConversion" describes the general concept being tested, not any specific method name, so no candidate shares tokens with the test name and everything ties at 0.0. This one also shows that "one test equals one focal method" doesn't always hold true. Some tests legitimately check multiple methods in one round trip scenario.

### snakeyaml engine, dumpToStringTwice

**Commit:** 9d2bca887ad1be7575bae2e427d074e2c49ff109
**Flaky test:** org.snakeyaml.engine.issues.issue25.DumpToStringTest#dumpToStringTwice

**Pipeline result:** `dumpToString` (score 0.75)

**Manual check:** correct. Confirmed by the source, dump.dumpToString(data) gets called twice in the test (once inside a try/catch expecting it to fail, then again after, expecting it to succeed), matching exactly what the test name says.

**Notes:** clean, high confidence result. No failure mode here, one of the good ones.

### common kafka, nextRecord_manyRecords

**Commit:** d7873514c1705575c642ed99d2fa501f9b319790
**Flaky test:** com.cerner.common.kafka.consumer.ProcessingPartitionTest#nextRecord_manyRecords

**Pipeline result:** `nextRecord` (score 0.5)

**Manual check:** correct. partition.nextRecord() gets called 3 times throughout the test, matching "manyRecords" in the name. Clean and unambiguous.

**Notes:** the whole file (26 tests total) scored really well overall, 24 out of 26 were clean unambiguous matches, several even hit 1.0. Only 2 minor ties at the end (the getResetOffset tests, tied between getResetOffset and a genuinely related helper method like getEarliestOffset), which are honestly just close calls rather than an actual failure.

### hbase, testClone

**Commit:** 07a3ffdd97 (note: the CSV's flaky_commit column value, 6bb4b387a34..., doesn't exist anywhere in hbase's repo history. I searched every branch and found nothing. Used the short hash from the CSV's Zenodo zip filename instead, which resolved fine. Flagged this to Suzzana since it might be a data error affecting other rows too)
**Flaky test:** org.apache.hadoop.hbase.monitoring.TestTaskMonitor#testClone

**Pipeline result:** `clone` (score 0.5)

**Manual check:** correct. monitor.clone() is the exact call under test, everything that comes after it (getDescription, getState, getStatus, toString, toMap, toJSON) is just comparing the clone against the original, not additional focal methods.

**Notes:** whole file did reasonably well, 6 out of 8 tests got clean matches. 2 ties (testTaskMonitorBasics, testTaskLimit) both landed at 0.0, likely the same scenario named pattern as karate's testPojoConversion.

### asset share commons, pack

**Commit:** ee3ef7051e3ea3eb7f5d904fac177bc56623c6ed (note: different from the CSV's Zenodo zip filename hash, 79fcce8. Both exist in the repo history, I used the flaky_commit column since it's the more specific value and the test file was confirmed present there)
**Flaky test:** com.adobe.aem.commons.assetshare.content.renditions.download.impl.AssetRenditionsZipperImplTest#pack

**Pipeline result:** tied at 0.0 among getResource, execute, getContentType

**Manual check:** correct answer is `execute`. zipper.execute(...), called on AssetRenditionsZipperImpl (the actual class under test), is the real action being tested. getResource is just test setup fetching a mock resource, and getContentType is a post call assertion.

**Why it happened:** scenario named test, single word version. "pack" describes what the class conceptually does, not the specific method name ("execute"), so there's zero token overlap even though execute is clearly correct once you look at the class name and file structure. Same category as karate's testPojoConversion, but here the test name doesn't even hint that multiple methods might be involved, it's abstracted one level further.

**Notes:** rest of the file (8 out of 9 tests) scored well, several strong single word matches between 0.6 and 1.0.

### servicecomb java chassis, should_convert_unknown_client_exception_to_invocation_exception

**Commit:** 9ba66ebc452db6aa5207e5cc7ebd03d48d358e9f
**Flaky test:** org.apache.servicecomb.core.exception.ExceptionsTest#should_convert_unknown_client_exception_to_invocation_exception

**Pipeline result:** `convert` (score 0.143)

**Manual check:** correct. Exceptions.convert(null, exception, BAD_REQUEST) is the exact call under test, matching the test name directly. getStatus() afterward is just a post call assertion, not the focal method.

**Notes:** whole file scored well, 3 out of 4 tests correctly matched to convert. 1 tie (should_protect_when_converter_throw_exception) at 0.0, likely scenario named again since it describes a protective behavior rather than naming a method.

---

## OD flaky tests

### ormlite core, OD batch (7 tests, 1 shared polluter)

**Commit:** 632b87c2a455b8eab4a6c09324e1f166273588d8
**Module:** . (whole repo)
**Polluter (same for all 7):** com.j256.ormlite.logger.LoggerFactoryTest#testSetLogFactory

| Flaky test (victim) | Focal method | Score | Verified |
|---|---|---|---|
| RuntimeExceptionDaoTest#testDeleteThrow | delete | 0.333 | ✅ checked directly against source |
| RuntimeExceptionDaoTest#testQueryRawDateTypesThrow | queryRaw | 0.333 | ✅ correct by pattern |
| RuntimeExceptionDaoTest#testQueryForFirstPreparedThrow | queryForFirst | 0.5 | ✅ correct by pattern |
| QueryBuilderWithSchemaTest#testQueryRawColumnsNotQuery | query | 0.2 | ✅ checked directly against source |
| RuntimeExceptionDaoTest#testStartThreadConnectionThrows | startThreadConnection | 0.6 | ✅ correct by pattern |
| RuntimeExceptionDaoTest#testUpdateRawThrow | updateRaw | 0.5 | ✅ correct by pattern |
| RuntimeExceptionDaoTest#testCloseLastIteratorThrow | closeLastIterator | 0.6 | ✅ correct by pattern |

**Notes:** all 7 came back clean, no ties, no missing candidates. Genuinely the best batch I've had so far. RuntimeExceptionDaoTest is a thin wrapper class (RuntimeExceptionDao) that turns checked SQLExceptions into unchecked RuntimeExceptions, and every single test calls rtDao.methodName(...) where the method name matches the test name exactly. That's basically the ideal case for this whole Jaccard approach. I checked 2 out of 7 directly against the source (testDeleteThrow, testQueryRawColumnsNotQuery) and both were correct. The other 5 follow the exact same wrapper pattern so I'm treating them as high confidence based on consistency rather than checking each one individually.

**On the pipeline run itself:** I ran this on the whole test folder recursively instead of just the target files, since one clone covers all 7 of these tests. That ended up processing 1112 tests across 115 files total. Most of those are unrelated to this specific batch, but it was a good large scale sanity check on how the tool performs overall.

### wikidata toolkit, createDirectoryManagerIoException

**Commit:** 20de6f7f12319f54eb962ff6e8357b3f5695d54d
**Module:** wdtk-util
**Polluter:** DirectoryManagerFactoryTest#createDirectoryManagerNoConstructor
**Flaky test (victim):** org.wikidata.wdtk.util.DirectoryManagerFactoryTest#createDirectoryManagerIoException

**Pipeline result:** `createDirectoryManager` (score 0.6)

**Manual check:** correct. DirectoryManagerFactory.createDirectoryManager(...) is the exact call under test, clean direct match with no complications.

**Notes:** clean result, no failure mode here. Worth noting the polluter and the victim test both live in the same file and class this time, unlike the ormlite core batch where the polluter (LoggerFactoryTest) was in a completely separate class.

### accumulo, testSetInstance_HdfsZooInstance_Implicit

**Commit:** a573f96d434fb5ef3016b8f7d3d9904e4fd88d65
**Module:** core
**Polluter:** ShellSetInstanceTest#testSetInstance_HdfsZooInstance_InstanceGiven
**Flaky test (victim):** org.apache.accumulo.core.util.shell.ShellSetInstanceTest#testSetInstance_HdfsZooInstance_Implicit

**Pipeline result:** no candidates found

**Manual check:** the test calls testSetInstance_HdfsZooInstance(false, false, false), a private helper method defined inside the same test class, not in src/main. The helper itself does all the real testing work (setting up ShellOptionsJC expectations, etc.), but since it's not a project method, it gets filtered out. There's no true single focal method in src/main for this specific test, the closest equivalent would mean following the private helper's own body.

**Why it happened:** same indirection pattern I first ran into with edn-java's assertRoundTrip helper. All 6 of the "no candidates" results in this file follow this exact structure, each testSetInstance_ variant is just a thin wrapper calling one shared private helper with different boolean flags.

**Notes:** only testSetInstance_Fake in this file got a clean result (setInstance, 0.5) since it's the one test that doesn't go through the shared helper.

### wildfly, testJavaContext

**Commit:** b19048b72669fc0e96665b1b125dc1fda21f5993
**Module:** naming
**Polluter:** WritableServiceBasedNamingStoreTestCase#testPermissions
**Flaky test (victim):** org.jboss.as.naming.InitialContextFactoryTestCase#testJavaContext

**Pipeline result:** tied at 0.0 between getName and lookup

**Manual check:** correct answer is `lookup`. initialContext.lookup("java:") is the real call under test, checking that the "java:" namespace resolves properly. getName (InitialContextFactory.class.getName()) is just setup, used to set a system property, not the thing actually being tested.

**Why it happened:** scenario named test with zero token overlap on either candidate. "testJavaContext" doesn't share a single word with "lookup" or "getName", so both landed at 0.0 by pure coincidence rather than genuine ambiguity. This is a case where the tokenizer really has nothing at all to work with, different from the karate or asset share commons ties, which at least shared partial words.

---

## Reproducing this

Two steps per test file:

```
python3 focal_extract.py <TestFile.java> > candidates.json    # steps 1, 2, 3, 5
python3 focal_method_finder_batch.py candidates.json out.json  # steps 4, 6
```

Or for a whole folder at once:

```
python3 run_pipeline.py <folder_path> out.json
```

focal_extract.py finds the project's src/main by walking up from the test file, parses everything under it, and only keeps candidates that are actually defined in the project. If a file won't parse or has no annotated tests, it returns an empty list and logs why, so a batch run doesn't die on one bad file.
