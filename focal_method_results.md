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