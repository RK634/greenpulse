
let map, nodes={}, graph={}, selectedLocation=null, selectedMarker=null;
let normalVehicleQueues = {};
let normalTrafficVehicles = [];
let movingVehicleEdges = {};
let nodeMarkers={}, signalMarkers={}, signalPhase={}, signalOverride={}, junctionLocks={};
let activeEmergencies={}, colors=["#20f49a","#54b7ff","#ffd45a","#ff6b83","#b578ff"], colorIndex=0;
let speedMultiplier = 1; // Internal fixed speed. Visible speed controls are hidden from dashboard.
let currentPriorityRules = {}, currentSeverityRules = {};

// Demo speed is intentionally slower than real-time so a professor can explain each step.
const EMERGENCY_SEGMENT_MS = 3800;
const EMERGENCY_JUNCTION_SEGMENT_MS = 4000;
const RETURN_SEGMENT_MS = 3600;
const RETURN_JUNCTION_SEGMENT_MS = 3800;
function simMs(ms){ return Math.max(900, Math.round(ms / speedMultiplier)); }

const selectedSpotBox=document.getElementById("selectedSpotBox"), startBtn=document.getElementById("startBtn"), resetBtn=document.getElementById("resetBtn"), sameRouteBtn=document.getElementById("sameRouteBtn"), singleAmbulanceBtn=document.getElementById("singleAmbulanceBtn"), conflictBtn=document.getElementById("conflictBtn"), queueDemoBtn=document.getElementById("queueDemoBtn"), accidentDemoBtn=document.getElementById("accidentDemoBtn"), emergencyTypeEl=document.getElementById("emergencyType"), severityLevelEl=document.getElementById("severityLevel");
const vehicleListEl=document.getElementById("vehicleList"), queueListEl=document.getElementById("queueList"), activeListEl=document.getElementById("activeEmergencies"), logsEl=document.getElementById("activityTimeline")||document.getElementById("logs"), systemStatusEl=document.getElementById("systemStatus"), activeCountEl=document.getElementById("activeCount"), signalOverrideEl=document.getElementById("signalOverride"), latestEtaEl=document.getElementById("latestEta"), kpiTotalEl=document.getElementById("kpiTotal"), kpiQueueEl=document.getElementById("kpiQueue"), kpiCompletedEl=document.getElementById("kpiCompleted"), kpiAvgEl=document.getElementById("kpiAvg"), priorityRulesEl=document.getElementById("priorityRules"), aiRecommendationEl=document.getElementById("aiRecommendation"), conflictCardEl=document.getElementById("conflictCard"), speedSlider=document.getElementById("speedSlider"), speedText=document.getElementById("speedText"), junctionTableEl=document.getElementById("junctionTable"), timelineListEl=document.getElementById("activityTimeline")||document.getElementById("timelineList"), iotStatusEl=document.getElementById("iotStatus"), hospitalStatusEl=document.getElementById("hospitalStatus"), analyticsBoxEl=document.getElementById("analyticsBox"), controlModeEl=document.getElementById("controlMode"), toastContainerEl=document.getElementById("toastContainer");
let iotHealthSnapshot=null;

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function apiGet(u){return await (await fetch(u)).json()}
async function apiPost(u,p={}){return await (await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)})).json()}
function etaFmt(s){s=Math.max(0,Math.round(s));let m=Math.floor(s/60),x=s%60;return m?`${m}m ${x}s`:`${x}s`}
function icon(t){return t==="fire_truck"?"🚒":t==="police"?"🚓":"🚑"}
function severityLabel(s){return (s||"high").charAt(0).toUpperCase()+(s||"high").slice(1)}
function setConflict(message, level="safe"){ if(!conflictCardEl)return; conflictCardEl.className=`decision-box ${level}`; conflictCardEl.innerHTML=message; }
function beep(){let A=window.AudioContext||window.webkitAudioContext;if(!A)return;let a=new A();[0,320,640].forEach(d=>setTimeout(()=>{let o=a.createOscillator(),g=a.createGain();o.type="square";o.frequency.value=880;g.gain.value=.055;o.connect(g);g.connect(a.destination);o.start();o.stop(a.currentTime+.16)},d))}
function divIcon(html, cls="marker-wrap"){return L.divIcon({html:`<div class="${cls}">${html}</div>`,className:"",iconSize:[40,40],iconAnchor:[20,20]})}

