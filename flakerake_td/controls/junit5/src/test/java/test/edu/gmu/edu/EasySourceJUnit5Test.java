package test.edu.gmu.edu;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.concurrent.ForkJoinPool;

/**
 * JUnit 5 port (by us) of the three tests in controls/junit4 (which are copied from gmu-swe/flakerake
 * integration-test/EasySourceTest, MIT License). Same bodies; only the annotations and the assertion class differ.
 */
public class EasySourceJUnit5Test {

    volatile int sharedInt = 0;

    @BeforeEach
    public void reset() {
        sharedInt = 0;
    }

    @Test
    public void testSingleThreadedNoInterception() {
        System.out.println("Passed!");
    }

    @Test
    public void testMultipleThreadsWithSynchronized() throws InterruptedException {
        Thread t1 = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    Thread.sleep(0);
                    incrementSharedInt();
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
        });
        Thread t2 = new Thread(this::otherIncrementSharedInt);
        t1.start();
        t2.start();
        Thread.sleep(5000);
        Assertions.assertEquals(2, sharedInt);
        t1.join();
        t2.join();
    }

    private synchronized void incrementSharedInt() {
        sharedInt++;
    }

    private void otherIncrementSharedInt() {
        synchronized (this) {
            sharedInt++;
        }
    }

    @Test
    public void sleepsBeginOfRunThreadMethods() throws InterruptedException {
        Thread thread = new Thread(() -> sharedInt++);
        thread.start();
        ForkJoinPool pool = new ForkJoinPool(5);
        pool.execute(() -> {System.out.println(Thread.currentThread());
            try {
                // Need to do this to force the ForkJoinPool to make new worker thread.
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        });
        pool.execute(() -> sharedInt++);
        pool.execute(() -> sharedInt++);

        System.out.println("Started all threads");
        Thread.sleep(5000);
        Assertions.assertEquals(3, sharedInt);
    }
}
