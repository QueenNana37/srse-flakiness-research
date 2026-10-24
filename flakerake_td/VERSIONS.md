
# Which package version produced what
- v2 (flaky_check_package_flakerake_v2.zip, sha256 30a6a55f54bf4e067908c31927d9696d2b3a9bc86be47edebb36f9df850ff671): JDK 8 + JUnit 4 only. Produced the stage-1 results in flakerake_stage1_results.csv (16 methods: 11 false, 5 inconclusive, 0 true; 23-24 Oct 2026).
- v4 (flaky_check_package_flakerake_v4.zip, sha256 fbf568308911a347345260d28f1719ebf4ddcfd2561790d72e6b5579ae9a1664): the files in this folder. Adds the JUnit 5 runner (JDK 8), controls, a run lock and night_run.py. JDK 11 rows are not run (FlakeRake's agent needs JDK 8).
- v3 was never run (v4 replaces it).
Details: README_flakerake.md and flakerake/PATCHES.md.
