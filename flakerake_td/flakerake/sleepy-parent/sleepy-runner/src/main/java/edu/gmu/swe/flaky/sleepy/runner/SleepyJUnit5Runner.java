package edu.gmu.swe.flaky.sleepy.runner;

import edu.gmu.swe.flaky.sleepy.intercept.FlakyLogger;
import edu.gmu.swe.flaky.sleepy.intercept.Wrapper;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import org.junit.platform.launcher.listeners.TestExecutionSummary;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.HashSet;
import java.util.Scanner;

import static org.junit.platform.engine.discovery.DiscoverySelectors.selectMethod;

/**
 * ADDED (not part of upstream FlakeRake): the JUnit 5 counterpart of {@link SleepyTestRunner}.
 *
 * Same arguments, same files and same exit codes as SleepyTestRunner, so that findFlakySleeps.py
 * can use it with --runner_class:
 *   args 0) TestMethod as Class#method   1) ThreadID   2) logging level   3) sleep time ms
 *        4) optional file with the lines to sleep at
 * It runs the one method through the JUnit Platform Launcher (JUnit 4's JUnitCore cannot run Jupiter tests).
 *
 * Differences that matter:
 *  - JUnit 4 reports a wrong test name as a failure. The Launcher just finds nothing and reports "success".
 *    A run in which no test was started (also: only skipped or only aborted) would then be NoFail for ever,
 *    a silent false negative. Here it is a failure with the marker {@link #NO_TEST_MARKER} in
 *    failure.log and in the log, and the exit code is 1337 like any failure.
 *  - Needs junit-platform-launcher (and an engine) on the class path. The module's own test class path
 *    usually lacks the launcher; flaky_check.py adds it through FLAKERAKE_EXTRA_CP.
 */
public class SleepyJUnit5Runner {

    public static final String NO_TEST_MARKER = "SLEEPY_JUNIT5_NO_TEST_EXECUTED";

    public static void main(String... args) throws FileNotFoundException {
        String threadIdTarget = args[1];
        long initTimeToSleep = Long.parseLong(args[3]);

        Wrapper.init(threadIdTarget, initTimeToSleep);
        FlakyLogger.init(FlakyLogger.Level.valueOf(args[2].toUpperCase()));

        String[] classAndMethod = args[0].split("#");

        String targetLinesToSleep = null;
        if (args.length > 4) {
            targetLinesToSleep = args[4];
        }
        if (targetLinesToSleep != null) {
            Wrapper.linesToSleepDuringRun = new HashSet<>();
            File file = new File(targetLinesToSleep);
            Scanner scanner = new Scanner(file);
            while (scanner.hasNextLine()) {
                String target = scanner.nextLine().trim();
                Wrapper.linesToSleepDuringRun.add(target);
            }
        }

        LauncherDiscoveryRequest request = LauncherDiscoveryRequestBuilder.request()
                .selectors(selectMethod(classAndMethod[0], classAndMethod[1]))
                .build();
        Launcher launcher = LauncherFactory.create();
        SummaryGeneratingListener listener = new SummaryGeneratingListener();
        launcher.execute(request, listener);
        TestExecutionSummary summary = listener.getSummary();

        boolean failed = summary.getTotalFailureCount() > 0;
        boolean noTest = !failed && summary.getTestsStartedCount() == 0;

        // Like SleepyTestRunner: only write failure.log on a failing run (do not overwrite a clean run's state).
        if (failed || noTest) {
            StringBuilder failureBuilder = new StringBuilder();
            if (failed) {
                for (TestExecutionSummary.Failure fail : summary.getFailures()) {
                    StringWriter trace = new StringWriter();
                    fail.getException().printStackTrace(new PrintWriter(trace));
                    FlakyLogger.info("Failure:");
                    FlakyLogger.info(fail.getTestIdentifier().getDisplayName() + trace);
                    failureBuilder.append(trace);
                }
            } else {
                String msg = "java.lang.IllegalStateException: " + NO_TEST_MARKER + " for " + args[0]
                        + " (started=" + summary.getTestsStartedCount()
                        + ", skipped=" + summary.getTestsSkippedCount()
                        + ", found=" + summary.getTestsFoundCount() + ")\n";
                FlakyLogger.info(msg);
                System.out.println(msg);
                failureBuilder.append(msg);
            }
            PrintWriter failureReporter = new PrintWriter(new File("./sleepy-records/internal/failure.log"));
            failureReporter.write(failureBuilder.toString());
            failureReporter.close();
        }

        boolean ok = !failed && !noTest;
        FlakyLogger.info(ok ? "OK" : "FAILURE");
        System.exit(ok ? 0 : 1337);
    }
}
