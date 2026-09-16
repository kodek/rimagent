using HarmonyLib;
using RimBridge.Server;
using Verse;

namespace RimBridge.Patches
{
    [HarmonyPatch(typeof(Root), nameof(Root.Update))]
    public static class Patch_Root_Update
    {
        public static void Postfix()
        {
            try { MainThreadQueue.Drain(); }
            catch (System.Exception ex) { BridgeLog.Error("drain failed: " + ex); }
        }
    }
}
