using System;
using System.Collections.Generic;
using System.Text;

namespace RimBridge.Engine
{
    /// <summary>
    /// Pure parser for engine paths (no Verse dependency, unit-tested).
    ///   Find.CurrentMap.mapPawns.FreeColonists[2].health.hediffSet.hediffs
    ///   Thing:Human1234.needs.mood.CurLevel
    ///   Def:ThingDef:Steel.BaseMarketValue
    ///   Type:RimWorld.GenConstruct
    ///   Map.listerThings.ThingsOfDef(Def:ThingDef:Steel)   <- calls with args only via engine.call; in paths only "()" is allowed
    /// </summary>
    public sealed class PathSegment
    {
        public string Name = "";
        public bool IsCall;
        public List<string> Indexers = new List<string>();
        public override string ToString() => Name + (IsCall ? "()" : "") + string.Concat(Indexers.ConvertAll(i => "[" + i + "]"));
    }

    public sealed class ParsedPath
    {
        /// <summary>Root tag: "" for plain identifiers, or Thing/Def/Type/Pawn/Zone/Area/Faction.</summary>
        public string RootTag = "";
        /// <summary>Root arguments after the tag (e.g. ["ThingDef","Steel"]) or [identifier] when RootTag is empty.</summary>
        public List<string> RootArgs = new List<string>();
        public List<PathSegment> Segments = new List<PathSegment>();
        public List<string> RootIndexers = new List<string>();
        public bool RootIsCall;
    }

    public static class PathParser
    {
        static readonly HashSet<string> Tags = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "Thing", "Def", "Type", "Pawn", "Zone", "Area", "Faction", "Room" };

        public static ParsedPath Parse(string path)
        {
            if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("empty path");
            var p = new ParsedPath();
            int i = 0;
            path = path.Trim();

            // Root: tag:arg(:arg)* or identifier
            string first = ReadIdent(path, ref i);
            if (i < path.Length && path[i] == ':' && Tags.Contains(first))
            {
                p.RootTag = Capitalize(first);
                while (i < path.Length && path[i] == ':')
                {
                    i++;
                    p.RootArgs.Add(ReadRootArg(path, ref i, allowDots: p.RootTag == "Type"));
                }
            }
            else
            {
                p.RootArgs.Add(first);
            }
            // Root may be followed by () and indexers
            if (Peek(path, i, "()")) { p.RootIsCall = true; i += 2; }
            while (i < path.Length && path[i] == '[') p.RootIndexers.Add(ReadIndexer(path, ref i));

            while (i < path.Length)
            {
                if (path[i] != '.') throw new ArgumentException($"unexpected '{path[i]}' at {i} in '{path}'");
                i++;
                var seg = new PathSegment { Name = ReadIdent(path, ref i) };
                if (Peek(path, i, "()")) { seg.IsCall = true; i += 2; }
                while (i < path.Length && path[i] == '[') seg.Indexers.Add(ReadIndexer(path, ref i));
                p.Segments.Add(seg);
            }
            return p;
        }

        static bool Peek(string s, int i, string what) => i + what.Length <= s.Length && string.CompareOrdinal(s, i, what, 0, what.Length) == 0;

        static string Capitalize(string s) => char.ToUpperInvariant(s[0]) + s.Substring(1).ToLowerInvariant();

        static string ReadIdent(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && (char.IsLetterOrDigit(s[i]) || s[i] == '_')) i++;
            if (i == start) throw new ArgumentException($"expected identifier at {i} in '{s}'");
            return s.Substring(start, i - start);
        }

        /// <summary>
        /// Root args: quoted strings, or unquoted [A-Za-z0-9_ +-]. For the Type tag the arg may contain dots
        /// (namespaces); the Reflector then resolves the longest prefix that is a type and treats the rest as members.
        /// </summary>
        static string ReadRootArg(string s, ref int i, bool allowDots)
        {
            int start = i;
            if (i < s.Length && (s[i] == '"' || s[i] == '\''))
            {
                char q = s[i++];
                var sb = new StringBuilder();
                while (i < s.Length && s[i] != q) sb.Append(s[i++]);
                if (i >= s.Length) throw new ArgumentException("unterminated quote in root arg");
                i++;
                return sb.ToString();
            }
            while (i < s.Length && (char.IsLetterOrDigit(s[i]) || s[i] == '_' || s[i] == '-' || s[i] == '+' || s[i] == '`' || s[i] == ' ' || (allowDots && s[i] == '.')))
                i++;
            if (i == start) throw new ArgumentException($"expected value at {i} in '{s}'");
            return s.Substring(start, i - start).Trim();
        }

        static string ReadIndexer(string s, ref int i)
        {
            // s[i] == '['
            i++;
            var sb = new StringBuilder();
            if (i < s.Length && (s[i] == '"' || s[i] == '\''))
            {
                char q = s[i++];
                while (i < s.Length && s[i] != q) sb.Append(s[i++]);
                if (i >= s.Length) throw new ArgumentException("unterminated quote in indexer");
                i++;
            }
            else
            {
                while (i < s.Length && s[i] != ']') sb.Append(s[i++]);
            }
            if (i >= s.Length || s[i] != ']') throw new ArgumentException($"expected ']' at {i} in '{s}'");
            i++;
            return sb.ToString().Trim();
        }
    }
}
