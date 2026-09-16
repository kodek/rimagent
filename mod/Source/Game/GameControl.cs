using System;
using System.IO;
using System.Linq;
using HarmonyLib;
using Newtonsoft.Json.Linq;
using RimBridge.Ledger;
using RimBridge.Server;
using RimWorld;
using RimWorld.Planet;
using Verse.Profile;
using Verse;

namespace RimBridge.GameCtl
{
    /// <summary>Pending new-game request consumed by the Root_Play.SetupForQuickTestPlay prefix.</summary>
    public sealed class NewGameRequest
    {
        public string Scenario = "Crashlanded";
        public string Storyteller = "Cassandra";
        public string Difficulty = "Rough";
        public string? Seed;
        public int MapSize = 250;
        public float Coverage = 0.3f;
        public bool Permadeath = false;
    }

    public static class GameControl
    {
        public static NewGameRequest? Pending;
        public static string LastJobStatus = "idle";

        [Rpc("game.status", "-> {state: menu|playing|loading, tick, day, hour, season, speed, paused, map_size, colonists, seq}")]
        public static JToken Status(JObject p)
        {
            var o = new JObject { ["seq"] = EventLedger.Seq, ["job"] = LastJobStatus, ["dev_mode"] = Prefs.DevMode, ["god_mode"] = DebugSettings.godMode };
            if (LongEventHandler.ShouldWaitForEvent || LongEventHandler.AnyEventNowOrWaiting) { o["state"] = "loading"; return o; }
            if (Current.ProgramState != ProgramState.Playing || Find.CurrentMap == null) { o["state"] = "menu"; return o; }
            var map = Find.CurrentMap;
            var tm = Find.TickManager;
            o["state"] = "playing";
            o["tick"] = tm.TicksGame;
            o["day"] = GenDate.DaysPassed;
            o["hour"] = GenLocalDate.HourInteger(map);
            o["date"] = GenDate.DateFullStringAt(Find.TickManager.TicksAbs, Find.WorldGrid.LongLatOf(map.Tile));
            o["season"] = GenLocalDate.Season(map).ToString();
            o["speed"] = (int)tm.CurTimeSpeed;
            o["paused"] = tm.Paused;
            o["map_size"] = new JArray(map.Size.x, map.Size.z);
            o["colonists"] = map.mapPawns.FreeColonistsCount;
            o["storyteller"] = Find.Storyteller?.def?.defName;
            o["difficulty"] = Find.Storyteller?.difficultyDef?.defName;
            o["seed"] = Find.World?.info?.seedString;
            o["assisted"] = EventLedger.Assisted;
            return o;
        }

        [Rpc("game.speed", "{speed: 0..4} set time speed (0 pause, 1 normal, 2 fast, 3 superfast, 4 ultrafast/dev)")]
        public static JToken Speed(JObject p)
        {
            RequirePlaying();
            int s = P.Int(p, "speed");
            if (s < 0 || s > 4) throw new RpcError("speed must be 0..4");
            Find.TickManager.CurTimeSpeed = (TimeSpeed)s;
            return new JObject { ["speed"] = (int)Find.TickManager.CurTimeSpeed, ["paused"] = Find.TickManager.Paused };
        }

        [Rpc("game.pause", "{paused: bool}")]
        public static JToken Pause(JObject p)
        {
            RequirePlaying();
            bool paused = P.Bool(p, "paused", true);
            var tm = Find.TickManager;
            if (paused && !tm.Paused) tm.Pause();
            else if (!paused && tm.Paused) tm.TogglePaused();
            return new JObject { ["paused"] = tm.Paused, ["speed"] = (int)tm.CurTimeSpeed };
        }

        [Rpc("game.save", "{name} save the current game")]
        public static JToken Save(JObject p)
        {
            RequirePlaying();
            string name = P.Str(p, "name");
            GameDataSaveLoader.SaveGame(name);
            return new JObject { ["saved"] = name, ["path"] = GenFilePaths.FilePathForSavedGame(name) };
        }

