/* Media Activity Card 0.3.0 — MIT */
const defaults={period:"day",trend:"90",live:true,summary:true,apps:true,recent:true,trends:true,insights:true,heatmap:true,export:true,target:0};
const colors=["#5b8def","#e36272","#35ae99","#e8a340","#a180dc","#45a5c7","#d27fb4","#8195a5"];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const csvSafe=s=>/^[\s\uFEFF]*[=+\-@]|^[\t\r\n]/.test(String(s))?"\'"+s:String(s);
const normalise=c=>({...defaults,...c,period:["day","week","month","year"].includes(c.period)?c.period:"day",trend:["30","90","365"].includes(String(c.trend))?String(c.trend):"90",target:Math.max(0,Math.min(1440,Number(c.target)||0))});
const formatTimestamp=(value,tz)=>{try{return new Date(value).toLocaleString(undefined,tz?{timeZone:tz}:{});}catch{return new Date(value).toLocaleString();}};
const sum=o=>Object.values(o||{}).reduce((a,b)=>a+b,0);
const duration=s=>{let m=Math.floor(Math.max(0,s||0)/60);return (m>=60?Math.floor(m/60)+"h ":"")+(m%60)+"m"};
const color=k=>colors[Array.from(k).reduce((a,c)=>(a*31+c.charCodeAt(0))>>>0,0)%colors.length];
const ranked=o=>Object.entries(o||{}).sort((a,b)=>b[1]-a[1]);
const pct=(a,b)=>b?Math.round((a-b)/b*100):null;
const date=d=>new Date(d+"T12:00:00").toLocaleDateString(undefined,{month:"short",day:"numeric"});
const style=":host{display:block;color:var(--primary-text-color)}*{box-sizing:border-box}ha-card{padding:18px;overflow:hidden}h2,h3,p{margin:0}h2{font-size:20px}h3{font-size:14px;margin-bottom:12px}.row,header{display:flex;align-items:center;justify-content:space-between;gap:10px}.muted{color:var(--secondary-text-color);font-size:12px;line-height:1.4}.section{padding:16px 0;border-top:1px solid var(--divider-color);margin-top:14px}.live{display:flex;gap:12px;align-items:center;padding:16px 0}.app-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:12px;color:white;font-size:22px;font-weight:bold}.tabs{display:flex;gap:4px;padding:4px;background:var(--secondary-background-color);border-radius:10px;margin:8px 0 16px;flex-wrap:wrap}button{font:inherit;color:inherit;cursor:pointer;border:1px solid var(--divider-color);background:transparent;border-radius:8px;padding:8px}button:focus-visible{outline:2px solid var(--primary-color)}.tabs button{flex:1;border:0;font-size:12px}.tabs button[aria-pressed=true]{background:var(--card-background-color,var(--ha-card-background));color:var(--primary-color);font-weight:bold;box-shadow:0 1px 4px #0002}.kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.kpi{padding:12px;background:var(--secondary-background-color);border-radius:12px}.number{font-size:clamp(19px,5vw,27px);font-weight:650;margin:5px 0;font-variant-numeric:tabular-nums}.bar{height:8px;background:var(--divider-color);border-radius:8px;overflow:hidden;margin:6px 0 12px}.bar span{display:block;height:100%;border-radius:8px}.swatch{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:6px}.chart{width:100%;height:auto;max-width:720px;max-height:260px;margin-inline:auto;display:block}.chart text{fill:var(--secondary-text-color);font-size:10px}.gridline{stroke:var(--divider-color)}.legend{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:11px}.heat{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}.heat div{text-align:center;border-radius:6px;padding:8px 2px;font-size:11px}.insight{display:flex;justify-content:space-between;gap:10px;margin-bottom:9px;font-size:13px}.insight span:last-child{text-align:right;font-weight:600}.status{font-size:12px;color:var(--secondary-text-color)}.active{color:#35ae99}.appname{overflow-wrap:anywhere;min-width:0}.appvalue{white-space:nowrap}footer{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}@media(max-width:480px){.heat div{font-size:9px;padding:6px 0}.kpi{padding:8px}.kpis{gap:6px}.appvalue{font-size:12px}}dialog{color:var(--primary-text-color);background:var(--card-background-color,var(--ha-card-background));border:1px solid var(--divider-color);border-radius:18px;width:min(840px,96vw);max-height:90dvh;overflow:auto;padding:20px}dialog::backdrop{background:#0009}";
const tabs=(values,current,kind)=>'<div class="tabs" role="group">'+values.map(([id,label])=>'<button data-'+kind+'="'+id+'" aria-pressed="'+(id===current)+'">'+label+'</button>').join("")+"</div>";
const kpi=(label,value,sub)=>'<div class="kpi"><div class="muted">'+esc(label)+'</div><div class="number">'+esc(value)+'</div><div class="muted">'+esc(sub)+'</div></div>';
const section=(name,body)=>'<div class="section"><h3>'+esc(name)+'</h3>'+body+'</div>';
const line=(label,val)=>'<div class="insight"><span class="muted">'+esc(label)+'</span><span>'+esc(val)+'</span></div>';
function chart(rows,apps,group=0){
 let data=rows;
 if(group){data=[];for(let i=0;i<rows.length;i+=group){let r=rows.slice(i,i+group);data.push({date:r[0].date,apps:{total:r.reduce((s,d)=>s+sum(d.apps),0)/r.length}});}}
 const max=Math.max(3600,...data.map(r=>sum(r.apps))),step=300/Math.max(1,data.length),base=110;
 let out='<svg class="chart" viewBox="0 0 340 140" role="img" aria-label="'+(group?"Average daily activity trend":"Daily activity by app")+'">';
 for(let i=0;i<=3;i++){let y=base-i*28;out+='<line class="gridline" x1="32" x2="334" y1="'+y+'" y2="'+y+'"/><text x="28" y="'+(y+3)+'" text-anchor="end">'+(max*i/3/3600).toFixed(1)+'h</text>';}
 const points=[];
 data.forEach((r,i)=>{let y=base,x=32+(i+.5)*step;
 if(group){y-=sum(r.apps)*84/max;points.push([x,y]);out+='<circle cx="'+x+'" cy="'+y+'" r="3" fill="var(--primary-color)"><title>'+esc(r.date+": "+duration(sum(r.apps)))+'</title></circle>';}
 else ranked(r.apps).forEach(([k,v])=>{let ht=v*84/max;y-=ht;out+='<rect x="'+(x-step*.35)+'" y="'+y+'" width="'+step*.7+'" height="'+ht+'" fill="'+color(k)+'"><title>'+esc(r.date+" "+(apps[k]||k)+": "+duration(v))+'</title></rect>';});
 if(i%Math.ceil(data.length/6)===0||i===data.length-1)out+='<text x="'+x+'" y="129" text-anchor="middle">'+esc(r.date.slice(5))+'</text>';
 });
 if(group)out+='<polyline points="'+points.map(p=>p.join(",")).join(" ")+'" stroke="var(--primary-color)" fill="none" stroke-width="2.5" stroke-linejoin="round"/>';
 return out+"</svg>";
}
class MediaActivityCard extends HTMLElement{
 constructor(){super();this.attachShadow({mode:"open"});this.request=0;this.shadowRoot.addEventListener("click",e=>this.handleClick(e));}
 setConfig(c){if(!c||typeof c.entity!=="string"||!c.entity.startsWith("sensor."))throw new Error("Select a Media Activity Tracker status sensor");this.config=normalise(c);this.period=this.config.period;this.trend=this.config.trend;this.data=null;this.error="";this.loading=false;this.request++;this.render();this.refresh();}
 set hass(h){this._hass=h;const v=h.states[this.config?.entity],sig=v?.attributes?.tracker_entry_id+":"+v?.last_changed+":"+v?.state;if(sig!==this.sig){this.sig=sig;this.refresh();}}
 connectedCallback(){this.timer=setInterval(()=>this.refresh(),30000);this.refresh();}
 disconnectedCallback(){clearInterval(this.timer);this.request++;this.loading=false;}
 getCardSize(){return 8;}
 static getConfigElement(){return document.createElement("media-activity-card-editor");}
 static getStubConfig(hass){return {entity:Object.keys(hass.states).find(k=>hass.states[k].attributes.tracker_entry_id)||""};}
 async refresh(){if(!this.isConnected||!this.config||!this._hass||this.loading)return;const entry=this._hass.states[this.config.entity]?.attributes?.tracker_entry_id;if(!entry){this.data=null;this.error="Select an available Tracking status sensor.";this.render();return;}const id=++this.request;this.loading=true;try{const d=await this._hass.callWS({type:"media_activity_tracker/report",entry_id:entry,days:366});if(id!==this.request)return;if(d.schema!==1)throw new Error("Unsupported tracker API");this.data=d;this.error="";}catch(e){if(id===this.request){this.data=null;this.error=e.message||"Tracker unavailable";}}finally{if(id===this.request){this.loading=false;this.render();}}}
 content(full=false){
 const d=this.data,c=this.config;if(!d)return '<p class="muted" role="status">'+esc(this.error||"Loading media activity…")+"</p>"+(this.error?'<button data-action="retry">Retry</button>':"");
 const p=d.periods[this.period]||d.periods.day,top=ranked(p.apps),total=p.seconds,delta=p.comparison_seconds===null?null:pct(p.comparison_seconds??total,p.previous_seconds),mode={playing:"Playing time",app:"App activity",power:"Powered-on time"}[d.mode]||"Activity",apps=d.apps;
 const recorded=d.history.filter(r=>!d.started||r.date>=(d.recorded_since||d.started.slice(0,10))),busy=recorded.reduce((a,b)=>!a||sum(b.apps)>sum(a.apps)?b:a,null),avg7=d.periods["7"].seconds/Math.max(1,d.periods["7"].observed_days??7),avg30=d.periods["30"].seconds/Math.max(1,d.periods["30"].observed_days??30),change=d.mixed_history?null:pct(avg7,avg30);
 let s='<header><div><h2>'+esc(c.title||d.name)+'</h2><div class="muted">'+esc(mode)+" · Since "+esc((d.recorded_since||new Date(d.started).toLocaleDateString()))+'</div></div><div class="status '+(d.active?"active":"")+'">'+esc(d.active?"● Tracking":({"condition_not_met":"Conditions unmet","source_unavailable":"Source unavailable","source_off":"Source off","app_excluded":"App excluded","paused":"Paused","buffering":"Buffering","source_not_active":"Not active","circular_condition":"Circular condition"}[d.reason]||d.state))+'</div></header>';
 if(d.mixed_history)s+='<p role="status" class="muted">History includes different sources or tracking modes; period comparisons are disabled.</p>';if(d.storage_error)s+='<p role="alert">History save failed; check Home Assistant storage and logs.</p>';if(this.error)s+='<p role="alert" class="muted">Last known data — '+esc(this.error)+'</p>';
 if(c.live||full)s+='<div class="live"><div class="app-icon" style="background:'+color(d.app||"?")+'">'+esc((d.app||"?").slice(0,1).toUpperCase())+'</div><div><strong>'+esc(d.app)+'</strong><div class="muted">'+esc(d.active?"Current session · "+duration(d.session_seconds):d.state==="paused"?"Paused · "+duration(d.session_seconds):"Not tracking")+'</div></div></div>';
 s+=tabs([["day","Today"],["week","Week"],["month","Month"],["year","Year"]],this.period,"period");
 if(c.summary||full){s+='<div class="kpis">'+kpi(d.mixed_history?"Recorded activity (mixed)":mode,duration(total),delta===null?"No comparable prior activity":(delta>0?"+":"")+delta+"% vs equivalent completed time")+kpi("Daily average",duration(total/Math.max(1,p.observed_days??p.days)),(p.observed_days??p.days)+" recorded calendar "+((p.observed_days??p.days)===1?"day":"days"))+kpi("Sessions",p.sessions,"Daily session count")+kpi("Longest session",duration(p.longest),"Single-day contribution")+'</div>';if(Number(c.target)>0){let target=Number(c.target)*60,today=d.periods.day.seconds;s+=section("Daily target",line(duration(today),duration(target))+'<div class="bar"><span style="width:'+Math.min(100,today/target*100)+'%;background:var(--primary-color)"></span></div>');}}
 if(c.apps||full)s+=section("Activity by application",top.length?top.map(([k,v])=>'<div class="row"><span class="appname"><i class="swatch" style="background:'+color(k)+'"></i>'+esc(apps[k]||k)+'</span><span class="appvalue">'+duration(v)+' <span class="muted">'+Math.round(v/total*100)+'%</span></span></div><div class="bar"><span style="width:'+(v/total*100)+'%;background:'+color(k)+'"></span></div>').join(""):'<p class="muted">No recorded activity.</p>');
 if(c.recent||full){const rows=recorded.slice(-7),keys=[...new Set(rows.flatMap(r=>Object.keys(r.apps)))];s+=section("Last 7 days",chart(rows,apps)+'<div class="legend">'+keys.map(k=>'<span><i class="swatch" style="background:'+color(k)+'"></i>'+esc(apps[k]||k)+'</span>').join("")+'</div>');}
 if((c.recent||full)&&this.period!=="day"){let count=p.days;let rows=recorded.slice(-count);s+=section(this.period==="year"?"Year-to-date trend":"Selected period daily breakdown",chart(rows,apps,this.period==="year"?14:0));}
 if(c.trends||full)s+=section("Long-term usage trend",tabs([["30","30 days"],["90","90 days"],["365","12 months"]],this.trend,"trend")+chart(recorded.slice(-Number(this.trend)),apps,this.trend==="365"?14:this.trend==="90"?7:1)+'<p class="muted">Average daily activity per interval</p>');
 if(c.heatmap||full){let w=Array.from({length:7},(_,i)=>({name:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i],total:0,n:0}));recorded.slice(-90).forEach(r=>{let i=(new Date(r.date+"T12:00:00").getDay()+6)%7;w[i].total+=sum(r.apps);w[i].n++;});let max=Math.max(1,...w.map(x=>x.total/Math.max(1,x.n)));s+=section("Typical activity by weekday",'<div class="heat">'+w.map(x=>'<div style="background:color-mix(in srgb,var(--primary-color) '+(8+55*x.total/Math.max(1,x.n)/max)+'%,transparent)">'+x.name+'<br><strong>'+duration(x.total/Math.max(1,x.n))+'</strong></div>').join("")+'</div><p class="muted">Last 90 recorded days</p>');}
 if(c.heatmap||full){
 const hours=Array.from({length:7},()=>Array(24).fill(0)),days=Array(7).fill(0);
 recorded.slice(-90).forEach(r=>{let i=(new Date(r.date+"T12:00:00").getDay()+6)%7;days[i]++;Object.entries(r.hours||{}).forEach(([h,v])=>{if(Number(h)>=0&&Number(h)<24)hours[i][Number(h)]+=v;});});
 const max=Math.max(1,...hours.flatMap((row,i)=>row.map(v=>v/Math.max(1,days[i]))));
 let svg='<svg class="chart" viewBox="0 0 340 113" role="img" aria-label="Average activity by weekday and local hour">';
 hours.forEach((row,i)=>{svg+='<text x="1" y="'+(20+i*12)+'">'+["M","T","W","T","F","S","S"][i]+'</text>';row.forEach((v,h)=>{let a=v/Math.max(1,days[i]);svg+='<rect x="'+(15+h*13)+'" y="'+(11+i*12)+'" width="11" height="10" rx="2" fill="var(--primary-color)" opacity="'+(a?0.2+0.8*a/max:0.05)+'"><title>'+esc(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][i]+" "+String(h).padStart(2,"0")+":00 · "+duration(a)+" average")+'</title></rect>';});});
 [0,6,12,18,23].forEach(h=>svg+='<text x="'+(15+h*13)+'" y="107" text-anchor="middle">'+String(h).padStart(2,"0")+'</text>');
 s+=section("Typical time of day",svg+'</svg><p class="muted">Average local-hour activity over the last 90 days; darker cells mean more activity.</p>');
 }
 if(c.insights||full)s+=section("Insights",line("Most used app",top.length?apps[top[0][0]]||top[0][0]:"None")+line("Busiest recorded day",busy&&sum(busy.apps)>0?date(busy.date)+" · "+duration(sum(busy.apps)):"None")+line("7-day average",duration(avg7))+line("30-day average",duration(avg30))+line("90-day average",duration(d.periods["90"].seconds/Math.max(1,d.periods["90"].observed_days??90)))+line("Recent trend",change===null?"No activity":(change>0?"+":"")+change+"% vs 30-day average"));
 if(full)s+=section("Recent sessions",d.sessions.slice(-Math.min(500,this.sessionLimit||30)).reverse().map(x=>line(formatTimestamp(x.start,d.timezone)+" · "+(apps[x.app]||x.app),duration(x.seconds))).join("")+(d.sessions.length>(this.sessionLimit||30)?'<button data-action="more-sessions">Show more sessions</button>':""));
 return s+'<footer>'+(full?'<button data-action="close">Close</button>':'<button data-action="details">Full statistics</button>')+(c.export||full?'<button data-action="export">Export CSV</button>':'')+'</footer>';
 }
 render(){
   if(!this.config)return;
   // Keep the dialog node alive during periodic refreshes.
   if(!this.shadowRoot.querySelector("ha-card")){
     this.shadowRoot.innerHTML="<style>"+style+"</style><ha-card></ha-card><dialog></dialog>";
   }
   const main=this.shadowRoot.querySelector("ha-card"),next=this.content();if(main.innerHTML!==next){const active=this.shadowRoot.activeElement,focus=active?.dataset?{...active.dataset}:null;main.innerHTML=next;if(focus){const target=[...main.querySelectorAll("button")].find(b=>Object.entries(focus).every(([k,v])=>b.dataset[k]===v));target?.focus({preventScroll:true});}}
   const dialog=this.shadowRoot.querySelector("dialog");
   if(dialog.open){const next=this.content(true),scroll=dialog.scrollTop;if(dialog.innerHTML!==next){dialog.innerHTML=next;dialog.scrollTop=scroll;}}
 }
 handleClick(e){
   const b=e.composedPath().find(node=>node instanceof HTMLButtonElement);
   if(!b)return;
   const {period,trend,action}=b.dataset;
   if(!period&&!trend&&!action)return;
   e.stopPropagation();
   if(period){this.period=period;this.render();}
   else if(trend){this.trend=trend;this.render();}
   else if(action==="details"){const dialog=this.shadowRoot.querySelector("dialog");dialog.innerHTML=this.content(true);if(!dialog.open)dialog.showModal();}
   else if(action==="close")this.shadowRoot.querySelector("dialog").close();
   else if(action==="export")this.exportData();
   else if(action==="retry")this.refresh();
   else if(action==="more-sessions"){this.sessionLimit=Math.min(500,(this.sessionLimit||30)+30);this.render();}
 }
 async exportData(){try{const entry=this._hass.states[this.config.entity].attributes.tracker_entry_id,d=await this._hass.callWS({type:"media_activity_tracker/report",entry_id:entry,days:3660}),safe=csvSafe,rows=[["date","application","seconds"],...d.history.flatMap(r=>Object.entries(r.apps).map(([k,v])=>[r.date,safe(d.apps[k]||k),Math.round(v)]))],csv=rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(",")).join("\n"),url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"})),a=document.createElement("a");a.href=url;a.download="media-activity.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){this.error="Export failed: "+(e.message||"unknown error");this.render();}}
}
class MediaActivityEditor extends HTMLElement{
 constructor(){super();this.attachShadow({mode:"open"});this.shadowRoot.addEventListener("change",e=>this.handleChange(e));}
 setConfig(c){this.config=normalise(c||{});this.render();}
 set hass(h){this._hass=h;const list=Object.keys(h.states).filter(k=>h.states[k].attributes.tracker_entry_id).join("|");if(list!==this.list){this.list=list;this.render();}}
 render(){if(!this.config||!this._hass)return;const entities=Object.entries(this._hass.states).filter(([,v])=>v.attributes.tracker_entry_id),opts=(values,key)=>values.map(([k,v])=>'<option value="'+esc(k)+'" '+(k===this.config[key]?"selected":"")+'>'+esc(v)+'</option>').join("");
 this.shadowRoot.innerHTML='<style>:host{display:block;color:var(--primary-text-color)}label{display:block;margin:12px 0}select,input:not([type=checkbox]){width:100%;padding:10px;background:var(--secondary-background-color);color:inherit;border:1px solid var(--divider-color);border-radius:6px;box-sizing:border-box}input[type=checkbox]{margin-right:8px}</style><label>Tracker status entity<select name="entity"><option value="">Select</option>'+opts(entities.map(([k,v])=>[k,v.attributes.friendly_name||k]),"entity")+'</select></label><label>Title<input name="title" value="'+esc(this.config.title||"")+'"></label><label>Default period<select name="period">'+opts([["day","Today"],["week","Week"],["month","Month"],["year","Year"]],"period")+'</select></label><label>Default trend<select name="trend">'+opts([["30","30 days"],["90","90 days"],["365","12 months"]],"trend")+'</select></label><label>Daily target in minutes (0 = disabled)<input name="target" type="number" min="0" max="1440" value="'+Number(this.config.target||0)+'"></label>'+[["live","Live status"],["summary","Summary"],["apps","App breakdown"],["recent","Recent daily chart"],["trends","Long-term trends"],["heatmap","Weekday heatmap"],["insights","Insights"],["export","Export CSV"]].map(([k,v])=>'<label><input type="checkbox" name="'+k+'" '+(this.config[k]?"checked":"")+'>'+v+'</label>').join("");
 }
 handleChange(e){
   const t=e.target;if(!t.name)return;
   this.config={...this.config,[t.name]:t.type==="checkbox"?t.checked:t.type==="number"?Math.max(0,Math.min(1440,Number(t.value)||0)):t.value};
   this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this.config},bubbles:true,composed:true}));
 }
}
if(!customElements.get("media-activity-card"))customElements.define("media-activity-card",MediaActivityCard);
if(!customElements.get("media-activity-card-editor"))customElements.define("media-activity-card-editor",MediaActivityEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="media-activity-card"))window.customCards.push({type:"media-activity-card",name:"Media Activity Card",description:"Per-device media activity and trends",preview:true});
