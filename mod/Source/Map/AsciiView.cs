using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using RimWorld;
using Verse;

namespace RimBridge.MapView
{
    /// <summary>Layered ASCII rendering of a map region, one character per cell. z grows upward (top row = max z).</summary>
    public static class AsciiView
    {
        public const string Legend =
            "? fog | @ colonist | ! hostile | a colony animal | w wild animal | n other pawn | # wall | + door | ^ rock | o ore | " +
            "b bed | t work table | s stove/campfire | r research | g power | % turret | x other building | p blueprint/frame | " +
            "S stockpile | G growing zone | ~ water | T tree | , plant/crop | i item | * fire | f fertile soil | : sand/gravel | - floor/road | . ground";

        public static readonly string[] Layers = { "all", "terrain", "buildings", "zones", "pawns", "items", "roof", "fog", "home" };

        public static string RenderLayer(Verse.Map map, CellRect box, string layer)
        {
            box = box.ClipInsideMap(map);
            var hostiles = new HashSet<IntVec3>();
            var colonists = new HashSet<IntVec3>();
            var animals = new HashSet<IntVec3>();
            var wild = new HashSet<IntVec3>();
            var others = new HashSet<IntVec3>();
            if (layer == "all" || layer == "pawns")
            {
                foreach (var p in map.mapPawns.AllPawnsSpawned)
                {
                    if (!box.Contains(p.Position)) continue;
                    if (p.HostileTo(Faction.OfPlayer)) hostiles.Add(p.Position);
                    else if (p.IsColonist) colonists.Add(p.Position);
                    else if (p.Faction == Faction.OfPlayer) animals.Add(p.Position);
                    else if (p.Faction == null && p.RaceProps.Animal) wild.Add(p.Position);
                    else others.Add(p.Position);
                }
            }
            var sb = new StringBuilder();
            // x header: label every 10 cells
            sb.Append("     ");
            for (int x = box.minX; x <= box.maxX; x++) sb.Append(x % 10 == 0 ? (x / 10 % 10).ToString() : " ");
            sb.Append('\n');
            sb.Append("     ");
            for (int x = box.minX; x <= box.maxX; x++) sb.Append(x % 10 == 0 ? "|" : (x % 5 == 0 ? ":" : " "));
            sb.Append('\n');
            for (int z = box.maxZ; z >= box.minZ; z--)
            {
                sb.Append(z.ToString().PadLeft(4)).Append(' ');
                for (int x = box.minX; x <= box.maxX; x++)
                {
                    var c = new IntVec3(x, 0, z);
                    sb.Append(Glyph(map, c, layer, hostiles, colonists, animals, wild, others));
                }
                sb.Append('\n');
            }
            return sb.ToString();
        }

        static char Glyph(Verse.Map map, IntVec3 c, string layer, HashSet<IntVec3> hostiles, HashSet<IntVec3> colonists, HashSet<IntVec3> animals, HashSet<IntVec3> wild, HashSet<IntVec3> others)
        {
            bool all = layer == "all";
            if ((all || layer == "fog") && c.Fogged(map)) return '?';
            if (layer == "fog") return '.';
            if (layer == "roof")
            {
                var roof = c.GetRoof(map);
                return roof == null ? '.' : roof.isThickRoof ? 'R' : roof.isNatural ? 'r' : 'c';
            }
            if (layer == "home") return map.areaManager.Home[c] ? 'H' : '.';
            if (all || layer == "pawns")
            {
                if (hostiles.Contains(c)) return '!';
                if (colonists.Contains(c)) return '@';
                if (animals.Contains(c)) return 'a';
                if (wild.Contains(c)) return 'w';
                if (others.Contains(c)) return 'n';
                if (layer == "pawns") return '.';
            }
            if (all || layer == "buildings")
            {
                var ed = c.GetEdifice(map);
                if (ed != null)
                {
                    var d = ed.def;
                    if (d.building != null && d.building.isResourceRock) return 'o';
                    if (d.building != null && d.building.isNaturalRock) return '^';
                    if (ed is Building_Door) return '+';
                    if (d.IsSmoothed || d.IsSmoothable) return '^';
                    if (d.defName.Contains("Wall") || (d.fillPercent >= 1f && !d.building.isTrap && d.passability == Traversability.Impassable && d.size == IntVec2.One && d.category == ThingCategory.Building && !(ed is Building_Turret))) return '#';
                    if (ed is Building_Bed) return 'b';
                    if (ed is Building_Turret) return '%';
                    if (ed is Building_ResearchBench) return 'r';
                    if (d.defName.Contains("Stove") || d.defName.Contains("Campfire") || d.defName.Contains("Brazier")) return 's';
                    if (ed is Building_WorkTable) return 't';
                    if (d.HasComp(typeof(CompPowerPlant)) || d.HasComp(typeof(CompPowerBattery))) return 'g';
                    return 'x';
                }
                foreach (var t in c.GetThingList(map))
                {
                    if (t is Blueprint || t is Frame) return 'p';
                    if (t.def.category == ThingCategory.Building && !(t is Building_Door)) { if (t.def.defName.Contains("Conduit")) continue; return 'x'; }
                }
                if (layer == "buildings") return '.';
            }
            if (all || layer == "items")
            {
                foreach (var t in c.GetThingList(map))
                {
                    if (t is Fire) return '*';
                    if (t.def.category == ThingCategory.Item) return 'i';
                }
                if (layer == "items") return '.';
            }
            if (all || layer == "zones")
            {
                var z = c.GetZone(map);
                if (z is Zone_Stockpile) return 'S';
                if (z is Zone_Growing) return 'G';
                if (layer == "zones") return '.';
            }
            // terrain + plants
            var terrain = c.GetTerrain(map);
            if (terrain.IsWater) return '~';
            var plant = c.GetPlant(map);
            if (plant != null) return plant.def.plant.IsTree ? 'T' : ',';
            if (terrain.layerable || terrain.defName.Contains("Road") || terrain.defName.Contains("Bridge") || terrain.defName.Contains("Floor") || terrain.defName.Contains("Tile") || terrain.defName.Contains("Carpet")) return '-';
            if (terrain.fertility >= 1.0f) return 'f';
            if (terrain.fertility <= 0.1f && terrain.fertility > 0f) return ':';
            if (terrain.fertility == 0f) return terrain.passability == Traversability.Impassable ? '^' : ':';
            return '.';
        }
    }
}