function signalHtml(id){
  let n = nodes[id];
  let p = signalPhase[id] || "ALL_RED";
  let o = signalOverride[id];

  let ns = "red";
  let ew = "red";

  if (p === "NS_GREEN") {
    ns = "green";
    ew = "red";
  } else if (p === "NS_YELLOW") {
    ns = "yellow";
    ew = "red";
  } else if (p === "EW_GREEN") {
    ns = "red";
    ew = "green";
  } else if (p === "EW_YELLOW") {
    ns = "red";
    ew = "yellow";
  } else {
    ns = "red";
    ew = "red";
  }

  if (o) {
    ns = "red";
    ew = "red";
    if (o === "NS") ns = "green";
    if (o === "EW") ew = "green";
  }

  let label = "ALL<br>RED";
  if (p === "NS_GREEN") label = "NS<br>GREEN";
  if (p === "NS_YELLOW") label = "NS<br>YELLOW";
  if (p === "EW_GREEN") label = "EW<br>GREEN";
  if (p === "EW_YELLOW") label = "EW<br>YELLOW";
  if (o) label = `EMG<br>${o}`;

  return `<div class="junction-signal"><div class="junction-grid">
    <div class="mini-light north ${ns}"></div><div class="mini-light east ${ew}"></div>
    <div class="junction-center">${label}</div>
    <div class="mini-light west ${ew}"></div><div class="mini-light south ${ns}"></div>
  </div><div class="signal-label ${n.traffic}">${n.traffic.toUpperCase()}</div></div>`;
}
function signalIcon(id){return L.divIcon({html:signalHtml(id),className:"",iconSize:[74,74],iconAnchor:[37,37]})}
function renderSignal(id){if(signalMarkers[id]) signalMarkers[id].setIcon(signalIcon(id))}
function getJunctionTiming(id) {
  const traffic = nodes[id]?.traffic || "medium";

  if (traffic === "heavy") {
    return {
      nsGreen: 7200,
      ewGreen: 7200,
      yellow: 1600,
      allRed: 900
    };
  }

  if (traffic === "medium") {
    return {
      nsGreen: 6000,
      ewGreen: 6000,
      yellow: 1400,
      allRed: 800
    };
  }

  return {
    nsGreen: 4800,
    ewGreen: 4800,
    yellow: 1200,
    allRed: 700
  };
}

function getJunctionOffset(id) {
  // Creates a city-like offset so all junctions do NOT change together.
  const numeric = parseInt(id.replace("j", ""), 10) || 1;
  return (numeric % 4) * 1100 + Math.floor(numeric / 4) * 450;
}

function runSingleJunctionSignal(id) {
  const timing = getJunctionTiming(id);

  async function cycle() {
    while (true) {
      if (!signalOverride[id]) {
        signalPhase[id] = "NS_GREEN";
        renderSignal(id);
      }
      await sleep(timing.nsGreen);

      if (!signalOverride[id]) {
        signalPhase[id] = "NS_YELLOW";
        renderSignal(id);
      }
      await sleep(timing.yellow);

      if (!signalOverride[id]) {
        signalPhase[id] = "ALL_RED";
        renderSignal(id);
      }
      await sleep(timing.allRed);

      if (!signalOverride[id]) {
        signalPhase[id] = "EW_GREEN";
        renderSignal(id);
      }
      await sleep(timing.ewGreen);

      if (!signalOverride[id]) {
        signalPhase[id] = "EW_YELLOW";
        renderSignal(id);
      }
      await sleep(timing.yellow);

      if (!signalOverride[id]) {
        signalPhase[id] = "ALL_RED";
        renderSignal(id);
      }
      await sleep(timing.allRed);
    }
  }

  setTimeout(cycle, getJunctionOffset(id));
}

function startSignals(){
  const ids = Object.keys(nodes).filter(id => nodes[id].type === "junction");

  // Realistic city standard:
  // every junction has its own independent cycle and offset.
  // Not all signals change at the same time.
  ids.forEach((id) => {
    signalPhase[id] = "ALL_RED";
    renderSignal(id);
    runSingleJunctionSignal(id);
  });
}

