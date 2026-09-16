using System;
using System.Linq;
using RimBridge.Engine;
using Xunit;

namespace RimBridge.Tests
{
    public class PathParserTests
    {
        [Fact]
        public void PlainRoot_WithSegmentsAndIndexer()
        {
            var p = PathParser.Parse("Find.CurrentMap.mapPawns.FreeColonists[2].health");

            Assert.Equal("", p.RootTag);
            Assert.Equal(new[] { "Find" }, p.RootArgs);
            Assert.False(p.RootIsCall);
            Assert.Empty(p.RootIndexers);
            Assert.Equal(4, p.Segments.Count);
            Assert.Equal(new[] { "CurrentMap", "mapPawns", "FreeColonists", "health" }, p.Segments.Select(s => s.Name));
            Assert.Equal(new[] { "2" }, p.Segments[2].Indexers);
            Assert.All(p.Segments, s => Assert.False(s.IsCall));
            Assert.Empty(p.Segments[0].Indexers);
            Assert.Empty(p.Segments[3].Indexers);
        }

        [Fact]
        public void ThingTag_WithIdArg()
        {
            var p = PathParser.Parse("Thing:Human1234.needs.mood.CurLevel");

            Assert.Equal("Thing", p.RootTag);
            Assert.Equal(new[] { "Human1234" }, p.RootArgs);
            Assert.Equal(new[] { "needs", "mood", "CurLevel" }, p.Segments.Select(s => s.Name));
        }

        [Fact]
        public void DefTag_WithTwoArgs()
        {
            var p = PathParser.Parse("Def:ThingDef:Steel.BaseMarketValue");

            Assert.Equal("Def", p.RootTag);
            Assert.Equal(new[] { "ThingDef", "Steel" }, p.RootArgs);
            Assert.Single(p.Segments);
            Assert.Equal("BaseMarketValue", p.Segments[0].Name);
        }

        [Fact]
        public void TypeTag_AllowsDotsInArg_NoSegments()
        {
            var p = PathParser.Parse("Type:RimWorld.GenConstruct.CanPlaceBlueprintAt");

            Assert.Equal("Type", p.RootTag);
            Assert.Equal(new[] { "RimWorld.GenConstruct.CanPlaceBlueprintAt" }, p.RootArgs);
            Assert.Empty(p.Segments);
        }

        [Fact]
        public void NonTypeTag_DoesNotSwallowDots()
        {
            // Dots are only part of the root arg for Type; elsewhere they start a segment.
            var p = PathParser.Parse("Def:ThingDef:Steel.label");
            Assert.Equal(new[] { "ThingDef", "Steel" }, p.RootArgs);
            Assert.Equal("label", Assert.Single(p.Segments).Name);
        }

        [Fact]
        public void SegmentCall_WithIndexer()
        {
            var p = PathParser.Parse("Map.listerThings.ThingsOfDef()[0]");

            Assert.Equal(new[] { "Map" }, p.RootArgs);
            Assert.Equal(2, p.Segments.Count);
            var last = p.Segments[1];
            Assert.Equal("ThingsOfDef", last.Name);
            Assert.True(last.IsCall);
            Assert.Equal(new[] { "0" }, last.Indexers);
            Assert.False(p.Segments[0].IsCall);
        }

        [Fact]
        public void QuotedIndexer_PreservesSpaces()
        {
            var p = PathParser.Parse("Map.zoneManager.AllZones[\"rice 1\"]");

            var last = p.Segments.Last();
            Assert.Equal("AllZones", last.Name);
            Assert.Equal(new[] { "rice 1" }, last.Indexers);
        }

        [Fact]
        public void SingleQuotedIndexer_AlsoWorks()
        {
            var p = PathParser.Parse("Map.zoneManager.AllZones['rice 1']");
            Assert.Equal(new[] { "rice 1" }, p.Segments.Last().Indexers);
        }

        [Fact]
        public void QuotedRootArg()
        {
            var p = PathParser.Parse("Pawn:\"Jen Smith\".skills");

            Assert.Equal("Pawn", p.RootTag);
            Assert.Equal(new[] { "Jen Smith" }, p.RootArgs);
            Assert.Equal("skills", Assert.Single(p.Segments).Name);
        }

        [Fact]
        public void RootCall_SetsRootIsCall()
        {
            var p = PathParser.Parse("Map()");
            Assert.True(p.RootIsCall);
            Assert.Empty(p.Segments);
        }

        [Fact]
        public void SegmentCall_SetsIsCallOnSegment_NotRoot()
        {
            var p = PathParser.Parse("Map.foo()");

            Assert.False(p.RootIsCall);
            var seg = Assert.Single(p.Segments);
            Assert.Equal("foo", seg.Name);
            Assert.True(seg.IsCall);
            Assert.Empty(seg.Indexers);
        }

        [Fact]
        public void RootIndexers_AreCaptured()
        {
            var p = PathParser.Parse("Things[3].def");
            Assert.Equal(new[] { "3" }, p.RootIndexers);
            Assert.Equal("def", Assert.Single(p.Segments).Name);
        }

        [Fact]
        public void MultipleIndexers_OnOneSegment()
        {
            var p = PathParser.Parse("Map.grid[1][2]");
            Assert.Equal(new[] { "1", "2" }, p.Segments[0].Indexers);
        }

        [Fact]
        public void TagIsCaseInsensitive_AndNormalized()
        {
            var p = PathParser.Parse("thing:Human1.def");
            Assert.Equal("Thing", p.RootTag);
            Assert.Equal(new[] { "Human1" }, p.RootArgs);
        }

        [Fact]
        public void WhitespaceIsTrimmed()
        {
            var p = PathParser.Parse("  Find.CurrentMap  ");
            Assert.Equal(new[] { "Find" }, p.RootArgs);
            Assert.Equal("CurrentMap", Assert.Single(p.Segments).Name);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void EmptyPath_Throws(string path)
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse(path));
        }

        [Fact]
        public void NullPath_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse(null!));
        }

        [Fact]
        public void DoubleDot_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Find..x"));
        }

        [Fact]
        public void TrailingDot_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Find.x."));
        }

        [Fact]
        public void UnterminatedIndexer_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Find.x[2"));
        }

        [Fact]
        public void UnterminatedQuotedIndexer_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Map.AllZones[\"rice"));
        }

        [Fact]
        public void UnterminatedQuotedRootArg_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Pawn:\"Jen.skills"));
        }

        [Fact]
        public void UnexpectedCharacter_Throws()
        {
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Find x"));
        }

        [Fact]
        public void CallWithArguments_IsRejected()
        {
            // Only "()" is allowed in paths; args go through engine.call.
            Assert.Throws<ArgumentException>(() => PathParser.Parse("Map.ThingsOfDef(Def:ThingDef:Steel)"));
        }

        [Fact]
        public void SegmentToString_RoundTrips()
        {
            var p = PathParser.Parse("Map.listerThings.ThingsOfDef()[0]");
            Assert.Equal("ThingsOfDef()[0]", p.Segments[1].ToString());
        }
    }
}
