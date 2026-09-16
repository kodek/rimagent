using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using RimWorld;
using UnityEngine;
using Verse;
using Verse.AI;
using Verse.AI.Group;

namespace RimBridge.Engine
{
    /// <summary>CLR object → compact JSON. Depth-limited; game objects render as handles the agent can pass back.</summary>
    public static class Render
    {
        public const int MaxItems = 200;
        public const int MaxMembers = 120;

        public static JToken Value(object? o, int depth, bool top = false)
        {
            try { return ValueInner(o, depth, top); }
            catch (Exception ex) { return new JObject { ["$error"] = ex.GetType().Name + ": " + ex.Message }; }
        }

        static JToken ValueInner(object? o, int depth, bool top)
        {
            if (o == null) return JValue.CreateNull();
            switch (o)
            {
                case string s: return s;
                case TaggedString ts: return ts.ToString().StripTags();
                case bool b: return b;
                case int i: return i;
                case long l: return l;
                case float f: return float.IsNaN(f) || float.IsInfinity(f) ? (JToken)f.ToString() : Math.Round(f, 3);
                case double d: return double.IsNaN(d) || double.IsInfinity(d) ? (JToken)d.ToString() : Math.Round(d, 3);
                case byte or sbyte or short or ushort or uint or ulong or decimal: return JToken.FromObject(o);
                case char c: return c.ToString();
                case Enum e: return e.ToString();
                case Type t: return "Type:" + t.FullName;
                case IntVec3 v: return new JArray(v.x, v.z);
                case IntVec2 v2: return new JArray(v2.x, v2.z);
                case Vector3 v3: return new JArray(Math.Round(v3.x, 2), Math.Round(v3.y, 2), Math.Round(v3.z, 2));
                case Vector2 vv: return new JArray(Math.Round(vv.x, 2), Math.Round(vv.y, 2));
                case CellRect r: return new JObject { ["min"] = new JArray(r.minX, r.minZ), ["max"] = new JArray(r.maxX, r.maxZ), ["w"] = r.Width, ["h"] = r.Height };
                case IntRange ir: return new JArray(ir.min, ir.max);
                case FloatRange fr: return new JArray(Math.Round(fr.min, 3), Math.Round(fr.max, 3));
                case Rot4 rot: return rot.ToStringWord();
                case Color col: return $"#{ColorUtility.ToHtmlStringRGBA(col)}";
                case DateTime dt: return dt.ToString("s");
            }
            if (!top)
            {
                // Handles for game objects when nested.
                switch (o)
                {
                    case Def def: return def.defName;
                    case Pawn p: return PawnHandle(p);
                    case Thing t: return ThingHandle(t);
                    case Faction f: return new JObject { ["name"] = f.Name, ["def"] = f.def.defName, ["hostile"] = f.HostileTo(Faction.OfPlayer), ["player"] = f.IsPlayer };
                    case Map m: return "Map:" + m.Index;
                    case Zone z: return new JObject { ["zone"] = z.label, ["type"] = z.GetType().Name, ["cells"] = z.Cells.Count };
                    case Area a: return a.Label;
                    case Room rm: return new JObject { ["room"] = rm.ID, ["role"] = rm.Role?.defName, ["cells"] = rm.CellCount };
                    case Job j: return new JObject { ["def"] = j.def?.defName, ["target"] = j.targetA.IsValid ? Value(j.targetA, 0) : null, ["forced"] = j.playerForced };
                    case LocalTargetInfo lt: return lt.HasThing ? Value(lt.Thing, 0) : (lt.IsValid ? new JArray(lt.Cell.x, lt.Cell.z) : JValue.CreateNull());
                    case Hediff h: return new JObject { ["def"] = h.def.defName, ["label"] = h.LabelCap.ToString(), ["part"] = h.Part?.Label, ["severity"] = Math.Round(h.Severity, 2) };
                    case SkillRecord sk: return new JObject { ["skill"] = sk.def.defName, ["level"] = sk.Level, ["passion"] = sk.passion.ToString(), ["disabled"] = sk.TotallyDisabled };
                    case Need n: return new JObject { ["need"] = n.def.defName, ["level"] = Math.Round(n.CurLevelPercentage, 2) };
                    case Thought th: return new JObject { ["thought"] = th.def.defName, ["label"] = th.LabelCap.ToString(), ["mood"] = Math.Round(th.MoodOffset(), 1) };
                    case Bill bill: return new JObject { ["bill"] = bill.recipe.defName, ["label"] = bill.LabelCap, ["suspended"] = bill.suspended, ["id"] = bill.GetUniqueLoadID() };
                    case Quest q: return new JObject { ["quest"] = q.id, ["name"] = q.name, ["state"] = q.State.ToString() };
                    case Verb vb: return new JObject { ["verb"] = vb.verbProps?.label, ["range"] = vb.verbProps?.range, ["tool"] = vb.tool?.label };
                    case Lord lord: return new JObject { ["lord"] = lord.loadID, ["faction"] = lord.faction?.Name, ["job"] = lord.LordJob?.GetType().Name, ["pawns"] = lord.ownedPawns.Count };
                    case Ideo ideo: return ideo.name;
                    case Precept pr: return pr.def.defName;
                    case Gene g: return g.def.defName;
                    case Trait tr: return new JObject { ["trait"] = tr.def.defName, ["degree"] = tr.Degree, ["label"] = tr.LabelCap };
                }
            }
            if (depth <= 0)
            {
                switch (o)
                {
                    case Def def: return def.defName;
                    case Pawn p: return PawnHandle(p);
                    case Thing t: return ThingHandle(t);
                }
                return o.ToString();
            }
            if (o is IDictionary dict)
            {
                var jo = new JObject();
                int n = 0;
                foreach (DictionaryEntry kv in dict)
                {
                    if (n++ >= MaxItems) { jo["$truncated"] = dict.Count; break; }
                    jo[KeyString(kv.Key)] = Value(kv.Value, depth - 1);
                }
                return jo;
            }
            if (o is IEnumerable en && !(o is string))
            {
                var arr = new JArray();
                int n = 0;
                int total = 0;
                foreach (var x in en)
                {
                    total++;
                    if (n >= MaxItems) continue;
                    arr.Add(Value(x, depth - 1));
                    n++;
                }
                if (total > MaxItems) arr.Add(new JObject { ["$truncated"] = total });
                return arr;
            }
            return ObjectMembers(o, depth, top);
        }