function initMap(){
  const center=[51.454,7.016];
  const bounds=L.latLngBounds([51.4338,6.9810],[51.4725,7.0445]);

  map=L.map("map",{
    zoomControl:true,
    maxBounds:bounds,
    maxBoundsViscosity:1.0,
    minZoom:13.5,
    maxZoom:16,
    zoomSnap:0.25,
    wheelPxPerZoomLevel:90
  }).setView(center,14.45);

  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",{
    attribution:"Tiles &copy; Esri",
    maxZoom:18
  }).addTo(map);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
    opacity:.22,
    attribution:"&copy; OpenStreetMap",
    maxZoom:18
  }).addTo(map);

  map.setMaxBounds(bounds);

  L.rectangle(bounds,{
    color:"#20f49a",
    weight:2,
    opacity:.72,
    fillColor:"#20f49a",
    fillOpacity:.035,
    dashArray:"8,8"
  }).addTo(map);

  L.marker([51.4712,6.9840],{
    icon:L.divIcon({
      html:`<div class="city-boundary-label">SMART CITY ZONE</div>`,
      className:"",
      iconSize:[160,28],
      iconAnchor:[0,0]
    }),
    interactive:false
  }).addTo(map);

  L.marker([51.4635,7.0160],{
    icon:L.divIcon({
      html:`<div class="city-zone-card">Downtown Control Sector<br>Signals + Emergency Routing Active</div>`,
      className:"",
      iconSize:[190,45],
      iconAnchor:[95,22]
    }),
    interactive:false
  }).addTo(map);

  map.on("click",e=>{
    if(!bounds.contains(e.latlng)){
      alert("Please select a point inside the smart-city operation zone.");
      return;
    }

    selectedLocation={lat:e.latlng.lat,lng:e.latlng.lng,name:`Selected Emergency (${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)})`};
    if(selectedMarker) map.removeLayer(selectedMarker);
    selectedMarker=L.marker([selectedLocation.lat,selectedLocation.lng],{icon:divIcon("🚨","marker-wrap emergency-marker")}).addTo(map);
    selectedSpotBox.textContent=selectedLocation.name + " · snapped to nearest road node";
    startBtn.disabled=false;
  });
}
function drawNetwork(){
  const done=new Set();
  Object.entries(graph).forEach(([a,nb])=>Object.keys(nb).forEach(b=>{
    let key=[a,b].sort().join("-"); if(done.has(key))return; done.add(key);
    let A=nodes[a],B=nodes[b]; if(!A||!B)return;

    L.polyline([[A.lat,A.lng],[B.lat,B.lng]],{
      color:"#0a0f17",
      weight:13,
      opacity:.78,
      lineCap:"round",
      className:"road-glow"
    }).addTo(map);

    L.polyline([[A.lat,A.lng],[B.lat,B.lng]],{
      color:"#3b4652",
      weight:9,
      opacity:.92,
      lineCap:"round"
    }).addTo(map);

    L.polyline([[A.lat,A.lng],[B.lat,B.lng]],{
      color:"#f7d76b",
      weight:1.2,
      opacity:.85,
      dashArray:"5,7",
      lineCap:"round"
    }).addTo(map);
  }));
}
function addMarkers(){
  Object.entries(nodes).forEach(([id,n])=>{
    if(n.type==="junction"){
      signalPhase[id]="NS_GREEN"; signalOverride[id]=null;
      signalMarkers[id]=L.marker([n.lat,n.lng],{icon:signalIcon(id),zIndexOffset:1000}).addTo(map).bindPopup(`<b>${n.name}</b><br>${n.traffic} traffic`);
    } else {
      let ic=n.type==="hospital"?"🏥":n.type==="station"?(n.vehicle_type==="fire_truck"?"🚒":n.vehicle_type==="police"?"🚓":"🚑"):"📍";
      nodeMarkers[id]=L.marker([n.lat,n.lng],{icon:divIcon(ic)}).addTo(map).bindPopup(`<b>${n.name}</b>`);
    }
  });
}
function approachDir(prev,next){
  let dx=next.lng-prev.lng, dy=next.lat-prev.lat;
  return Math.abs(dx)>Math.abs(dy)?"EW":"NS";
}
function isRoadConnected(fromId, toId) {
  return graph[fromId] && graph[fromId][toId] !== undefined;
}

function validateRoadPath(path) {
  for (let i = 0; i < path.length - 1; i++) {
    if (!isRoadConnected(path[i], path[i + 1])) {
      console.error("Invalid road path:", path[i], "→", path[i + 1]);
      return false;
    }
  }
  return true;
}

async function waitGreen(nodeId, prev) {
  if (!nodes[nodeId] || nodes[nodeId].type !== "junction") return;

  const dir = approachDir(nodes[prev], nodes[nodeId]);
  const requiredPhase = `${dir}_GREEN`;

  // Normal traffic must obey the city signal. During emergency override,
  // normal vehicles wait so the corridor stays clear.
  while (signalOverride[nodeId] || signalPhase[nodeId] !== requiredPhase) {
    await sleep(180);
  }

  await sleep(260);
}

