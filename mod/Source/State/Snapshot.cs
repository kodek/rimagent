using Newtonsoft.Json.Linq;
using Verse;

namespace RimBridge.State
{
    public static class Snapshot
    {
        public static JObject Daily(Map map) => new JObject { ["colonists"] = map.mapPawns.FreeColonistsCount };
    }
}
