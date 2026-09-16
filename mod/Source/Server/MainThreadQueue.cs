using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace RimBridge.Server
{
    /// <summary>A unit of work that must run on the Unity main thread.</summary>
    public sealed class MainThreadJob
    {
        public Func<JToken?> Work = null!;
        public JToken? Result;
        public Exception? Error;
        public readonly ManualResetEventSlim Done = new ManualResetEventSlim(false);
        /// <summary>Frames to wait before running (used by screenshot: move camera, then capture next frame).</summary>
        public int DelayFrames;
    }

    /// <summary>
    /// Request threads enqueue jobs; the Root.Update Harmony postfix drains them every frame
    /// (main menu and play scene, paused or not).
    /// </summary>
    public static class MainThreadQueue
    {
        private static readonly ConcurrentQueue<MainThreadJob> Queue = new ConcurrentQueue<MainThreadJob>();
        private static readonly ConcurrentQueue<MainThreadJob> Delayed = new ConcurrentQueue<MainThreadJob>();
        public static int FrameCount;
        public static bool MainThreadAlive => FrameCount > 0;
        private static long _lastDrainTicks;

        public static JToken? Run(Func<JToken?> work, int timeoutMs = 30000, int delayFrames = 0)
        {
            var job = new MainThreadJob { Work = work, DelayFrames = delayFrames };
            Queue.Enqueue(job);
            if (!job.Done.Wait(timeoutMs))
                throw new TimeoutException($"main thread did not run the job within {timeoutMs} ms (last drain {(Stopwatch.GetTimestamp() - _lastDrainTicks) / (double)Stopwatch.Frequency:F1}s ago)");
            if (job.Error != null) throw job.Error;
            return job.Result;
        }

        /// <summary>Called from the Root.Update postfix. Never throws.</summary>
        public static void Drain(int budgetMs = 200)
        {
            FrameCount++;
            _lastDrainTicks = Stopwatch.GetTimestamp();
            var sw = Stopwatch.StartNew();
            // Re-queue delayed jobs whose wait expired.
            int n = Delayed.Count;
            for (int i = 0; i < n; i++)
            {
                if (!Delayed.TryDequeue(out var d)) break;
                if (--d.DelayFrames > 0) Delayed.Enqueue(d); else Queue.Enqueue(d);
            }
            while (sw.ElapsedMilliseconds < budgetMs && Queue.TryDequeue(out var job))
            {
                if (job.DelayFrames > 0) { Delayed.Enqueue(job); continue; }
                try { job.Result = job.Work(); }
                catch (Exception ex) { job.Error = ex; }
                finally { job.Done.Set(); }
            }
        }
    }
}
