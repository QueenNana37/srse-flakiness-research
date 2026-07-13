# Flakiness of AI-Generated Java Tests — Results Log

**Question:** When ChatUniTest (gpt-4o-mini) generates unit tests for a Java class, are the generated tests themselves flaky?  
**Detectors:** NonDex → implementation-dependent (ID) · iDFlakies → order-dependent (OD) · 100x loop → non-deterministic (ND)  
**Dataset:** test_list.csv (IDoFT known-flaky Java tests).

> A test counts toward flakiness only if it first compiles and passes in normal order. Broken tests are excluded before detection.

Generated tests for **3 classes across 3 projects**. **2 came back completely clean. 1 class produced an ID flaky test** — crane4j-core `ObjectUtils` (details below).

## Summary

| #  | Project      | Class              | Gen | Passed | Failed | ID             | OD                  | ND |
|----|--------------|--------------------|-----|--------|--------|----------------|---------------------|----|
| 1  | edn-java     | Printers           | 8   | 4      | 4      | 0/4            | ⚠️ mixed JUnit 4+5 | 0  |
| 2  | apollo-java  | ItemOpenApiService | 15  | 10     | 5      | 0/10           | ⚠️ mixed JUnit 4+5 | 0  |
| 3  | crane4j-core | ObjectUtils        | 47  | 46     | 1      | **1/46 FLAKY** | ⚠️ mixed JUnit 4+5 | 0  |

**Totals: 2 clean classes · 1 ID-flaky class · iDFlakies blocked by mixed JUnit on all projects · 0 ND-flaky**

## The flaky test — crane4j-core `ObjectUtils`

ChatUniTest generated `testGetFromMap`. It **passes in normal order but fails under NonDex** when HashMap iteration order is randomized.

**Root cause:** GPT used a `HashMap` and assumed entries come out in insertion order (`value1` at index 0, `value2` at index 1, `value3` at index 2). HashMap does not guarantee insertion order — when NonDex shuffles it, the assertions fail.

```java
Map<String, String> map = new HashMap<>();
map.put("key1", "value1");
map.put("key2", "value2");
map.put("key3", "value3");
assertEquals("value1", ObjectUtils.get(map, 0)); // FLAKY — order not guaranteed
```

The fix would be to use `LinkedHashMap` instead of `HashMap`, or avoid asserting on specific index positions.

## Failure patterns observed

| Pattern | Projects |
|---|---|
| Wrong GPT assumptions (wrong exceptions, wrong output format) | edn-java, apollo-java, crane4j-core |
| Mockito cannot mock final class (Gson) | apollo-java |
| GPT assumes HashMap insertion order | crane4j-core ← **caused ID flakiness** |
| iDFlakies blocked by mixed JUnit 4+5 | all 3 projects |

## Null results — abandoned projects

| Project | Reason |
|---|---|
| fastjson | ExceptionInInitializerError — sun.reflect.annotation incompatible with Java 11 |
| dubbo-common | Multi-module build conflicts, internal version mismatches |

## Methodology

1. Clone project at flaky commit SHA
2. `mvn install -DskipTests` to build
3. Add ChatUniTest plugin (gpt-4o-mini, direct OpenAI API)
4. Add JUnit Jupiter + mockito-junit-jupiter to test dependencies
5. Run `chatunitest:class` on target class
6. Copy tests to `src/test/java`, delete `*_Suite.java`
7. Run `mvn test`
8. 100x loop to check ND flakiness
9. NonDex for ID flakiness
10. iDFlakies for OD flakiness