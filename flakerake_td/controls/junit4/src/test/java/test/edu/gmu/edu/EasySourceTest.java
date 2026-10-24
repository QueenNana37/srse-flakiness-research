package test.edu.gmu.edu;

import org.junit.Assert;
import org.junit.Before;
import org.junit.Test;

import java.util.concurrent.ForkJoinPool;

/**
 * Three tests copied from gmu-swe/flakerake integration-test/EasySourceTest.java (MIT License), unchanged except for
 * dropping the other tests of that class and an unused import. The comments are upstream's.
 */
public class EasySourceTest {

    volatile int sharedInt = 0;

    @Before
    public void tearDown() {
        sharedInt = 0;
    }

    @Test
    public void testSingleThreadedNoInterception() {
        System.out.println("Passed!");
    }

    @Test
    public void testMultipleThreadsWithSynchronized() throws InterruptedException {
        // Should result in showing that sleeping t1 and or t2 cause the same failures.
        // This test shows that depending on which thread reaches a sync primitive first, has an extra affect for sleeping in the function.
        // This is also a clear example of when our method does not find every possible failure.
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
        Assert.assertEquals(2, sharedInt);
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
        // NOTE to test this check that we're sleeping in the run methods of Thread and ForkJoinWorkerThread
        // Our tool should make this fail with both types of threads.
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
        Assert.assertEquals(3, sharedInt);
    }
}
