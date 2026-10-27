#!/usr/bin/env python3
"""Build the FlakeRake agent + runners with ASM 9 (for JDK 9 and newer) into their OWN Maven repository.

Why: the agent that `flaky_check.py` builds from flakerake/sleepy-parent uses ASM 5.0.3. That cannot read the class files of
JDK 11 (not even the JDK's own java.lang.Thread, which the agent has to rewrite), see flakerake/PATCHES.md "ASM 9 agent".
This script builds a second agent from a temporary COPY of flakerake/sleepy-parent with two files replaced by the ones in
flakerake/asm9/overlay/ (pom.xml: ASM 9.7.1 instead of asm-all 5.0.3; SleepyInterceptingAgent.java: ASM5 -> ASM9, one line).
flakerake/sleepy-parent itself is not touched, so the JDK 8 agent stays exactly as it was.

    python3 flakerake/asm9/build_asm9_agent.py --repo ~/.m2/flakerake-asm9-repository --jdk /usr/lib/jvm/java-8-openjdk-amd64

--repo is passed to Maven as -Dmaven.repo.local, so it is a complete Maven repository of its own (the first build downloads the
plugins and dependencies again). The jars end up in
<repo>/edu/gmu/swe/flaky/sleepy/{sleepy-interceptor,sleepy-runner}/0.0.4-SNAPSHOT/, the same path findFlakySleeps.py reads
through MAVEN_REPO. Exit code 0 = jars are there (built now, or up to date), 1 = failed (the Maven output is shown).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = [("sleepy-interceptor", "sleepy-interceptor-0.0.4-SNAPSHOT.jar"),
             ("sleepy-runner", "sleepy-runner-0.0.4-SNAPSHOT.jar")]
RUNNER5 = "edu/gmu/swe/flaky/sleepy/runner/SleepyJUnit5Runner.class"
ASM_CLASS = "agent/org/objectweb/asm/Opcodes.class"  # ASM's shaded constants; ASM 5.0.3's has ASM4 and ASM5 only


def jar_paths(repo):
    base = Path(repo) / "edu" / "gmu" / "swe" / "flaky" / "sleepy"
    return [base / a / "0.0.4-SNAPSHOT" / j for a, j in ARTIFACTS]


def check_jars(repo):
    """"" if both jars are there and are what we expect, else the reason why not."""
    interceptor, runner = jar_paths(repo)
    for j in (interceptor, runner):
        if not j.is_file():
            return f"{j} is missing"
    try:
        with zipfile.ZipFile(interceptor) as z:
            names = set(z.namelist())
            if "edu/gmu/swe/flaky/sleepy/intercept/SleepyInterceptingAgent.class" not in names:
                return "the interceptor jar has no SleepyInterceptingAgent class"
            if ASM_CLASS not in names:
                return "the interceptor jar has no shaded ASM (agent/org/objectweb/asm)"
            if b"ASM9" not in z.read(ASM_CLASS):
                return "the shaded ASM in the interceptor jar is older than ASM 9 (no ASM9 constant)"
        with zipfile.ZipFile(runner) as z:
            if RUNNER5 not in z.namelist():
                return "the runner jar has no SleepyJUnit5Runner"
    except (OSError, zipfile.BadZipFile) as ex:
        return f"cannot read the jars: {ex}"
    return ""


def newest_source(fr):
    files = [f for f in (fr / "sleepy-parent").rglob("*") if f.is_file() and "target" not in f.parts]
    files += [f for f in (fr / "asm9" / "overlay").rglob("*") if f.is_file()]
    return max(f.stat().st_mtime for f in files)


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--repo", type=Path, required=True, help="Maven repository for the ASM 9 agent (its own, not ~/.m2/repository)")
    a.add_argument("--jdk", type=Path, required=True, help="JDK home to build with (JDK 8, as for the other agent)")
    a.add_argument("--flakerake-dir", type=Path, default=HERE.parent, help="the patched FlakeRake folder (default: flakerake/)")
    a.add_argument("--force", action="store_true", help="build even if the jars look up to date")
    args = a.parse_args()
    fr, repo, jdk = args.flakerake_dir.resolve(), args.repo.expanduser().resolve(), args.jdk.resolve()
    overlay = fr / "asm9" / "overlay"
    if not (fr / "sleepy-parent" / "pom.xml").is_file() or not overlay.is_dir():
        print(f"ERROR: {fr} has no sleepy-parent/pom.xml or asm9/overlay/")
        return 1
    if not (jdk / "bin" / "javac").exists():
        print(f"ERROR: no javac in {jdk}/bin (a JDK, not a JRE, is needed)")
        return 1
    if repo == (Path.home() / ".m2" / "repository").resolve():
        print("ERROR: --repo must not be ~/.m2/repository: the ASM 9 agent has the same file names as the ASM 5 agent there")
        return 1
    why = check_jars(repo)
    if not why and not args.force:
        jars = jar_paths(repo)
        if all(j.stat().st_mtime >= newest_source(fr) for j in jars):
            print(f"ASM 9 agent is up to date in {repo}")
            return 0
        why = "the jars are older than the sources"
    print(f"Building the ASM 9 agent into {repo} ({why or 'forced'})", flush=True)

    work = Path(tempfile.mkdtemp(prefix="flakerake_asm9_build_"))
    try:
        src = work / "sleepy-parent"
        shutil.copytree(fr / "sleepy-parent", src, ignore=shutil.ignore_patterns("target"))
        for f in sorted(p for p in overlay.rglob("*") if p.is_file()):
            rel = f.relative_to(overlay)
            dest = src / rel
            if not dest.is_file():
                print(f"ERROR: overlay file {rel} replaces nothing in sleepy-parent (upstream layout changed?)")
                return 1
            if dest.read_bytes() == f.read_bytes():
                print(f"ERROR: overlay file {rel} is identical to the original, nothing would change")
                return 1
            shutil.copyfile(f, dest)
            print(f"  replaced {rel}", flush=True)
        env = dict(os.environ)
        env["JAVA_HOME"] = str(jdk)
        env["PATH"] = str(jdk / "bin") + os.pathsep + env.get("PATH", "")
        cmd = ["mvn", "-B", "-f", str(src / "pom.xml"), "install", "-DskipTests", "-Dmaven.repo.local=" + str(repo)]
        print("  " + " ".join(cmd), flush=True)
        code = subprocess.run(cmd, env=env, cwd=str(work)).returncode
        why = check_jars(repo)
        if code != 0 or why:
            print(f"ERROR: the ASM 9 agent build failed (mvn exit {code}{'; ' + why if why else ''}). "
                  f"Build folder kept for inspection: {work}")
            work = None
            return 1
        print(f"ASM 9 agent built: {jar_paths(repo)[0]}")
        return 0
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
