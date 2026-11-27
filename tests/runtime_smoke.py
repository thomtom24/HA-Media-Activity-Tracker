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

async def safety_checks(hass, entry):
    """Use real HA Store, actual filesystem errors and real HA permission policies."""
    from copy import deepcopy
    from types import SimpleNamespace
    from homeassistant.auth.models import Group, User
    from homeassistant.auth.permissions.models import PermissionLookup
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from custom_components.media_activity_tracker import websocket_report
    tracker = entry.runtime_data
    path = Path(tracker.store.path)
    snapshot = deepcopy(tracker.engine.storage())
    await tracker.store.async_save(snapshot)
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0
    original = path.with_name(path.name + ".test-original")
    path.rename(original)
    path.mkdir()
    try:
        await tracker.store.async_save(snapshot)
        assert tracker.store.write_failed
    finally:
        path.rmdir()
        original.rename(path)
    await tracker.store.async_save(snapshot)
    assert not tracker.store.write_failed
    assert tracker.store.last_success
    assert json.loads(path.read_text())["data"] == snapshot
    assert path.stat().st_mode & 0o077 == 0
    registry = er.async_get(hass)
    status_id = registry.async_get_entity_id("sensor", DOMAIN, entry.entry_id+"_status")
    lookup = PermissionLookup(registry, dr.async_get(hass))
    for allowed_ids, permitted in (([tracker.source], False), ([status_id], False),
                                  ([tracker.source, status_id], True)):
        group = Group(name="Restricted runtime test", policy={"entities":{"entity_ids":{entity:{"read":True} for entity in allowed_ids}}})
        user = User(name="Restricted", perm_lookup=lookup, groups=[group], is_active=True)
        result = []
        connection = SimpleNamespace(user=user, send_error=lambda *args: result.append(("error",args)),
                                     send_result=lambda *args: result.append(("result",args)))
        websocket_report(hass, connection, {"id":1,"entry_id":entry.entry_id,"days":1})
        assert result and result[0][0] == ("result" if permitted else "error"), result

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
            await safety_checks(hass, entry)
            hass.config_entries.async_update_entry(entry, options={**entry.options, "mode":"power"})
            assert await hass.config_entries.async_reload(entry.entry_id)
            assert entry.runtime_data.engine.data["mixed_history"]
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