        static string KeyString(object k) => k switch { Def d => d.defName, Thing t => t.ThingID, _ => k?.ToString() ?? "null" };

        public static JObject ThingHandle(Thing t)
        {
            var o = new JObject { ["id"] = t.ThingID, ["def"] = t.def.defName, ["label"] = t.LabelCap.ToString() };
            if (t.Spawned) o["pos"] = new JArray(t.Position.x, t.Position.z);
            else if (t.PositionHeld.IsValid) { o["pos"] = new JArray(t.PositionHeld.x, t.PositionHeld.z); o["held"] = true; }
            if (t.stackCount > 1) o["count"] = t.stackCount;
            if (t.Faction != null && !t.Faction.IsPlayer) o["faction"] = t.Faction.Name;
            if (t.Destroyed) o["destroyed"] = true;
            return o;
        }

        public static JObject PawnHandle(Pawn p)
        {
            var o = new JObject { ["id"] = p.ThingID, ["name"] = p.LabelShort, ["kind"] = p.kindDef?.defName };
            if (p.Spawned) o["pos"] = new JArray(p.Position.x, p.Position.z);
            if (p.Faction != null) o["faction"] = p.Faction.IsPlayer ? "Player" : p.Faction.Name;
            if (p.HostileTo(Faction.OfPlayer)) o["hostile"] = true;
            if (p.Dead) o["dead"] = true;
            else if (p.Downed) o["downed"] = true;
            if (p.Drafted) o["drafted"] = true;
            return o;
        }

        /// <summary>Dump public instance fields/properties. Skips indexers, delegates, and members that throw.</summary>
        public static JObject ObjectMembers(object o, int depth, bool includeSummary)
        {
            var type = o.GetType();
            var jo = new JObject { ["$type"] = type.FullName };
            if (includeSummary)
            {
                switch (o)
                {
                    case Pawn p: jo["$handle"] = PawnHandle(p); break;
                    case Thing t: jo["$handle"] = ThingHandle(t); break;
                    case Def d: jo["$def"] = d.defName; jo["$label"] = d.label; break;
                }
            }
            int n = 0;
            foreach (var f in type.GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                if (n++ >= MaxMembers) break;
                if (typeof(Delegate).IsAssignableFrom(f.FieldType)) continue;
                try { jo[f.Name] = Value(f.GetValue(o), depth - 1); } catch { }
            }
            foreach (var pr in type.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (n++ >= MaxMembers) break;
                if (!pr.CanRead || pr.GetIndexParameters().Length > 0) continue;
                if (typeof(Delegate).IsAssignableFrom(pr.PropertyType)) continue;
                if (pr.PropertyType == typeof(IEnumerable) || pr.PropertyType.Name.StartsWith("IEnumerator")) continue;
                if (jo[pr.Name] != null) continue;
                try { jo[pr.Name] = Value(pr.GetValue(o), depth - 1); } catch { }
            }
            return jo;
        }
    }
}