        [Rpc("game.list_saves", "-> [{name, modified}]")]
        public static JToken ListSaves(JObject p)
        {
            var arr = new JArray();
            foreach (var f in GenFilePaths.AllSavedGameFiles.OrderByDescending(f => f.LastWriteTime))
                arr.Add(new JObject { ["name"] = Path.GetFileNameWithoutExtension(f.Name), ["modified"] = f.LastWriteTime.ToString("s") });
            return arr;
        }

        [Rpc("game.load", "{name} load a saved game (async; poll game.status until state=playing)")]
        public static JToken Load(JObject p)
        {
            string name = P.Str(p, "name");
            if (!File.Exists(GenFilePaths.FilePathForSavedGame(name))) throw new RpcError($"no save named '{name}'");
            LastJobStatus = "loading " + name;
            GameDataSaveLoader.LoadGame(name); // vanilla path: disposes the current game, loads the Play scene, then the save
            LongEventHandler.QueueLongEvent(() => { LastJobStatus = "idle"; EventLedger.Add("game", "loaded save " + name); }, null, false, null);
            return new JObject { ["loading"] = name };
        }

        [Rpc("game.new_game", "{scenario?: defName, storyteller?: defName, difficulty?: defName, seed?: string, map_size?: 200..300, permadeath?: bool} start a fresh game (async; poll game.status)")]
        public static JToken NewGame(JObject p)
        {
            var r = new NewGameRequest
            {
                Scenario = P.Str(p, "scenario", "Crashlanded"),
                Storyteller = P.Str(p, "storyteller", "Cassandra"),
                Difficulty = P.Str(p, "difficulty", "Rough"),
                Seed = P.OptStr(p, "seed"),
                MapSize = P.Int(p, "map_size", 250),
                Permadeath = P.Bool(p, "permadeath", false),
            };
            if (DefDatabase<ScenarioDef>.GetNamedSilentFail(r.Scenario) == null) throw new RpcError($"unknown scenario '{r.Scenario}'. Known: " + string.Join(", ", DefDatabase<ScenarioDef>.AllDefs.Select(d => d.defName)));
            if (DefDatabase<StorytellerDef>.GetNamedSilentFail(r.Storyteller) == null) throw new RpcError($"unknown storyteller '{r.Storyteller}'. Known: " + string.Join(", ", DefDatabase<StorytellerDef>.AllDefs.Select(d => d.defName)));
            if (DefDatabase<DifficultyDef>.GetNamedSilentFail(r.Difficulty) == null) throw new RpcError($"unknown difficulty '{r.Difficulty}'. Known: " + string.Join(", ", DefDatabase<DifficultyDef>.AllDefs.Select(d => d.defName)));
            Pending = r;
            LastJobStatus = "starting new game";
            // Same shape as GameDataSaveLoader.LoadGame: dispose the current game (if any), load the Play scene with
            // Current.Game == null so Root_Play.Start takes the quicktest path, which our prefix intercepts.
            Current.Game?.Dispose();
            LongEventHandler.QueueLongEvent(() =>
            {
                MemoryUtility.ClearAllMapsAndWorld();
                Current.Game = null;
            }, "Play", "GeneratingMap", true, GameAndMapInitExceptionHandlers.ErrorWhileGeneratingMap);
            return new JObject { ["starting"] = true, ["scenario"] = r.Scenario, ["seed"] = r.Seed };
        }

        [Rpc("game.quit_to_menu", "leave the current game")]
        public static JToken QuitToMenu(JObject p)
        {
            RequirePlaying();
            GenScene.GoToMainMenu();
            return true;
        }

        [Rpc("game.dev_mode", "{enabled: bool, god?: bool}")]
        public static JToken DevMode(JObject p)
        {
            Prefs.DevMode = P.Bool(p, "enabled", true);
            if (p["god"] != null) DebugSettings.godMode = P.Bool(p, "god", false);
            return new JObject { ["dev_mode"] = Prefs.DevMode, ["god_mode"] = DebugSettings.godMode };
        }

