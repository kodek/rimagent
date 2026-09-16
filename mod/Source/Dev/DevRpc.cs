using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using RimBridge.Engine;
using RimBridge.Ledger;
using RimBridge.Server;
using RimWorld;
using Verse;

namespace RimBridge.Dev
{
    /// <summary>Training/curriculum tools. Every call flags the current game as 'assisted' in the ledger.</summary>
    public static class DevRpc
    {
        static Verse.Map Map()
        {
            GameCtl.GameControl.RequirePlaying();
            if (!Prefs.DevMode) throw new RpcError("dev tools require dev mode (game.dev_mode)");
            if (!EventLedger.Assisted) { EventLedger.Assisted = true; EventLedger.Add("assisted", "dev tool used; this game is now marked assisted"); }
            return Find.CurrentMap;
        }

        [Rpc("dev.spawn", "{def: ThingDef, cell: [x,z], count?: 1, stuff?: ThingDef, quality?: Awful..Legendary} spawn items/buildings (assisted)")]
        public static JToken Spawn(JObject p)
        {
            var map = Map();
            var def = Lookup.Def<ThingDef>(P.Str(p, "def"));
            var cell = Lookup.Cell(p["cell"]);
            int count = P.Int(p, "count", 1);
            ThingDef? stuff = p["stuff"] != null ? Lookup.Def<ThingDef>(P.Str(p, "stuff")) : (def.MadeFromStuff ? GenStuff.DefaultStuffFor(def) : null);
            var spawned = new JArray();
            int remaining = count;
            while (remaining > 0)
            {
                var t = ThingMaker.MakeThing(def, stuff);
                int n = Math.Min(remaining, def.stackLimit > 0 ? def.stackLimit : 1);
                t.stackCount = n; remaining -= n;
                if (p["quality"] != null && t.TryGetComp<CompQuality>() is { } cq) cq.SetQuality((QualityCategory)Enum.Parse(typeof(QualityCategory), P.Str(p, "quality"), true), ArtGenerationContext.Colony);
                if (def.category == ThingCategory.Building) t.SetFaction(Faction.OfPlayer);
                GenPlace.TryPlaceThing(t, cell, map, ThingPlaceMode.Near);
                spawned.Add(Render.ThingHandle(t));
                if (def.category == ThingCategory.Building) break;
            }
            EventLedger.Add("dev", $"spawned {count}x {def.defName}");
            return spawned;
        }

        [Rpc("dev.spawn_pawn", "{kind: PawnKindDef, cell: [x,z], faction?: Player|<name>|none, count?: 1} spawn pawns (assisted)")]
        public static JToken SpawnPawn(JObject p)
        {
            var map = Map();
            var kind = Lookup.Def<PawnKindDef>(P.Str(p, "kind"));
            var cell = Lookup.Cell(p["cell"]);
            string f = P.Str(p, "faction", "Player");
            Faction? faction = f.Equals("none", StringComparison.OrdinalIgnoreCase) ? null : Lookup.FactionOrNull(f) ?? throw new RpcError("unknown faction");
            var arr = new JArray();
            for (int i = 0; i < P.Int(p, "count", 1); i++)
            {
                var pawn = PawnGenerator.GeneratePawn(new PawnGenerationRequest(kind, faction, PawnGenerationContext.NonPlayer, forceGenerateNewPawn: true));
                GenSpawn.Spawn(pawn, CellFinder.RandomClosewalkCellNear(cell, map, 4), map);
                arr.Add(Render.PawnHandle(pawn));
            }
            EventLedger.Add("dev", $"spawned {arr.Count}x {kind.defName} ({f})");
            return arr;
        }

        [Rpc("dev.incident", "{def: IncidentDef (e.g. RaidEnemy, ColdSnap, Flashstorm, TraderCaravanArrival), points?: float, faction?: name} fire an incident now (assisted)")]
        public static JToken Incident(JObject p)
        {
            var map = Map();
            var def = Lookup.Def<IncidentDef>(P.Str(p, "def"));
            var parms = StorytellerUtility.DefaultParmsNow(def.category, map);
            if (p["points"] != null) parms.points = P.Float(p, "points");
            if (p["faction"] != null) parms.faction = Lookup.FactionOrNull(P.Str(p, "faction")) ?? throw new RpcError("unknown faction");
            parms.forced = true;
            if (!def.Worker.CanFireNow(parms)) BridgeLog.Warning($"dev.incident {def.defName}: CanFireNow false, forcing anyway");
            bool ok = def.Worker.TryExecute(parms);
            EventLedger.Add("dev", $"incident {def.defName} points={parms.points} ok={ok}");
            return new JObject { ["fired"] = ok, ["def"] = def.defName, ["points"] = parms.points };
        }