function clearJunctionTraffic(nodeId, dir) {
  // Visual clearance: nearby normal vehicles are pushed slightly away from the
  // junction when an emergency corridor opens. This makes the demo look like
  // traffic is creating space for the emergency vehicle.
  const n = nodes[nodeId];
  if (!n) return;

  normalTrafficVehicles.forEach(v => {
    const ll = v.marker.getLatLng();
    const dLat = ll.lat - n.lat;
    const dLng = ll.lng - n.lng;
    const near = Math.abs(dLat) < 0.0015 && Math.abs(dLng) < 0.0015;
    if (!near) return;

    const push = dir === "NS" ? 0.0011 : 0.0013;
    const target = dir === "NS"
      ? [ll.lat, ll.lng + (dLng >= 0 ? push : -push)]
      : [ll.lat + (dLat >= 0 ? push : -push), ll.lng];

    v.marker.setLatLng(target);
  });
}
function startAmbientTraffic() {
  // Busy city traffic: all normal vehicles use only connected road edges and
  // must obey four-way signal phases before crossing a junction.
  const routes = [
    ["🚗", ["j1", "j2", "j3", "j4", "police_east", "j4", "j8", "j7", "j6", "j10", "hospital", "j10", "j6", "j7", "j8", "j4", "j3", "j2", "j1"], 5200],
    ["🚙", ["amb_south", "j13", "j14", "j15", "j16", "j12", "j8", "j7", "j6", "j10", "j14", "amb_south"], 5600],
    ["🚕", ["amb_north", "j1", "j5", "j9", "j13", "amb_south", "j13", "j9", "j5", "j1", "amb_north"], 6000],
    ["🚘", ["j5", "j6", "j10", "hospital", "j10", "j6", "j5"], 5400],
    ["🚗", ["j9", "j10", "j11", "j12", "j8", "j7", "j6", "j10", "j9"], 5800],
    ["🚙", ["j2", "j6", "j10", "j14", "amb_south", "j14", "j10", "j6", "j2"], 6200],
    ["🚐", ["j4", "j3", "j2", "j6", "j10", "j14", "j15", "j16", "j12", "j8", "j4"], 6400],
    ["🚚", ["fire_west", "j5", "j6", "j7", "j8", "police_east", "j8", "j7", "j6", "j5", "fire_west"], 7000],
    ["🚗", ["j13", "j9", "j5", "j1", "amb_north", "j1", "j5", "j9", "j13"], 6100],
    ["🚕", ["j16", "j15", "j11", "j7", "j3", "j4", "j8", "j12", "j16"], 6300],
    ["🚲", ["j2", "j6", "j10", "j11", "j15", "j14", "j10", "j6", "j2"], 7600],
    ["🚲", ["j3", "j7", "j11", "j15", "j16", "j12", "j8", "j7", "j3"], 8000],
    ["🚗", ["j6", "j7", "j11", "j10", "j6", "j5", "j9", "j10", "j6"], 5000],
    ["🚙", ["j10", "j11", "j15", "j14", "j10", "j9", "j5", "j6", "j10"], 5300],
    ["🚕", ["j7", "j8", "j12", "j11", "j7", "j6", "j2", "j3", "j7"], 5700],
    ["🚘", ["j2", "j6", "j7", "j3", "j2", "j1", "j5", "j6", "j2"], 5500],
    ["🚐", ["j14", "j10", "j11", "j15", "j14", "j13", "j9", "j10", "j14"], 5900],
    ["🚚", ["j8", "j7", "j11", "j12", "j8", "j4", "j3", "j7", "j8"], 6800]
  ];

  routes.forEach((r, idx) => setTimeout(() => spawn(r[0], r[1], "marker-wrap normal-marker", r[2]), idx * 260));

  spawn("🚶", ["j6", "j7", "j6", "j5", "j6"], "marker-wrap person-marker", 9000);
  spawn("🚶", ["j10", "j11", "j10", "j9", "j10"], "marker-wrap person-marker", 9400);
  spawn("🚶", ["j2", "j3", "j2", "j1", "j2"], "marker-wrap person-marker", 9200);
}
function spawn(ic, path, cls, d) {
  if (!validateRoadPath(path)) {
    return;
  }

  let marker = L.marker([nodes[path[0]].lat, nodes[path[0]].lng], {
    icon: divIcon(ic, cls),
    zIndexOffset: cls.includes("normal") ? 500 : 300
  }).addTo(map);

  const trafficRef = { marker, path, currentIndex: 0, icon: ic };
  if (cls.includes("normal")) normalTrafficVehicles.push(trafficRef);

  let i = 0;

  (async function loop() {
    while (true) {
      let next = (i + 1) % path.length;

      if (!isRoadConnected(path[i], path[next])) {
        i = 0;
        await sleep(500);
        continue;
      }

      await waitGreen(path[next], path[i]);
      await animateMarker(marker, nodes[path[i]], nodes[path[next]], d);

      i = next;
      trafficRef.currentIndex = i;
      await sleep(150 + Math.random() * 300);
    }
  })();
}
async function animateMarker(marker,a,b,d){
  const steps=36;
  for(let i=1;i<=steps;i++){
    let t=i/steps;
    marker.setLatLng([a.lat+(b.lat-a.lat)*t, a.lng+(b.lng-a.lng)*t]);
    await sleep(d/steps);
  }
}
function routeLine(route, color) {
  let group = L.layerGroup().addTo(map);

  for (let i = 0; i < route.length - 1; i++) {
    let from = route[i];
    let to = route[i + 1];

    L.polyline(
      [
        [from.lat, from.lng],
        [to.lat, to.lng]
      ],
      {
        color,
        weight: 7,
        opacity: 0.92,
        dashArray: "8,8"
      }
    ).addTo(group);
  }

  return group;
}

