using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using RimBridge.Engine;
using RimBridge.Server;
using RimWorld;
using Verse;

namespace RimBridge.State
{
    /// <summary>Electrical grid perception and wiring: what is powered, what is not, and how to connect it.</summary>
    public static class PowerRpc
    {
        static Verse.Map Map() { GameCtl.GameControl.RequirePlaying(); return Find.CurrentMap; }

        [Rpc("state.power", "power nets with generation/consumption/storage and members, plus every UNPOWERED consumer with the nearest conduit or transmitter cell. Read this when anything electrical is not working.")]
        public static JToken Power(JObject p)
        {
            var map = Map();
            var nets = new JArray();
            int i = 0;
            foreach (var net in map.powerNetManager.AllNetsListForReading)
            {
                float gain = 0, use = 0;
                foreach (var c in net.powerComps) { if (!c.PowerOn) continue; if (c.PowerOutput > 0) gain += c.PowerOutput; else use += -c.PowerOutput; }
                nets.Add(new JObject
                {
                    ["net"] = i++,
                    ["generation_w"] = Math.Round(gain), ["consumption_w"] = Math.Round(use),
                    ["stored_wd"] = Math.Round(net.CurrentStoredEnergy()), ["capacity_wd"] = Math.Round(net.batteryComps.Sum(b => b.Props.storedEnergyMax)),
                    ["producers"] = new JArray(net.powerComps.Where(c => c.Props.PowerConsumption < 0 || c.PowerOutput > 0).Select(c => c.parent.ThingID + (c.PowerOn ? "" : " (off)"))),
                    ["consumers"] = new JArray(net.powerComps.Where(c => c.Props.PowerConsumption > 0).Select(c => c.parent.ThingID + (c.PowerOn ? "" : " (OFF: no power or switched off)"))),
                    ["batteries"] = new JArray(net.batteryComps.Select(b => b.parent.ThingID)),
                    ["conduit_cells"] = net.transmitters.Count(t => t.parent.def == ThingDefOf.PowerConduit),
                });
            }
            // unpowered consumers: things with a CompPowerTrader that consume power and have no net
            var unpowered = new JArray();
            var transmitterCells = new List<IntVec3>();
            foreach (var b in map.listerBuildings.allBuildingsColonist)
                if (b.TransmitsPowerNow) transmitterCells.Add(b.Position);
            foreach (var b in map.listerBuildings.allBuildingsColonist)
            {
                var cp = b.TryGetComp<CompPowerTrader>();
                if (cp == null || cp.Props.PowerConsumption <= 0) continue;
                if (cp.PowerNet != null && cp.PowerOn) continue;
                var o = Render.ThingHandle(b);
                o["needs_w"] = Math.Round(cp.Props.PowerConsumption);
                o["reason"] = cp.PowerNet == null ? "not connected to any net (no conduit/transmitter adjacent)" : (!cp.PowerOn ? "on a net but off: net has no power, or the building is switched off/broken" : "?");
                if (transmitterCells.Count > 0)
                {
                    var near = transmitterCells.OrderBy(c => c.DistanceTo(b.Position)).First();
                    o["nearest_conduit"] = Snapshot.Cell(near); o["conduit_dist"] = (int)near.DistanceTo(b.Position);
                }
                unpowered.Add(o);
            }
            var pendingConduits = map.listerThings.ThingsInGroup(ThingRequestGroup.Blueprint).Count(t => t.def.entityDefToBuild == ThingDefOf.PowerConduit);
            return new JObject { ["nets"] = nets, ["unpowered_consumers"] = unpowered, ["conduit_blueprints_pending"] = pendingConduits, ["tip"] = "connect with ui.wire(from=<thing or cell>, to=<thing or cell>); conduits can run under walls and doors. Batteries store, generators produce, everything must touch a conduit or another powered building." };
        }

