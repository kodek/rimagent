using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using RimBridge.Engine;
using RimBridge.Server;
using RimWorld;
using Verse;

namespace RimBridge.State
{
    public static class DefsRpc
    {
        [Rpc("defs.get", "{def: defName, type?: ThingDef|RecipeDef|ResearchProjectDef|... (auto-detected if omitted), depth?: 1} rich def info: costs, stats, recipes, research, what it unlocks")]
        public static JToken Get(JObject p)
        {
            string name = P.Str(p, "def");
            Def? def = null;
            if (p["type"] != null) def = Lookup.DefOrNull(Lookup.DefType(P.Str(p, "type")), name);
            else
                foreach (var t in new[] { typeof(ThingDef), typeof(RecipeDef), typeof(ResearchProjectDef), typeof(TerrainDef), typeof(PawnKindDef), typeof(HediffDef), typeof(JobDef), typeof(WorkTypeDef), typeof(IncidentDef), typeof(TraitDef), typeof(SkillDef), typeof(StatDef), typeof(ThingCategoryDef), typeof(BiomeDef), typeof(WeatherDef), typeof(PlantDef_Placeholder) })
                {
                    if (t == typeof(PlantDef_Placeholder)) continue;
                    def = Lookup.DefOrNull(t, name); if (def != null) break;
                }
            if (def == null) throw new RpcError($"no def named '{name}' (try defs.search)");
            var o = new JObject { ["def"] = def.defName, ["type"] = def.GetType().Name, ["label"] = def.label, ["description"] = def.description?.StripTags() };
            switch (def)
            {
                case ThingDef td:
                    o["category"] = td.category.ToString();
                    o["market_value"] = Math.Round(td.BaseMarketValue, 1);
                    o["mass"] = td.BaseMass;
                    o["stack_limit"] = td.stackLimit;
                    if (td.building != null || td.designationCategory != null)
                    {
                        o["buildable"] = td.BuildableByPlayer;
                        o["size"] = new JArray(td.size.x, td.size.z);
                        o["cost"] = new JObject((td.costList ?? new System.Collections.Generic.List<ThingDefCountClass>()).Select(c => new JProperty(c.thingDef.defName, c.count)));
                        if (td.MadeFromStuff) { o["stuff_cost"] = td.costStuffCount; o["stuff_categories"] = new JArray(td.stuffCategories.Select(s => s.defName)); }
                        o["work_to_build"] = Math.Round(td.GetStatValueAbstract(StatDefOf.WorkToBuild, td.MadeFromStuff ? GenStuff.DefaultStuffFor(td) : null));
                        o["research"] = new JArray((td.researchPrerequisites ?? new System.Collections.Generic.List<ResearchProjectDef>()).Select(r => r.defName));
                        o["research_done"] = td.IsResearchFinished;
                        if (td.building != null) { o["passable"] = td.passability.ToString(); o["power"] = td.GetCompProperties<CompProperties_Power>()?.PowerConsumption; o["is_bed"] = td.IsBed; o["work_table"] = td.IsWorkTable; }
                        var recipes = td.AllRecipes;
                        if (recipes != null && recipes.Count > 0) o["recipes"] = new JArray(recipes.Take(60).Select(r => r.defName + (r.AvailableNow ? "" : " (locked)")));
                    }
                    if (td.IsWeapon) { o["weapon"] = true; o["ranged"] = td.IsRangedWeapon; var v = td.Verbs?.FirstOrDefault(); if (v != null) { o["range"] = v.range; o["warmup"] = v.warmupTime; o["burst"] = v.burstShotCount; o["damage"] = v.defaultProjectile?.projectile?.GetDamageAmount(null); } }
                    if (td.IsApparel) { o["apparel"] = true; o["layers"] = new JArray(td.apparel.layers.Select(l => l.defName)); o["body_parts"] = new JArray(td.apparel.bodyPartGroups.Select(b => b.defName)); o["armor_sharp"] = Math.Round(td.GetStatValueAbstract(StatDefOf.ArmorRating_Sharp, td.MadeFromStuff ? GenStuff.DefaultStuffFor(td) : null), 2); o["insulation_cold"] = Math.Round(td.GetStatValueAbstract(StatDefOf.Insulation_Cold, td.MadeFromStuff ? GenStuff.DefaultStuffFor(td) : null), 1); }
                    if (td.IsNutritionGivingIngestible) { o["nutrition"] = td.GetStatValueAbstract(StatDefOf.Nutrition); o["food_type"] = td.ingestible.foodType.ToString(); o["preferability"] = td.ingestible.preferability.ToString(); }
                    if (td.plant != null) { o["plant"] = new JObject { ["sowable"] = td.plant.Sowable, ["grow_days"] = td.plant.growDays, ["harvest"] = td.plant.harvestedThingDef?.defName, ["yield"] = td.plant.harvestYield, ["min_fertility"] = td.plant.fertilityMin, ["fertility_sensitivity"] = td.plant.fertilitySensitivity, ["min_skill"] = td.plant.sowMinSkill, ["is_tree"] = td.plant.IsTree} ; }
                    if (td.race != null) { o["race"] = new JObject { ["animal"] = td.race.Animal, ["humanlike"] = td.race.Humanlike, ["wildness"] = Math.Round(td.GetStatValueAbstract(StatDefOf.Wildness), 2), ["predator"] = td.race.predator, ["body_size"] = td.race.baseBodySize, ["meat"] = td.GetStatValueAbstract(StatDefOf.MeatAmount), ["trainability"] = td.race.trainability?.defName, ["manhunter_on_damage"] = td.race.manhunterOnDamageChance, ["manhunter_on_tame_fail"] = td.race.manhunterOnTameFailChance }; }
                    if (td.building?.isResourceRock == true) o["mineable"] = new JObject { ["yields"] = td.building.mineableThing?.defName, ["amount"] = td.building.mineableYield };
                    o["used_by_recipes"] = new JArray(DefDatabase<RecipeDef>.AllDefs.Where(r => r.ingredients.Any(i => i.filter.Allows(td))).Take(30).Select(r => r.defName));
                    o["made_by_recipes"] = new JArray(DefDatabase<RecipeDef>.AllDefs.Where(r => r.products.Any(pr => pr.thingDef == td)).Take(30).Select(r => r.defName + " @ " + string.Join("/", r.AllRecipeUsers.Select(u => u.defName))));
                    break;
                case RecipeDef rd:
                    o["work"] = rd.workAmount;
                    o["skill"] = rd.workSkill?.defName; o["min_skill"] = rd.skillRequirements?.FirstOrDefault()?.minLevel;
                    o["ingredients"] = new JArray(rd.ingredients.Select(i => new JObject { ["count"] = i.GetBaseCount(), ["allowed"] = string.Join("/", i.filter.AllowedThingDefs.Take(8).Select(d => d.defName)) }));
                    o["products"] = new JObject(rd.products.Select(pr => new JProperty(pr.thingDef.defName, pr.count)));
                    o["at"] = new JArray(rd.AllRecipeUsers.Select(u => u.defName));
                    o["research"] = rd.researchPrerequisite?.defName; o["available"] = rd.AvailableNow;
                    break;
                case ResearchProjectDef rp:
                    o["cost"] = rp.baseCost; o["tech"] = rp.techLevel.ToString(); o["finished"] = rp.IsFinished; o["can_start"] = rp.CanStartNow; o["progress"] = Math.Round(rp.ProgressPercent * 100);
                    o["prerequisites"] = new JArray((rp.prerequisites ?? new System.Collections.Generic.List<ResearchProjectDef>()).Select(r => r.defName + (r.IsFinished ? " ✓" : "")));
                    o["bench"] = rp.requiredResearchBuilding?.defName; o["facilities"] = new JArray((rp.requiredResearchFacilities ?? new System.Collections.Generic.List<ThingDef>()).Select(f => f.defName));
                    o["unlocks"] = new JArray(rp.UnlockedDefs.Select(d => d.defName));
                    o["leads_to"] = new JArray(DefDatabase<ResearchProjectDef>.AllDefs.Where(r => r.prerequisites?.Contains(rp) == true).Select(r => r.defName));
                    break;
                case TerrainDef ter:
                    o["fertility"] = ter.fertility; o["buildable"] = ter.BuildableByPlayer; o["cost"] = new JObject((ter.costList ?? new System.Collections.Generic.List<ThingDefCountClass>()).Select(c => new JProperty(c.thingDef.defName, c.count))); o["research"] = new JArray((ter.researchPrerequisites ?? new System.Collections.Generic.List<ResearchProjectDef>()).Select(r => r.defName)); o["beauty"] = ter.GetStatValueAbstract(StatDefOf.Beauty);
                    break;
                case PawnKindDef pk:
                    o["race"] = pk.race.defName; o["combat_power"] = pk.combatPower; o["wildness"] = Math.Round(pk.race.GetStatValueAbstract(StatDefOf.Wildness), 2); o["predator"] = pk.race.race?.predator;
                    break;
                case IncidentDef inc:
                    o["category"] = inc.category.defName; o["min_threat_points"] = inc.minThreatPoints; o["base_chance"] = inc.baseChance;
                    break;
                case HediffDef hd:
                    o["tendable"] = hd.tendable; o["lethal_severity"] = hd.lethalSeverity; o["is_disease"] = hd.makesSickThought; o["stages"] = hd.stages?.Count;
                    break;
            }
            if (P.Int(p, "depth", 0) > 0) o["raw"] = Render.ObjectMembers(def, P.Int(p, "depth", 0), false);
            return o;
        }