        [Rpc("dev.god_mode", "{enabled: bool} instant build/free everything (assisted)")]
        public static JToken God(JObject p) { Map(); DebugSettings.godMode = P.Bool(p, "enabled", true); return new JObject { ["god_mode"] = DebugSettings.godMode }; }

        [Rpc("dev.heal", "{pawn} remove all injuries/diseases (assisted)")]
        public static JToken Heal(JObject p)
        {
            Map();
            var pawn = Lookup.Pawn(P.Str(p, "pawn"));
            foreach (var h in pawn.health.hediffSet.hediffs.ToList()) if (h is Hediff_Injury || h.def.tendable || h.def.makesSickThought || h is Hediff_MissingPart) pawn.health.RemoveHediff(h);
            return Render.PawnHandle(pawn);
        }

        [Rpc("dev.set_need", "{pawn, need: NeedDef (Food, Rest, Joy, Mood...), level: 0..1} (assisted)")]
        public static JToken SetNeed(JObject p)
        {
            Map();
            var pawn = Lookup.Pawn(P.Str(p, "pawn"));
            var need = pawn.needs.TryGetNeed(Lookup.Def<NeedDef>(P.Str(p, "need"))) ?? throw new RpcError("pawn lacks that need");
            need.CurLevelPercentage = P.Float(p, "level");
            return new JObject { ["need"] = need.def.defName, ["level"] = need.CurLevelPercentage };
        }

        [Rpc("dev.finish_research", "{def} complete a research project instantly (assisted)")]
        public static JToken FinishResearch(JObject p)
        {
            Map();
            var def = Lookup.Def<ResearchProjectDef>(P.Str(p, "def"));
            Find.ResearchManager.FinishProject(def, false, null, false);
            return new JObject { ["finished"] = def.defName };
        }

        [Rpc("dev.weather", "{def: WeatherDef} force weather (assisted)")]
        public static JToken Weather(JObject p) { var map = Map(); var def = Lookup.Def<WeatherDef>(P.Str(p, "def")); map.weatherManager.TransitionTo(def); return new JObject { ["weather"] = def.defName }; }

        [Rpc("dev.destroy", "{thing} destroy a thing (assisted)")]
        public static JToken Destroy(JObject p) { Map(); var t = Lookup.ThingOrNull(P.Str(p, "thing")) ?? Lookup.Pawn(P.Str(p, "thing")); t.Destroy(); return new JObject { ["destroyed"] = t.ThingID }; }

        [Rpc("dev.damage", "{pawn|thing, amount, def?: Cut|Blunt|Gunshot|Burn} apply damage (assisted)")]
        public static JToken Damage(JObject p)
        {
            Map();
            var t = Lookup.ThingOrNull(P.OptStr(p, "thing") ?? P.Str(p, "pawn")) ?? Lookup.Pawn(P.Str(p, "pawn"));
            var dd = Lookup.Def<DamageDef>(P.Str(p, "def", "Cut"));
            t.TakeDamage(new DamageInfo(dd, P.Float(p, "amount")));
            return t is Pawn pw ? Render.PawnHandle(pw) : (JToken)Render.ThingHandle(t);
        }

        [Rpc("dev.kill_hostiles", "kill every hostile pawn on the map (assisted)")]
        public static JToken KillHostiles(JObject p)
        {
            var map = Map();
            int n = 0;
            foreach (var pw in map.mapPawns.AllPawnsSpawned.Where(x => x.HostileTo(Faction.OfPlayer)).ToList()) { pw.Kill(null); n++; }
            return new JObject { ["killed"] = n };
        }

        [Rpc("dev.reveal_map", "remove fog of war (assisted)")]
        public static JToken Reveal(JObject p) { var map = Map(); map.fogGrid.ClearAllFog(); return true; }
    }
}