        [Rpc("map.power", "{x?, z?, around?, w?: 30, h?: 30} the ELECTRICAL camera: = conduit, G generator, B battery, C powered consumer, X UNPOWERED consumer, digits = net id under a transmitter, + door, # wall, . other. Use before and after wiring.")]
        public static JToken PowerView(JObject p)
        {
            var map = Map();
            IntVec3 center;
            if (p["around"] != null) { var t = Lookup.ThingOrNull(P.Str(p, "around")) ?? Lookup.Pawn(P.Str(p, "around")); center = t.PositionHeld; }
            else { var home = Snapshot.HomeCenter(map); center = new IntVec3(P.Int(p, "x", home.x), 0, P.Int(p, "z", home.z)); }
            int w = Math.Min(P.Int(p, "w", 30), 60), h = Math.Min(P.Int(p, "h", 30), 60);
            var box = CellRect.CenteredOn(center, w, h).ClipInsideMap(map);
            var netIds = new Dictionary<PowerNet, int>();
            int n = 0; foreach (var net in map.powerNetManager.AllNetsListForReading) netIds[net] = n++;
            var sb = new System.Text.StringBuilder();
            sb.Append("      "); for (int x = box.minX; x <= box.maxX; x++) sb.Append(x >= 100 ? (x / 100).ToString() : " "); sb.Append('\n');
            sb.Append("      "); for (int x = box.minX; x <= box.maxX; x++) sb.Append((x / 10 % 10).ToString()); sb.Append('\n');
            sb.Append("      "); for (int x = box.minX; x <= box.maxX; x++) sb.Append((x % 10).ToString()); sb.Append('\n');
            var things = new JArray(); var seen = new HashSet<Thing>();
            for (int z = box.maxZ; z >= box.minZ; z--)
            {
                sb.Append(z.ToString().PadLeft(4)).Append("  ");
                for (int x = box.minX; x <= box.maxX; x++)
                {
                    var c = new IntVec3(x, 0, z);
                    char g = '.';
                    Building? edifice = c.GetEdifice(map);
                    Thing? conduit = null; Thing? powered = null; Blueprint? bp = null;
                    foreach (var t in c.GetThingList(map))
                    {
                        if (t.def == ThingDefOf.PowerConduit) conduit = t;
                        else if (t is Blueprint b && b.def.entityDefToBuild == ThingDefOf.PowerConduit) bp = b;
                        else if (t.TryGetComp<CompPower>() != null) powered = t;
                    }
                    if (powered != null)
                    {
                        var cp = powered.TryGetComp<CompPower>();
                        if (powered.TryGetComp<CompPowerBattery>() != null) g = 'B';
                        else if (cp is CompPowerTrader tr) g = tr.Props.PowerConsumption < 0 ? 'G' : (tr.PowerOn ? 'C' : 'X');
                        else g = 'c';
                        if (seen.Add(powered)) { var o = Render.ThingHandle(powered); o["net"] = cp?.PowerNet != null && netIds.TryGetValue(cp.PowerNet, out var nid) ? nid : (int?)null; o["powered"] = (cp as CompPowerTrader)?.PowerOn; things.Add(o); }
                    }
                    else if (conduit != null) { var cp = conduit.TryGetComp<CompPower>(); g = cp?.PowerNet != null && netIds.TryGetValue(cp.PowerNet, out var nid) ? (char)('0' + (nid % 10)) : '='; }
                    else if (bp != null) g = '~';
                    else if (edifice is Building_Door) g = '+';
                    else if (edifice != null && edifice.def.category == ThingCategory.Building && edifice.def.building?.isNaturalRock != true && edifice.def.passability == Traversability.Impassable) g = '#';
                    else if (edifice != null && edifice.def.building?.isNaturalRock == true) g = '^';
                    sb.Append(g);
                }
                sb.Append('\n');
            }
            return new JObject { ["box"] = Render.Value(box, 1), ["grid"] = sb.ToString(), ["legend"] = "digit = conduit on that net id, = conduit (no net), ~ conduit blueprint, G generator, B battery, C powered consumer, X UNPOWERED consumer, c other power building, + door, # wall, ^ rock", ["things"] = things, ["nets"] = netIds.Count };
        }