async function refreshQueue(){
  if (!queueListEl) return;

  let queue = await apiGet("/api/queue");
  queueListEl.innerHTML = "";

  if (!queue.length) {
    queueListEl.innerHTML = `<div class="queue-card"><div>No waiting emergency in queue.</div></div>`;
    return;
  }

  queue.forEach(q => {
    queueListEl.innerHTML += `
      <div class="queue-card">
        <strong>Queue #${q.id} · ${q.emergency_type.toUpperCase()}</strong>
        <div>Severity: ${severityLabel(q.severity)} · Priority Score: ${q.priority_score || q.priority}</div>
        <div>Spot: ${q.spot_name}</div>
        <div>Status: ${q.status}</div>
        <div>Created: ${q.created_at}</div>
      </div>
    `;
  });
}

async function runQueuedDispatches(items){
  if (!items || !items.length) return;

  for (const item of items) {
    await refreshQueue();
    await refreshVehicles();
    await refreshLogs();
    simulate(item);
    await sleep(800);
  }
}

async function updateVehicleStatus(id,status){
  const r=await apiPost("/api/vehicle/status",{vehicle_id:id,status});
  if(r.error){ alert(r.error); return; }
  await refreshVehicles(); await refreshLogs(); await refreshDashboard();
}
async function refreshVehicles(){
  let v=await apiGet("/api/vehicles"); vehicleListEl.innerHTML="";
  v.forEach(x=>vehicleListEl.innerHTML+=`<div class="vehicle-card"><strong>${x.name}</strong><div>${x.vehicle_type.replace("_"," ").toUpperCase()}</div><div>${x.location_name}</div><span class="badge ${x.status}">${x.status}</span><div class="vehicle-actions"><button class="mini-btn" onclick="updateVehicleStatus('${x.id}','available')">Available</button><button class="mini-btn" onclick="updateVehicleStatus('${x.id}','maintenance')">Maintenance</button><button class="mini-btn" onclick="updateVehicleStatus('${x.id}','offline')">Offline</button></div></div>`);
}
async function refreshLogs(){
  if(!logsEl) return;
  let logs=await apiGet("/api/events");
  logsEl.innerHTML = logs.length ? "" : `<div class="timeline-item">No activity yet. Run a demo scenario.</div>`;
  logs.forEach(l=>logsEl.innerHTML+=`<div class="timeline-item"><strong>${l.created_at}</strong><span>#${l.emergency_id||"-"} · ${l.event_type.toUpperCase()}</span><p>${l.message}</p></div>`);
}
function updateActive(){
  let list=Object.values(activeEmergencies).sort((a,b)=>(b.priorityScore||b.priority)-(a.priorityScore||a.priority));
  activeCountEl.textContent=list.length; activeListEl.innerHTML=list.length?"":`<div class="emergency-card"><div>No active emergency now.</div></div>`;
  systemStatusEl.textContent=list.length?"Emergency Running":"Normal City Mode"; if(!list.length)signalOverrideEl.textContent="None";
  list.forEach(e=>activeListEl.innerHTML+=`<div class="emergency-card"><strong>#${e.id} · ${e.vehicleName}</strong><div>${e.type.toUpperCase()} · ${severityLabel(e.severity)} · Score ${e.priorityScore||e.priority}</div><div>${e.spotName}</div><div class="progress-track"><span style="width:${e.progress}%"></span></div><div>Progress: ${e.progress}% · ETA left: ${etaFmt(e.etaLeft)}</div></div>`);
}
async function sigLog(eid,n,action,sec=0){await apiPost("/api/signal-log",{emergency_id:eid,junction_name:n.name,action,traffic:n.traffic,seconds:sec});await refreshLogs();}
async function preClear(em,n,prev){
  let eid = em.id;
  let pri = em.priority;
  let dir = approachDir(prev,n);

  // Same junction + same direction = shared green corridor.
  // Different direction = conflict, so priority decides who passes first.
  while (junctionLocks[n.id] && junctionLocks[n.id].eid !== eid) {
    const lock = junctionLocks[n.id];

    if (lock.dir === dir) {
      setConflict(`<strong>Shared Green Corridor</strong><br>${n.name}: two emergency vehicles are using the same direction (${dir}). No priority conflict needed.`, "safe");
      await sigLog(eid,n,"shared",1);
      break;
    }

    if (lock.priority > pri || lock.priority === pri) {
      setConflict(`<strong>Priority Conflict Detected</strong><br>${n.name}: different direction conflict. Current route (${lock.dir}) keeps green; lower/equal priority waits briefly.`, "warning");
      await sigLog(eid,n,"priority_wait",2);
      await sleep(700);
      continue;
    }

    // Higher-priority emergency gets the conflicting junction direction.
    setConflict(`<strong>Priority Override</strong><br>${n.name}: different direction conflict. Higher priority route (${dir}) receives the green signal first.`, "danger");
    break;
  }

  junctionLocks[n.id] = {eid, priority: pri, dir};

  // Clear normal traffic around the junction before the emergency vehicle arrives.
  clearJunctionTraffic(n.id, dir);

  // If the emergency direction is already green, do not make the vehicle wait.
  if (signalOverride[n.id] === dir) {
    signalOverrideEl.textContent = `${n.name}: shared ${dir} emergency green`;
    clearJunctionTraffic(n.id, dir);
    renderSignal(n.id);
    return;
  }

  // If normal city cycle is already green for this emergency direction, pass immediately.
  if (!signalOverride[n.id] && signalPhase[n.id] === `${dir}_GREEN`) {
    signalOverride[n.id] = dir;
    renderSignal(n.id);
    signalOverrideEl.textContent = `${n.name}: ${dir} already green, emergency passes`;
    clearJunctionTraffic(n.id, dir);
    await sigLog(eid,n,"green",0);
    return;
  }

  // Real city emergency preemption:
  // current signal goes yellow, then all-red safety clearance, then route-direction green.
  signalOverride[n.id] = null;

  if (signalPhase[n.id] === "NS_GREEN") {
    signalPhase[n.id] = "NS_YELLOW";
  } else if (signalPhase[n.id] === "EW_GREEN") {
    signalPhase[n.id] = "EW_YELLOW";
  } else {
    signalPhase[n.id] = "ALL_RED";
  }

  renderSignal(n.id);
  signalOverrideEl.textContent = `${n.name}: preemption yellow`;
  await sigLog(eid,n,"pre_clear",n.pre_clear_seconds);
  await sleep(320);

  signalPhase[n.id] = "ALL_RED";
  renderSignal(n.id);
  signalOverrideEl.textContent = `${n.name}: all-red clearance`;
  await sleep(260);

  signalOverride[n.id] = dir;
  renderSignal(n.id);
  signalOverrideEl.textContent = `${n.name}: ${dir} emergency green`;
  clearJunctionTraffic(n.id, dir);
  await sigLog(eid,n,"green",n.pre_clear_seconds);

  // Very small driver reaction only after a signal change.
  await sleep(120);
}