        sealed class PlantDef_Placeholder : Def { }

        [Rpc("defs.search", "{query, type?: ThingDef|RecipeDef|ResearchProjectDef|..., limit?: 30} search defs by defName/label substring")]
        public static JToken Search(JObject p)
        {
            string q = P.Str(p, "query");
            int limit = P.Int(p, "limit", 30);
            var types = p["type"] != null ? new[] { Lookup.DefType(P.Str(p, "type")) } : new[] { typeof(ThingDef), typeof(RecipeDef), typeof(ResearchProjectDef), typeof(TerrainDef), typeof(PawnKindDef), typeof(IncidentDef), typeof(HediffDef), typeof(WorkTypeDef), typeof(JobDef) };
            var arr = new JArray();
            foreach (var t in types)
            foreach (var d in GenDefDatabase.GetAllDefsInDatabaseForDef(t))
            {
                if (arr.Count >= limit) break;
                if ((d.defName?.IndexOf(q, StringComparison.OrdinalIgnoreCase) ?? -1) >= 0 || (d.label?.IndexOf(q, StringComparison.OrdinalIgnoreCase) ?? -1) >= 0)
                    arr.Add(new JObject { ["def"] = d.defName, ["type"] = t.Name, ["label"] = d.label });
            }
            return arr;
        }

