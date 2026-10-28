#!/bin/bash
# Creates known_td/ in the package folder: two placeholder classes and known_td/known_td_tests.csv
# (the 7 known TD tests of CAMEL-12025 as known_td_row_900, the 1 of YARN-9405 as known_td_row_901).
# Run it in the package folder (where flaky_check.py is):   bash /path/to/setup_known_td.sh
# Nothing else is touched. See README_flakerake.md, "Known TD check".
[ -f flaky_check.py ] || { echo "run this in the package folder (the one with flaky_check.py)"; exit 1; }
set -e
mkdir -p known_td/runs/row_900/placeholder known_td/runs/row_901/placeholder
cat > known_td/runs/row_900/placeholder/KnownTdPlaceholderCamel.java <<'EOF'
// placeholder for the known TD check: copied into the module for the run, removed afterwards
public class KnownTdPlaceholderCamel {
}
EOF
cat > known_td/runs/row_901/placeholder/KnownTdPlaceholderYarn.java <<'EOF'
// placeholder for the known TD check: copied into the module for the run, removed afterwards
public class KnownTdPlaceholderYarn {
}
EOF
python3 - <<'EOF'
import csv
HEAD = ["project", "sha", "module", "generated_test", "test_file", "focal_method", "zip", "java", "junit",
        "mockito_fix", "focal_from_test", "focal_from_test_type"]
CAMEL = ("https://github.com/apache/camel", "c501ba7e6d8c94ad3c26c78a4ee941fdd745717f", "components/camel-reactor",
         "known_td/runs/row_900/placeholder/KnownTdPlaceholderCamel.java", "CAMEL-12025")
YARN = ("https://github.com/apache/hadoop", "eeda6891e49bc13ae86d0193f94238b7109e291d",
        "hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-services/hadoop-yarn-services-core",
        "known_td/runs/row_901/placeholder/KnownTdPlaceholderYarn.java", "YARN-9405")
R = "org.apache.camel.component.reactor.engine.ReactorStreamsServiceTest#"
rows = [(CAMEL, R + m) for m in ("testFromStreamTimer", "testMultipleSubscriptionsWithTimer", "testFrom", "testTo",
                                  "testToWithExchange", "testToFunction", "testToFunctionWithExchange")]
rows.append((YARN, "org.apache.hadoop.yarn.service.TestYarnNativeServices#testExpressUpgrade"))
with open("known_td/known_td_tests.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(HEAD)
    for (proj, sha, module, placeholder, zipname), test in rows:
        w.writerow([proj, sha, module, test, placeholder, test, zipname, "8", "4", "false", test, "td"])
print("wrote known_td/known_td_tests.csv with", len(rows), "tests")
EOF
