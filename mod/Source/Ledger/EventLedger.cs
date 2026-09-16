using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using RimWorld;
using Verse;

namespace RimBridge.Ledger
{
    /// <summary>
    /// Append-only ring buffer of typed game events with a monotonic sequence number. Written on the main
    /// thread by Harmony patches; read from request threads via Since(). Also mirrored to ledger.jsonl in the
    /// mod folder so the agent can rebuild an episode timeline after a restart.
    /// </summary>
    public static class EventLedger
    {
        private const int MaxEvents = 20000;
        private static readonly object Lock = new object();
        private static readonly LinkedList<JObject> Events = new LinkedList<JObject>();
        private static long _seq;
        private static StreamWriter? _file;
        public static bool Assisted; // set when dev.* tools are used during the current game

        public static long Seq { get { lock (Lock) return _seq; } }

        public static void Add(string kind, string text, JObject? data = null, IntVec3? cell = null, string? thingId = null)
        {
            // Skip events fired during world/pawn generation and loading; only "game" markers pass.
            if (kind != "game" && Current.ProgramState != ProgramState.Playing) return;
            var e = new JObject
            {
                ["kind"] = kind,
                ["text"] = text,
            };
            try
            {
                if (Current.ProgramState == ProgramState.Playing && Find.TickManager != null)
                {
                    e["tick"] = Find.TickManager.TicksGame;
                    e["day"] = GenDate.DaysPassed;
                    e["hour"] = Find.CurrentMap != null ? GenLocalDate.HourInteger(Find.CurrentMap) : 0;
                }
            }
            catch { }
            if (cell.HasValue && cell.Value.IsValid) e["cell"] = new JArray(cell.Value.x, cell.Value.z);
            if (thingId != null) e["thing"] = thingId;
            if (data != null) e["data"] = data;
            lock (Lock)
            {
                e["seq"] = ++_seq;
                Events.AddLast(e);
                while (Events.Count > MaxEvents) Events.RemoveFirst();
                try
                {
                    _file ??= new StreamWriter(Path.Combine(ModRoot(), "ledger.jsonl"), append: true) { AutoFlush = true };
                    _file.WriteLine(e.ToString(Formatting.None));
                }
                catch { }
            }
        }

        public static JObject Since(long since, int limit)
        {
            var arr = new JArray();
            long last = since;
            lock (Lock)
            {
                foreach (var e in Events)
                {
                    long s = (long)e["seq"]!;
                    if (s <= since) continue;
                    arr.Add(e);
                    last = s;
                    if (arr.Count >= limit) break;
                }
                return new JObject { ["events"] = arr, ["last_seq"] = last, ["head_seq"] = _seq, ["assisted"] = Assisted };
            }
        }

        public static void ResetForNewGame()
        {
            lock (Lock) { Assisted = false; }
            Add("game", "new game started");
        }

        public static string ModRoot()
        {
            var mod = LoadedModManager.GetMod<RimBridgeMod>();
            return mod?.Content?.RootDir ?? Path.GetTempPath();
        }
    }
}
