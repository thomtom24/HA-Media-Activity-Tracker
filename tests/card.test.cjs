const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const registry=new Map(),context={HTMLElement:class{},customElements:{get:k=>registry.get(k),define:(k,v)=>registry.set(k,v)},window:{}};
vm.createContext(context);
vm.runInContext(fs.readFileSync("custom_components/media_activity_tracker/www/ha-media-activity-card.js","utf8"),context);
test("registers card and editor",()=>{assert.ok(registry.has("media-activity-card"));assert.ok(registry.has("media-activity-card-editor"));});
test("escapes untrusted app names",()=>assert.equal(vm.runInContext('esc("<script>")',context),"&lt;script&gt;"));
test("formats duration",()=>assert.equal(vm.runInContext("duration(9000)",context),"2h 30m"));
test("avoids divide by zero",()=>assert.equal(vm.runInContext("pct(1,0)",context),null));
test("renders empty charts",()=>assert.match(vm.runInContext("chart([], {})",context),/<svg/));

test("duplicate module does not register card or editor twice",()=>{
 const oldCard=registry.get("media-activity-card"),oldEditor=registry.get("media-activity-card-editor");
 const second={HTMLElement:class{},customElements:context.customElements,window:context.window};
 vm.createContext(second);
 vm.runInContext(fs.readFileSync("custom_components/media_activity_tracker/www/ha-media-activity-card.js","utf8"),second);
 assert.equal(registry.get("media-activity-card"),oldCard);
 assert.equal(registry.get("media-activity-card-editor"),oldEditor);
 assert.equal(context.window.customCards.filter(c=>c.type==="media-activity-card").length,1);
});

test("protects spreadsheet formulas including leading whitespace",()=>{
 assert.equal(vm.runInContext('csvSafe("  =1+1")',context),"'  =1+1");
 assert.equal(vm.runInContext('csvSafe("Netflix")',context),"Netflix");
});
test("normalises unsupported card settings",()=>{
 assert.equal(vm.runInContext('normalise({period:"bad",trend:"bad",target:-20}).period',context),"day");
 assert.equal(vm.runInContext('normalise({target:-20}).target',context),0);
});
test("stable tracker identity survives a sensor rename",()=>{
 assert.equal(vm.runInContext('trackerEntity({states:{"sensor.new":{attributes:{tracker_entry_id:"abc"}}}},{entity:"sensor.old",tracker_entry_id:"abc"})',context),"sensor.new");
});
