# ChatUniTest JUnit 4 mode

Patch and prompts that make ChatUniTest (core 2.1.1) write JUnit 4 tests instead of JUnit 5.
JUnit 5 stays the default, and the JUnit 4 mode only turns on with `-Dchatunitest.junit=4`.

## What is here
- `chatunitest-core-junit4.patch`: patch for ZJU-ACES-ISE/chatunitest-core at commit 9852d41 ("update the version to 2.1.1"). It changes TestSkeleton.java and AbstractRunner.java and adds util/JUnitFlavor.java. `git apply --check` passes on 9852d41.
- `prompts-junit4/`: prompt templates for JUnit 4 (extra.ftl is empty). Use with `-DpromptPath`.
- `scripts/`: small helper scripts used for the ReproFlake work.

## Build the patched core
Standard Maven steps, but not yet re-run from scratch for this README.

```
git clone https://github.com/ZJU-ACES-ISE/chatunitest-core.git
cd chatunitest-core && git checkout 9852d41
git apply /path/to/chatunitest-core-junit4.patch
mvn clean install -DskipTests -Dmaven.repo.local=<local repo>
```

Then run the released plugin io.github.zju-aces-ise:chatunitest-maven-plugin:2.1.1 with the same `-Dmaven.repo.local`, so it picks up the patched core.

## Run
Key goes in an environment variable (`OPENAI_API_KEY`). i put it so it never commits our key.

```
mvn io.github.zju-aces-ise:chatunitest-maven-plugin:2.1.1:method "-DselectMethod=<package.Class>#<method name or method number>" -Dchatunitest.junit=4 -DpromptPath=<path to prompts-junit4> -DtmpOutput=<tmp dir> -Dmodel=gpt-4o-mini -Durl=https://api.openai.com/v1/chat/completions "-DapiKeys=$OPENAI_API_KEY" -Dmaven.repo.local=<local repo>
```

- `#<method number>` picks one overload. The number is the file name in `<tmpOutput>/<project>/class-info/<package path>/<Class>/<n>.json`.
- The `methodWithoutOverload` goal does not work with the released plugin 2.1.1: the signature never matched (3 runs, "Method not found").
- Use a separate `-DtmpOutput` and `-DtestOutput` for each run, or runs overwrite each other.

## Results so far (gpt-4o-mini, one run each unless noted)
| Project and method | ChatUniTest said | Real `mvn test` |
|---|---|---|
| BOOKKEEPER-846 LedgerChecker.checkLedger | 1 success | does not compile (project is source 1.7 with -Werror) |
| Adyen Checkout.payments | 1 success | 3 of 3 tests error |
| edn-java Printers.printString(Object) | 1 success | 1 of 1 passes (simple case) |
| edn-java Printers.printString(Protocol, Object), 3 runs | 0 tests | n/a: 75 rounds, 66 compile failures, 9 run failures |

## Things to know
- ChatUniTest's own "success" is not reliable (Adyen). Count a test only if `mvn test` shows `Tests run:` of at least 1 and it passes.
- ChatUniTest compiles generated tests at the JDK's default source level, not the project's.
- edn-java needed mockito-core 4.11.0 added to its pom as a test dependency. That version was chosen by us, not by the project.
- The original ChatUniTest prompt says "use reflection to invoke private methods". It is likely part of why the model writes reflection workarounds.
- On the edn two-argument method the errors were invented methods (115 missing symbols, 9 different names) and `new Printers()` on a private constructor.