        [Rpc("ui.wire", "{from: thing|cell, to: thing|cell, dry_run?: false} lay power conduit blueprints along a walkable path between two points (conduits go under walls/doors). Returns the path and any cells that could not take a conduit.")]
        public static JToken Wire(JObject p)
        {
            var map = Map();
            IntVec3 a = Locate.Cell(p["from"], map, "from"), b = Locate.Cell(p["to"], map, "to");
            bool dry = P.Bool(p, "dry_run", false);
            var conduit = ThingDefOf.PowerConduit;
            bool Ok(IntVec3 c) => c.InBounds(map) && !c.Fogged(map) && c.GetTerrain(map).passability != Traversability.Impassable && (c.GetEdifice(map) == null || c.GetEdifice(map).def.building?.isNaturalRock != true);
            // BFS (4-neighbour) over cells where a conduit can exist
            var prev = new Dictionary<IntVec3, IntVec3>(); var q = new Queue<IntVec3>(); q.Enqueue(a); prev[a] = a;
            IntVec3? found = null; int steps = 0;
            while (q.Count > 0 && steps++ < 20000)
            {
                var c = q.Dequeue();
                if (c.AdjacentToCardinal(b) || c == b) { found = c; break; }
                foreach (var d in GenAdj.CardinalDirections)
                {
                    var nc = c + d;
                    if (prev.ContainsKey(nc) || !Ok(nc)) continue;
                    prev[nc] = c; q.Enqueue(nc);
                }
            }
            if (found == null) throw new RpcError("no path for conduits between those points");
            var path = new List<IntVec3>(); for (var c = found.Value; c != a; c = prev[c]) path.Add(c); path.Add(a); path.Reverse();
            var placed = new JArray(); var skipped = new JArray(); var failed = new JArray();
            foreach (var c in path)
            {
                if (c.GetThingList(map).Any(t => t.def == conduit || (t is Blueprint bb && bb.def.entityDefToBuild == conduit) || t.TryGetComp<CompPower>() != null)) { skipped.Add(Snapshot.Cell(c)); continue; }
                var rep = GenConstruct.CanPlaceBlueprintAt(conduit, c, Rot4.North, map, false, null, null, null);
                if (!rep.Accepted) { failed.Add(new JObject { ["cell"] = Snapshot.Cell(c), ["reason"] = rep.Reason?.StripTags() }); continue; }
                if (!dry) GenConstruct.PlaceBlueprintForBuild(conduit, c, map, Rot4.North, Faction.OfPlayer, null);
                placed.Add(Snapshot.Cell(c));
            }
            return new JObject { ["from"] = Snapshot.Cell(a), ["to"] = Snapshot.Cell(b), ["path_length"] = path.Count, ["placed"] = placed, ["skipped_already_powered"] = skipped, ["failed"] = failed, ["dry_run"] = dry, ["steel_cost"] = placed.Count };
        }

        [Rpc("dev.unlock_all_research", "finish every research project (assisted)")]
        public static JToken UnlockAll(JObject p)
        {
            GameCtl.GameControl.RequirePlaying();
            if (!Ledger.EventLedger.Assisted) { Ledger.EventLedger.Assisted = true; Ledger.EventLedger.Add("assisted", "dev tool used; this game is now marked assisted"); }
            Find.ResearchManager.DebugSetAllProjectsFinished();
            return new JObject { ["finished"] = DefDatabase<ResearchProjectDef>.AllDefs.Count(r => r.IsFinished) };
        }

        [Rpc("state.work_matrix", "every colonist x every work type: current priority, relevant skill level and passion, disabled flags. The raw material for a priority matrix.")]
        public static JToken WorkMatrix(JObject p)
        {
            var map = Map();
            var cols = new JArray();
            foreach (var pawn in map.mapPawns.FreeColonists)
            {
                var row = new JObject { ["pawn"] = pawn.LabelShort, ["id"] = pawn.ThingID };
                var wt = new JObject();
                foreach (var w in DefDatabase<WorkTypeDef>.AllDefs.OrderByDescending(w => w.naturalPriority))
                {
                    if (pawn.WorkTypeIsDisabled(w)) { wt[w.defName] = "X"; continue; }
                    var skills = w.relevantSkills.Select(s => pawn.skills?.GetSkill(s));
                    var best = skills.Where(s => s != null).OrderByDescending(s => s!.Level).FirstOrDefault();
                    wt[w.defName] = new JObject { ["pri"] = pawn.workSettings?.GetPriority(w) ?? 0, ["skill"] = best?.Level, ["passion"] = best?.passion.ToString() };
                }
                row["work"] = wt;
                cols.Add(row);
            }
            return new JObject { ["colonists"] = cols, ["manual_priorities"] = Current.Game.playSettings.useWorkPriorities };
        }

        [Rpc("ui.set_work_many", "{matrix: {pawn: {WorkType: 0-4, ...}, ...}} set many colonists' priorities in one call")]
        public static JToken SetWorkMany(JObject p)
        {
            Map();
            var m = P.Obj(p, "matrix") ?? throw new RpcError("missing matrix");
            var res = new JObject();
            foreach (var kv in m)
                res[kv.Key] = Ui.UiRpc.SetWork(new JObject { ["pawn"] = kv.Key, ["priorities"] = kv.Value });
            return res;
        }
    }
}