async function release(eid,n){
  await sigLog(eid,n,"passed");
  await sleep(250);

  if (junctionLocks[n.id]?.eid === eid) {
    delete junctionLocks[n.id];

    signalOverride[n.id] = null;
    signalPhase[n.id] = "ALL_RED";
    renderSignal(n.id);
  }

  await sigLog(eid,n,"reset");
  signalOverrideEl.textContent = "None";

  // The independent standard city cycle for this junction continues automatically.
}

async function ambulanceReturnToHospital(result, marker, emergencyId) {
  if (!result.hospital_return_route || !result.hospital_return_route.length) return;

  const returnRoute = result.hospital_return_route;
  const hospitalLine = routeLine(returnRoute, "#ff4d64");

  if (activeEmergencies[emergencyId]) {
    activeEmergencies[emergencyId].spotName = "Transporting patient to hospital";
    activeEmergencies[emergencyId].progress = 0;
    updateActive();
  }

  signalOverrideEl.textContent = "Ambulance returning to hospital";
  await refreshLogs();

  const total = returnRoute.length - 1;
  let eta = 40;

  for (let i = 1; i < returnRoute.length; i++) {
    const nxt = returnRoute[i];
    const prev = returnRoute[i - 1];
    const p0 = Math.round(((i - 1) / total) * 100);
    const p1 = Math.round((i / total) * 100);

    if (nxt.type === "junction") {
      await preClear(activeEmergencies[emergencyId], nxt, prev);
    }

    await animateEmergency(marker, prev, nxt, simMs(nxt.type === "junction" ? RETURN_JUNCTION_SEGMENT_MS : RETURN_SEGMENT_MS), emergencyId, eta, p0, p1);
    eta = Math.max(0, eta - 2.6);

    if (nxt.type === "junction") {
      await release(emergencyId, nxt);
    }
  }

  hospitalLine.remove();
  signalOverrideEl.textContent = "Hospital transfer completed";
}

