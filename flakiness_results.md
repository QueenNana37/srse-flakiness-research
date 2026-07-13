# Flakiness of AI-Generated Java Tests — Results Log

**Question:** When ChatUniTest (gpt-4o-mini) generates unit tests for a Java class, are the generated tests themselves flaky?  
**Detectors:** NonDex → implementation-dependent (ID) · iDFlakies → order-dependent (OD) · 100x loop → non-deterministic (ND)  
**Dataset:** test_list.csv (IDoFT known-flaky Java tests).

> A test counts toward flakiness only if it first compiles and passes in normal order. Broken tests are excluded (and logged) before detection.

## Summary

| #  | Project      | Class                | Gen | Passed | Failed | ID  | OD                    | ND |
|----|--------------|----------------------|-----|--------|--------|-----|-----------------------|----|
| 1  | edn-java     | Printers             | 8   | 4      | 4      | 0/4 | ⚠️ mixed JUnit 4+5   | 0  |
| 2  | apollo-java  | ItemOpenApiService   | 15  | 10     | 5      | 0/10| ⚠️ mixed JUnit 4+5   | 0  |

**Totals: 2 projects · 0 ID-flaky · 0 OD-flaky (iDFlakies blocked by mixed JUnit) · 0 ND-flaky**

## Failure patterns observed

| Pattern | Projects |
|---|---|
| Wrong GPT assumptions (wrong exceptions, wrong output format) | edn-java, apollo-java |
| Mockito cannot mock final class (Gson) | apollo-java |
| iDFlakies blocked by mixed JUnit 4+5 | edn-java, apollo-java |

## Null results — abandoned projects

| Project | Reason |
|---|---|
| fastjson | ExceptionInInitializerError — sun.reflect.annotation incompatible with Java 11 |
| dubbo-common | Multi-module build conflicts, internal version mismatches |

## Methodology

1. Clone project at flaky commit SHA
2. `mvn install -DskipTests` to build
3. Add ChatUniTest plugin (gpt-4o-mini, OpenAI API)
4. Add JUnit Jupiter + mockito-junit-jupiter dependencies
5. Run `chatunitest:class` on target class
6. Copy tests to `src/test/java`, delete `*_Suite.java`
7. Run `mvn test`
8. 100x loop to check ND flakiness
9. NonDex for ID flakiness
10. iDFlakies for OD flakiness