        [Rpc("game.log_tail", "{lines?: 100, filter?: substring} tail Player.log", MainThread = false)]
        public static JToken LogTail(JObject p)
        {
            int n = P.Int(p, "lines", 100);
            string? filter = P.OptStr(p, "filter");
            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal), "Library/Logs/Ludeon Studios/RimWorld by Ludeon Studios/Player.log");
            if (!File.Exists(path)) throw new RpcError("Player.log not found at " + path);
            string[] lines;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs)) lines = sr.ReadToEnd().Split('\n');
            var q = lines.AsEnumerable();
            if (!string.IsNullOrEmpty(filter)) q = q.Where(l => l.IndexOf(filter!, StringComparison.OrdinalIgnoreCase) >= 0);
            var tail = q.Reverse().Take(n).Reverse();
            return string.Join("\n", tail);
        }

        [Rpc("bridge.methods", "list all rpc methods with docs", MainThread = false)]
        public static JToken Methods(JObject p) => Rpc.Describe();

        public static void RequirePlaying()
        {
            if (Current.ProgramState != ProgramState.Playing || Find.CurrentMap == null)
                throw new RpcError("no game is running (state=" + Current.ProgramState + "); call game.new_game or game.load first");
        }
    }

    /// <summary>
    /// When the Play scene loads with Current.Game == null, vanilla calls SetupForQuickTestPlay (the dev quicktest
    /// path). If a NewGameRequest is pending we run our own parameterised setup instead.
    /// </summary>
    [HarmonyPatch(typeof(Root_Play), nameof(Root_Play.SetupForQuickTestPlay))]
    static class Patch_SetupForQuickTestPlay
    {
        static bool Prefix()
        {
            var r = GameControl.Pending;
            if (r == null) return true;
            GameControl.Pending = null;
            try
            {
                Current.ProgramState = ProgramState.Entry;
                Verse.Game.ClearCaches();
                Current.Game = new Verse.Game();
                Current.Game.InitData = new GameInitData();
                Current.Game.Scenario = DefDatabase<ScenarioDef>.GetNamed(r.Scenario).scenario;
                Find.Scenario.PreConfigure();
                Current.Game.storyteller = new Storyteller(DefDatabase<StorytellerDef>.GetNamed(r.Storyteller), DefDatabase<DifficultyDef>.GetNamed(r.Difficulty));
                string seed = string.IsNullOrEmpty(r.Seed) ? GenText.RandomSeedString() : r.Seed!;
                Current.Game.World = WorldGenerator.GenerateWorld(r.Coverage, seed, OverallRainfall.Normal, OverallTemperature.Normal, OverallPopulation.Normal, LandmarkDensity.Normal);
                Rand.PushState(seed.GetHashCode());
                try { Find.GameInitData.ChooseRandomStartingTile(); }
                finally { Rand.PopState(); }
                Find.GameInitData.mapSize = r.MapSize;
                Find.GameInitData.permadeath = r.Permadeath;
                Find.GameInitData.permadeathChosen = true;
                Find.Scenario.PostIdeoChosen();
                EventLedger.ResetForNewGame();
                GameControl.LastJobStatus = "idle";
                BridgeLog.Message($"new game: {r.Scenario} / {r.Storyteller} / {r.Difficulty} / seed {seed}");
                return false;
            }
            catch (Exception ex)
            {
                BridgeLog.Error("new game setup failed, falling back to vanilla quicktest: " + ex);
                GameControl.LastJobStatus = "error: " + ex.Message;
                return true;
            }
        }
    }

    [HarmonyPatch(typeof(TimeSlower), "ForcedNormalSpeed", MethodType.Getter)]
    static class Patch_NoForcedNormalSpeed
    {
        static void Postfix(ref bool __result) { if (RimBridgeMod.Settings?.neverPause == true) __result = false; }
    }

    [HarmonyPatch(typeof(WindowStack), "WindowsForcePause", MethodType.Getter)]
    static class Patch_NoWindowForcePause
    {
        static void Postfix(ref bool __result) { if (RimBridgeMod.Settings?.neverPause == true) __result = false; }
    }
}