async function simulate(r){
  beep();
  let eid=r.emergency_id, route=r.route, color=colors[colorIndex++%colors.length];
  let line=routeLine(route,color);
  let veh=L.marker([route[0].lat,route[0].lng],{icon:divIcon(icon(r.vehicle.vehicle_type),"marker-wrap emergency-marker"),zIndexOffset:2000}).addTo(map);
  activeEmergencies[eid]={id:eid,priority:r.priority,priorityScore:r.priority_score,severity:r.severity,type:r.emergency_type,vehicleName:r.vehicle.name,spotName:r.spot.name,progress:0,etaLeft:r.vehicle.eta_seconds,vehicle:veh,line};
  latestEtaEl.textContent=etaFmt(r.vehicle.eta_seconds); await refreshVehicles(); await refreshQueue(); await refreshLogs(); await refreshDashboard(); updateActive();
  let total=route.length-1, eta=r.vehicle.eta_seconds;
  for(let i=1;i<route.length;i++){
    let nxt=route[i],prev=route[i-1],p0=Math.round((i-1)/total*100),p1=Math.round(i/total*100);
    if(nxt.type==="junction") await preClear(activeEmergencies[eid],nxt,prev);
    await animateEmergency(veh,prev,nxt,simMs(nxt.type==="junction"?EMERGENCY_JUNCTION_SEGMENT_MS:EMERGENCY_SEGMENT_MS),eid,eta,p0,p1);
    eta=Math.max(0,eta-2.8);
    if(nxt.type==="junction") await release(eid,nxt);
  }
  await ambulanceReturnToHospital(r, veh, eid);
  let completeResult = await apiPost("/api/complete",{emergency_id:eid});
  await refreshLogs(); await refreshVehicles(); await refreshQueue(); await runQueuedDispatches(completeResult.dispatched_from_queue); await sleep(1200);
  if(activeEmergencies[eid]){map.removeLayer(activeEmergencies[eid].vehicle); activeEmergencies[eid].line.remove(); delete activeEmergencies[eid];}
  updateActive();
}
async function animateEmergency(marker,a,b,d,eid,eta,p0,p1){
  const steps=38;
  for(let i=1;i<=steps;i++){
    let t=i/steps;
    marker.setLatLng([a.lat+(b.lat-a.lat)*t,a.lng+(b.lng-a.lng)*t]);
    if(activeEmergencies[eid]){
      let e=activeEmergencies[eid]; e.progress=Math.round(p0+(p1-p0)*t); e.etaLeft=Math.max(0,eta-(d/1000)*t); latestEtaEl.textContent=etaFmt(e.etaLeft); updateActive();
    }
    await sleep(d/steps);
  }
}
function showNotification(title, message, type="safe"){
  if(!toastContainerEl) return;
  const toast=document.createElement("div");
  toast.className=`toast ${type}`;
  toast.innerHTML=`<strong>${title}</strong><span>${message}</span>`;
  toastContainerEl.appendChild(toast);
  setTimeout(()=>{toast.style.opacity="0";toast.style.transform="translateY(10px)";},4200);
  setTimeout(()=>toast.remove(),4900);
}
function trackIotHealthChanges(devices){
  if(!Array.isArray(devices)) return;
  const current={};
  devices.forEach(d=>current[d.device]=d.status);
  if(iotHealthSnapshot){
    devices.forEach(d=>{
      const old=iotHealthSnapshot[d.device];
      if(old && old!==d.status){
        const bad=["offline","fault","error","inactive"].some(x=>String(d.status).toLowerCase().includes(x));
        showNotification("IoT device health changed", `${d.device}: ${old} → ${d.status}`, bad?"danger":"warning");
      }
    });
  }
  iotHealthSnapshot=current;
}

async function refreshDashboard(){
  const d = await apiGet("/api/dashboard");
  if(kpiTotalEl){ kpiTotalEl.textContent=d.metrics.total_emergencies; kpiQueueEl.textContent=d.metrics.waiting; kpiCompletedEl.textContent=d.metrics.completed; kpiAvgEl.textContent=d.metrics.avg_response_text; }
  if(priorityRulesEl){
    priorityRulesEl.innerHTML = Object.entries(d.priority_rules).map(([k,v])=>`<div><strong>${k.toUpperCase()}</strong><span>Base ${v}</span></div>`).join("") + Object.entries(d.severity_rules).map(([k,v])=>`<div><strong>${k.toUpperCase()}</strong><span>+${v}</span></div>`).join("");
  }
  if(aiRecommendationEl) aiRecommendationEl.innerHTML = `<strong>Recommendation:</strong><br>${d.recommendation}`;
  if(junctionTableEl){
    let activeJ = {};
    Object.values(signalOverride).forEach(()=>{});
    junctionTableEl.innerHTML = `<table><thead><tr><th>Junction</th><th>Traffic</th><th>Signal</th><th>Override</th></tr></thead><tbody>${d.junctions.map(j=>`<tr><td>${j.name}</td><td>${j.traffic}</td><td>${signalOverride[j.id] ? signalOverride[j.id]+" GREEN" : (signalPhase[j.id]||"Normal")}</td><td>${signalOverride[j.id]?"Yes":"No"}</td></tr>`).join("")}</tbody></table>`;
  }
  if(timelineListEl){
    timelineListEl.innerHTML = d.timeline.length ? d.timeline.map(t=>`<div class="timeline-item"><strong>${t.created_at}</strong><span>#${t.emergency_id||"-"} · ${t.event_type.toUpperCase()}</span><p>${t.message}</p></div>`).join("") : `<div class="timeline-item">No activity yet. Run a demo scenario.</div>`;
  }
  trackIotHealthChanges(d.iot);
  if(analyticsBoxEl){
    const types = Object.entries(d.by_type).map(([k,v])=>`${k}: ${v}`).join(" · ") || "No emergency data yet";
    analyticsBoxEl.innerHTML = `<div>Total handled: <strong>${d.metrics.total_emergencies}</strong></div><div>Available vehicles: <strong>${d.metrics.available_vehicles}</strong></div><div>Busy vehicles: <strong>${d.metrics.busy_vehicles}</strong></div><div>Time saved estimate: <strong>${d.metrics.estimated_time_saved}</strong></div><div>${types}</div>`;
  }
}

