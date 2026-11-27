"""Exercise real Core startup and upgrade from v0.3.0 in disposable config."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

DOMAIN = "media_activity_tracker"
SOURCE = "media_player.runtime_tv"
SECOND = "media_player.runtime_second"
GATE = "binary_sensor.runtime_gate"

async def wait(hass, predicate):
    async with asyncio.timeout(30):
        while not predicate():
            await hass.async_block_till_done()
            await asyncio.sleep(.05)

async def create(hass, entity, name, gate=False):
    from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
    from homeassistant.data_entry_flow import FlowResultType
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    steps = [{"name":name,"entity":entity},{"mode":"playing","logic":"and","condition_entities":[GATE] if gate else []}]
    if gate:
        steps.append({"operator":"equals","value":"on"})
    for data in steps:
        assert result["type"] == FlowResultType.FORM, result
        result = await flow.async_configure(result["flow_id"], data)
    assert result["type"] == FlowResultType.CREATE_ENTRY, result
    entry = result["result"]
    await wait(hass, lambda: entry.state == ConfigEntryState.LOADED)
    return entry

def status(hass, entry):
    from homeassistant.helpers import entity_registry as er
    entity = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, entry.entry_id+"_status")
    assert entity
    return hass.states.get(entity)

async def phase(directory, name, version):
    from homeassistant import bootstrap, loader
    from homeassistant.const import __version__
    from homeassistant.core import HomeAssistant
    assert __version__ == version
    hass = HomeAssistant(str(directory))
    loader.async_setup(hass)
    try:
        config = {"homeassistant":{"name":"Media Activity CI","time_zone":"UTC","latitude":0,"longitude":0,"elevation":0,"unit_system":"metric","currency":"GBP","country":"GB"},"http":{"server_port":8123}}
        assert await bootstrap.async_from_config_dict(config,hass) is not None
        await hass.async_start()
        hass.states.async_set(SOURCE,"playing",{"app_id":"12","app_name":"Netflix"})
        hass.states.async_set(GATE,"on")
        hass.states.async_set(SECOND,"off")
        if name == "old":
            entry = await create(hass,SOURCE,"Runtime TV",True)
            await asyncio.sleep(2)
            hass.states.async_set(SOURCE,"paused",{"app_id":"12","app_name":"Netflix"})
            await wait(hass,lambda: status(hass,entry).state=="paused")
            total=entry.runtime_data.report(1)["periods"]["day"]["seconds"]
            assert total >= 1
            assert await hass.config_entries.async_unload(entry.entry_id)
            (directory/"expected.json").write_text(json.dumps({"id":entry.entry_id,"total":total}))
        else:
            expected=json.loads((directory/"expected.json").read_text())
            entry=hass.config_entries.async_get_entry(expected["id"])
            assert entry is not None
            await wait(hass,lambda: entry.entry_id in hass.data.get(DOMAIN,{}))
            assert entry.runtime_data.report(1)["periods"]["day"]["seconds"] >= expected["total"]
            second=await create(hass,SECOND,"Runtime second")
            assert second.runtime_data.report(1)["periods"]["day"]["seconds"] == 0
            await wait(hass,lambda: status(hass,entry).state=="tracking")
            hass.states.async_set(GATE,"off")
            await wait(hass,lambda: status(hass,entry).state=="condition_not_met")
            assert await hass.config_entries.async_reload(entry.entry_id)
            await wait(hass,lambda: status(hass,entry).state=="condition_not_met")
            assert entry.runtime_data.report(1)["periods"]["day"]["seconds"] >= expected["total"]
            assert await hass.config_entries.async_unload(second.entry_id)
        print("PASS",version,name,flush=True)
    finally:
        await hass.async_stop(force=True)

def main():
    version=sys.argv[1]
    if len(sys.argv)==4:
        asyncio.run(phase(Path(sys.argv[2]),sys.argv[3],version))
        return
    repo=Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="media-activity-ci-") as temp:
        directory=Path(temp)
        (directory/"configuration.yaml").write_text("homeassistant:\nhttp:\n")
        for name, source in (("old",repo/"previous-release/custom_components"),("new",repo/"custom_components")):
            target=directory/"custom_components"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source,target)
            subprocess.run([sys.executable,__file__,version,temp,name],check=True,timeout=240)

if __name__=="__main__":
    main()
