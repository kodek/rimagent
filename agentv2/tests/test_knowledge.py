from __future__ import annotations

import json

import httpx
from test_runner import Script

from agentv2.knowledge import INDEX, build_index, page_file, scrape_wiki, search, wikitext_to_markdown
from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model
from agentv2.wake import Wake

PAGES = {
    "Raid": "{{Infobox main|type = Event|points = 35}}\n'''Raids''' happen when [[Pirate|pirates]] attack.\n\nRaid points grow with colony wealth.",
    "Rice plant": "{{Infobox main|growdays = 3}}\nRice grows fast in a [[Growing zone|growing zone]].",
    "Steel": "Steel is a metal. You mine it from compacted steel.",
}


def fake_wiki(requests: list[dict[str, str]]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests.append(params)
        if params.get("list") == "allpages":
            if "apcontinue" in params:
                return httpx.Response(200, json={"query": {"allpages": [{"title": "Steel"}]}})
            return httpx.Response(200, json={"query": {"allpages": [{"title": "Raid"}, {"title": "Rice plant"}]}, "continue": {"apcontinue": "S"}})
        pages = [{"title": t, "revisions": [{"slots": {"main": {"content": PAGES[t]}}}]} for t in params["titles"].split("|")]
        return httpx.Response(200, json={"query": {"pages": pages}})

    return httpx.MockTransport(handle)


async def test_scrape_writes_pages_once_and_the_index_ranks_them(tmp_path):
    requests: list[dict[str, str]] = []
    async with httpx.AsyncClient(transport=fake_wiki(requests)) as client:
        assert await scrape_wiki(client, tmp_path / "wiki", log=lambda _: None) == 3
        assert await scrape_wiki(client, tmp_path / "wiki", log=lambda _: None) == 0
    raid = page_file(tmp_path / "wiki", "Raid").read_text()
    assert raid.startswith("# Raid\n\ntype: Event\npoints: 35\n\n") and "Raids happen when pirates attack." in raid
    assert sum(1 for r in requests if r.get("prop") == "revisions") == 1
    assert build_index(tmp_path, log=lambda _: None) == 3
    hits = search(tmp_path / INDEX, "how do raid points work")
    assert hits[0]["title"] == "Raid" and hits[0]["path"] == "wiki/Raid.md"
    assert [h["title"] for h in search(tmp_path / INDEX, "growing rice")][:1] == ["Rice plant"]
    assert search(tmp_path / INDEX, "?!") == []


def test_wikitext_keeps_the_infobox_numbers():
    text = wikitext_to_markdown("Wall", "{{Stats|hp = 300}}\n{{Other|x = 1}}\nA [[wall]] <div>blocks</div>.{{#ask: x\n|y}}")
    assert text == "# Wall\n\nhp: 300\n\nA wall blocks.\n"


async def test_the_director_searches_the_wiki(settings, bridge, bus, tmp_path):
    knowledge = settings.knowledge_dir = tmp_path / "knowledge"
    (knowledge / "wiki").mkdir(parents=True)
    page_file(knowledge / "wiki", "Raid").write_text(wikitext_to_markdown("Raid", PAGES["Raid"]))
    script = Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        script.responses = [code("await kb_search(query='raid')"), call("end_turn", {"notes": "no index yet"})]
        await rt.runner.step(Wake("first", False))
        assert "agentv2 seed" in json.dumps([str(p) for p in script.received[-1][-1].parts])
        build_index(knowledge, log=lambda _: None)
        script.responses = [code("await kb_search(query='raid points')"), call("end_turn", {"notes": "read"})]
        await rt.runner.step(Wake("second", False))
        assert "Raid points grow with colony wealth" in str(script.received[-1][-1].parts)