async function updateHospitalCapacity(name, beds, icu){
  const r = await apiPost("/api/hospital/capacity", {hospital:name, beds:beds, icu:icu});
  if(r.error){ alert(r.error); return; }
  await refreshDashboard();
  await refreshLogs();
}

async function createNow(type, loc){
  let r=await apiPost("/api/emergency",{emergency_type:type,lat:loc.lat,lng:loc.lng,spot_name:loc.name,severity:loc.severity || (severityLevelEl?severityLevelEl.value:"high")});
  if(r.error){alert(r.error);return}
  if(r.queued){
    alert(r.message);
    await refreshQueue();
    await refreshLogs();
    return;
  }
  simulate(r);
}
function createEmergency(){if(selectedLocation) createNow(emergencyTypeEl.value, selectedLocation);}
function markScenarioSpot(loc){
  if(selectedMarker) map.removeLayer(selectedMarker);
  selectedMarker=L.marker([loc.lat,loc.lng],{icon:divIcon("🚨","marker-wrap emergency-marker")}).addTo(map);
  selectedLocation=loc; selectedSpotBox.textContent=loc.name; startBtn.disabled=false;
}
function singleAmbulanceDemo(){ const loc={lat:51.4496,lng:7.0108,name:"Single Ambulance Emergency",severity:"high"}; markScenarioSpot(loc); createNow("medical",loc); }
function sameRouteDemo(){
  const loc={lat:51.4480,lng:7.0320,name:"Same Route Demo Emergency",severity:"high"};
  markScenarioSpot(loc); setConflict("<strong>Same Route Demo Started</strong><br>Vehicles using the same direction can share the green corridor.", "safe");
  createNow("medical",loc);
  setTimeout(()=>createNow("police",loc),2200);
}
function conflictDemo(){
  const a={lat:51.4566,lng:7.0106,name:"Conflict Demo Central Cross - Medical",severity:"critical"};
  const b={lat:51.4564,lng:7.0241,name:"Conflict Demo Business Cross - Fire",severity:"critical"};
  markScenarioSpot(a); setConflict("<strong>Conflict Demo Started</strong><br>Different emergency directions will activate priority logic.", "warning");
  createNow("medical",a);
  setTimeout(()=>createNow("fire",b),1600);
}
function queueDemo(){
  const locs=[
    {lat:51.4480,lng:7.0320,name:"Queue Demo Medical 1",severity:"high"},
    {lat:51.4490,lng:7.0210,name:"Queue Demo Medical 2",severity:"critical"},
    {lat:51.4550,lng:7.0120,name:"Queue Demo Medical 3",severity:"medium"}
  ];
  markScenarioSpot(locs[0]); locs.forEach((loc,i)=>setTimeout(()=>createNow("medical",loc),i*900));
}
function accidentScenario(){
  const loc={lat:51.4478,lng:7.0107,name:"Road Accident Multi-Response",severity:"critical"};
  markScenarioSpot(loc);
  createNow("accident",loc);
  setTimeout(()=>createNow("police",{...loc,name:"Police Support for Accident"}),1300);
}
async function reset(){
  Object.values(activeEmergencies).forEach(e=>{map.removeLayer(e.vehicle);map.removeLayer(e.line)});
  activeEmergencies={}; junctionLocks={}; Object.keys(signalOverride).forEach(k=>{signalOverride[k]=null; renderSignal(k)});
  await apiPost("/api/reset"); await refreshVehicles(); await refreshQueue(); await refreshLogs(); await refreshDashboard(); updateActive(); latestEtaEl.textContent="-"; setConflict("No conflict detected.", "safe"); await refreshDashboard();
}
async function init(){
  initMap();
  let d=await apiGet("/api/map"); nodes=d.nodes; graph=d.graph; currentPriorityRules=d.priority; currentSeverityRules=d.severity;
  drawNetwork(); addMarkers(); startSignals(); startAmbientTraffic();
  await refreshVehicles(); await refreshQueue(); await refreshLogs(); await refreshDashboard(); updateActive();
  startBtn.onclick=createEmergency; resetBtn.onclick=reset; sameRouteBtn.onclick=sameRouteDemo; if(singleAmbulanceBtn)singleAmbulanceBtn.onclick=singleAmbulanceDemo; if(conflictBtn)conflictBtn.onclick=conflictDemo; if(queueDemoBtn)queueDemoBtn.onclick=queueDemo; if(accidentDemoBtn)accidentDemoBtn.onclick=accidentScenario; if(speedSlider)speedSlider.oninput=()=>{speedMultiplier=parseFloat(speedSlider.value); speedText.textContent=speedMultiplier<0.9?"Slow":speedMultiplier>1.2?"Fast":"Normal"};
  setInterval(refreshLogs,6000); setInterval(refreshVehicles,7000); setInterval(refreshQueue,5000); setInterval(refreshDashboard,4500);
}
init();