        [Rpc("defs.buildable", "{category?: Structure|Production|Furniture|Power|Security|Misc|Floors|...} everything the player can build right now with costs (research done)")]
        public static JToken Buildable(JObject p)
        {
            GameCtl.GameControl.RequirePlaying();
            string? cat = P.OptStr(p, "category");
            var arr = new JArray();
            foreach (var d in DefDatabase<ThingDef>.AllDefs.Where(d => d.BuildableByPlayer && d.IsResearchFinished && d.designationCategory != null).Concat<BuildableDef>(DefDatabase<TerrainDef>.AllDefs.Where(t => t.BuildableByPlayer && t.IsResearchFinished && t.designationCategory != null)))
            {
                if (cat != null && !string.Equals(d.designationCategory.defName, cat, StringComparison.OrdinalIgnoreCase)) continue;
                var stuff = d.MadeFromStuff ? GenStuff.DefaultStuffFor(d) : null;
                arr.Add(new JObject { ["def"] = d.defName, ["label"] = d.label, ["category"] = d.designationCategory.defName, ["cost"] = new JObject(d.CostListAdjusted(stuff).Select(c => new JProperty(c.thingDef.defName, c.count))), ["stuff"] = d.MadeFromStuff, ["size"] = d is ThingDef td ? new JArray(td.size.x, td.size.z) : new JArray(1, 1) });
            }
            return arr;
        }

        [Rpc("defs.work_types", "all work types in priority order with what they cover")]
        public static JToken WorkTypes(JObject p) => new JArray(DefDatabase<WorkTypeDef>.AllDefs.OrderByDescending(w => w.naturalPriority).Select(w => new JObject { ["def"] = w.defName, ["label"] = w.labelShort, ["skills"] = new JArray(w.relevantSkills.Select(s => s.defName)), ["givers"] = string.Join(", ", w.workGiversByPriority.Take(6).Select(g => g.label)) }));
    }
}
