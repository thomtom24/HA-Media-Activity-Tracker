const { chromium }=require("playwright");
const assert=require("node:assert/strict");
const path=require("node:path");
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000},acceptDownloads:true});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.setContent('<main style="width:1500px"></main>');
  await page.addScriptTag({path:path.resolve("custom_components/media_activity_tracker/www/ha-media-activity-card.js")});
  await page.evaluate(()=>{
   const day={seconds:300,apps:{"id:12":300},sessions:1,longest:300,days:1,previous_seconds:0};
   const periods={day,week:{...day,seconds:900,apps:{"id:12":900},days:7},month:{...day,days:26},year:{...day,days:330},"7":day,"30":day,"90":day,"365":day};
   const report={schema:1,started:"2026-11-26T12:00:00Z",name:"Test TV",state:"playing",mode:"playing",app:"Netflix",active:true,session_seconds:300,reason:"tracking",apps:{"id:12":"Netflix"},periods,history:[{date:"2026-11-26",apps:day.apps,hours:{"12":300}}],sessions:[]};
   const hass={states:{"sensor.test":{state:"tracking",last_changed:"1",attributes:{tracker_entry_id:"test",friendly_name:"Test tracker"}}},callWS:async()=>report};
   window.testHass=hass;
   const card=document.createElement("media-activity-card");card.setConfig({entity:"sensor.test"});document.querySelector("main").append(card);card.hass=hass;
   const editor=document.createElement("media-activity-card-editor");editor.setConfig({entity:"sensor.test"});editor.hass=hass;document.body.append(editor);
   editor.addEventListener("config-changed",e=>window.lastConfig=e.detail.config);
  });
  const card=page.locator("media-activity-card"), week=card.locator('ha-card button[data-period="week"]');
  await week.waitFor();await week.click();assert.equal(await week.getAttribute("aria-pressed"),"true");assert.match(await card.locator("ha-card .number").first().innerText(),/15m/);
  const trend=card.locator('ha-card button[data-trend="30"]');await trend.click();assert.equal(await trend.getAttribute("aria-pressed"),"true");
  await card.locator('ha-card button[data-action="details"]').click();assert.equal(await card.locator("dialog").evaluate(d=>d.open),true);
  await card.locator('dialog button[data-period="month"]').click();assert.equal(await card.locator('dialog button[data-period="month"]').getAttribute("aria-pressed"),"true");
  await card.locator('dialog button[data-action="close"]').click();assert.equal(await card.locator("dialog").evaluate(d=>d.open),false);
  const download=page.waitForEvent("download");await card.locator('ha-card button[data-action="export"]').click();assert.equal((await download).suggestedFilename(),"media-activity.csv");
  const chart=await card.locator("ha-card .chart").first().boundingBox();assert.ok(chart.width<=721&&chart.height<=261);
  await page.locator('media-activity-card-editor select[name="period"]').selectOption("month");assert.equal(await page.evaluate(()=>window.lastConfig.period),"month");
  await page.setViewportSize({width:375,height:800});
  await page.evaluate(()=>{document.querySelector("main").style.width="100%";});
  const narrow=await card.boundingBox();assert.ok(narrow.width<=375);
  await card.locator('ha-card button[data-period="day"]').focus();
  await page.evaluate(()=>document.querySelector("media-activity-card").render());
  assert.equal(await card.evaluate(c=>c.shadowRoot.activeElement.dataset.period),"day");
  await card.locator('ha-card button[data-action="details"]').click();
  await page.evaluate(()=>{const c=document.querySelector("media-activity-card");c.hass={...window.testHass,callWS:async()=>{throw new Error("unauthorized");}};return c.refresh();});
  await card.locator('dialog button[data-action="retry"]').waitFor();
  await card.locator('dialog button[data-action="close"]').click();
  await card.locator('ha-card button[data-action="retry"]').waitFor();
  assert.doesNotMatch(await card.innerText(),/Netflix/);
  assert.deepEqual(errors,[]);
  console.log("Browser interactions, export, editor and responsive chart sizing passed");
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
