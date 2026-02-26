const statusText = document.getElementById("statusText");
const modePill   = document.getElementById("modePill");
const statusTags = document.getElementById("statusTags");
const retryRow   = document.getElementById("retryRow");
const retryBtn   = document.getElementById("retryBtn");
const helpText   = document.getElementById("helpText");

const pickers     = document.getElementById("pickers");
const schoolInput = document.getElementById("schoolInput");
const majorInput  = document.getElementById("majorInput");
const schoolSug   = document.getElementById("schoolSug");
const majorSug    = document.getElementById("majorSug");
const loadBtn     = document.getElementById("loadBtn");
const clearBtn    = document.getElementById("clearBtn");

const results     = document.getElementById("results");
const parsedArea  = document.getElementById("parsedArea");
const finalBtn    = document.getElementById("finalBtn");
const copyBtn     = document.getElementById("copyBtn");
const finalOut    = document.getElementById("finalOut");

let indexJson = null;

let campuses = [];     // [{id, code, pretty, years, latestYear, yearMap}]
let fuseCampus = null;

// selected
let selectedCampus = "";
let selectedYear = "";
let majorsForCampus = []; // [{id, pretty, path}]
let fuseMajors = null;

loadBtn.classList.add("btnGrow");
finalBtn.classList.add("btnGrow");

if (!clearBtn.querySelector("span")) {
  clearBtn.innerHTML = `<span>${clearBtn.textContent.trim() || "Clear"}</span>`;
}
clearBtn.classList.add("btnClearX");

if (!copyBtn.classList.contains("ghost")) copyBtn.classList.add("ghost");

function ensureSuggestUI(inputEl) {
  if (inputEl.parentElement?.classList?.contains("suggestWrap")) return;

  const wrap = document.createElement("div");
  wrap.className = "suggestWrap";
  inputEl.parentNode.insertBefore(wrap, inputEl);
  wrap.appendChild(inputEl);

  const box = document.createElement("div");
  box.className = "suggestBox";
  wrap.appendChild(box);

  return box;
}

const schoolBox = ensureSuggestUI(schoolInput);
const majorBox  = ensureSuggestUI(majorInput);

function showBox(box, show) {
  if (!box) return;
  box.classList.toggle("show", !!show);
}

function renderSuggestions(box, items, onPick) {
  if (!box) return;

  box.innerHTML = "";
  if (!items.length) {
    showBox(box, false);
    return;
  }

  for (const it of items) {
    const row = document.createElement("div");
    row.className = "suggestItem";

    const left = document.createElement("div");
    left.className = "suggestLeft";

    const title = document.createElement("div");
    title.className = "suggestTitle";
    title.textContent = it.title;

    const sub = document.createElement("div");
    sub.className = "suggestSub";
    sub.textContent = it.sub || "";

    left.appendChild(title);
    left.appendChild(sub);

    const meta = document.createElement("div");
    meta.className = "suggestMeta";
    meta.textContent = it.meta || "";

    row.appendChild(left);
    if (it.meta) row.appendChild(meta);

    row.addEventListener("click", () => onPick(it));
    box.appendChild(row);
  }

  showBox(box, true);
}

function closeAllSuggest() {
  showBox(schoolBox, false);
  showBox(majorBox, false);
}

document.addEventListener("click", (e) => {
  const inSchool = schoolInput.parentElement.contains(e.target);
  const inMajor  = majorInput.parentElement.contains(e.target);
  if (!inSchool && !inMajor) closeAllSuggest();
});

function setTags(list){
  statusTags.innerHTML = "";
  for (const t of list){
    const el = document.createElement("span");
    el.className = "tag";
    el.innerHTML = `<i></i>${t}`;
    statusTags.appendChild(el);
  }
  statusTags.style.display = "flex";
}

function clearUI(){
  selectedCampus = "";
  selectedYear = "";
  majorsForCampus = [];
  fuseMajors = null;

  schoolInput.value = "";
  majorInput.value = "";
  delete majorInput.dataset.majorId;

  schoolSug.textContent = "";
  majorSug.textContent = "Pick a campus first to see major suggestions.";

  parsedArea.innerHTML = "";
  finalOut.textContent = "";
  results.style.display = "none";
  closeAllSuggest();
}

function buildCampusIndex(campusList){
  campuses = campusList || [];
  fuseCampus = new Fuse(
    campuses.map(c => ({ ...c, label: c.id })),
    { keys:["code","pretty","id","label"], threshold:0.35 }
  );
}

async function loadIndex(){
  modePill.textContent = "loading…";
  statusText.textContent = "Loading data/index.json…";
  retryRow.style.display = "none";
  helpText.style.display = "none";
  statusTags.style.display = "none";

  try{
    const res = await fetch("./data/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    indexJson = await res.json();

    const campusList = indexJson?.campuses || [];
    buildCampusIndex(campusList);

    if (!campuses.length) throw new Error("index.json loaded, but contains 26 campuses.");

    modePill.textContent = "ready";
    statusText.textContent = "Data loaded";
    //setTags([`${campuses.length}   campuses `, " ", " mode: GitHub Pages (static index)"]);

    pickers.style.display = "block";
    clearUI();
  } catch (e){
    modePill.textContent = "failed";
    statusText.textContent = "Could not load data/index.json.";
    retryRow.style.display = "flex";
    helpText.style.display = "block";
    helpText.textContent =
      `Fix: Make sure ./data/index.json exists and you are serving via GitHub Pages or a local server.
Error: ${String(e.message || e)}`;
  }
}

function updateSchoolSuggestions(){
  const q = schoolInput.value.trim();
  if (!q || !fuseCampus) {
    schoolSug.textContent = "";
    renderSuggestions(schoolBox, [], ()=>{});
    return;
  }

  const hits = fuseCampus.search(q, { limit: 6 });

  const items = hits.map(h => {
    const c = h.item;
    return {
      title: c.code || (c.id.split("_")[0] || c.id),
      sub: c.pretty || c.id.replaceAll("_"," "),
      meta: "campus",
      value: c.id
    };
  });

  renderSuggestions(schoolBox, items, (it) => {
    schoolInput.value = it.title;
    selectCampus(it.value);
    closeAllSuggest();
    majorInput.focus();
  });
}

function selectCampus(campusId){
  selectedCampus = campusId;

  majorsForCampus = [];
  fuseMajors = null;
  majorInput.value = "";
  delete majorInput.dataset.majorId;
  renderSuggestions(majorBox, [], ()=>{});

  const c = campuses.find(x => x.id === selectedCampus);
  if (!c) {
    majorSug.textContent = "Campus not found in index.";
    return;
  }

  selectedYear = c.latestYear || (c.years?.[0] || "");
  const yearMap = c.yearMap || {};
  majorsForCampus = yearMap[selectedYear] || [];

  fuseMajors = new Fuse(
    majorsForCampus.map(m => ({ label: m.pretty, id: m.id, path: m.path })),
    { keys:["label","id"], threshold:0.35 }
  );

  majorSug.textContent =
    `Campus locked: ${c.pretty} • ${majorsForCampus.length} majors • ${selectedYear}`;
}

schoolInput.addEventListener("input", () => {
  updateSchoolSuggestions();

  if (selectedCampus) {
    selectedCampus = "";
    selectedYear = "";
    majorsForCampus = [];
    fuseMajors = null;

    majorInput.value = "";
    delete majorInput.dataset.majorId;

    majorSug.textContent = "Pick a campus first to see major suggestions.";
    renderSuggestions(majorBox, [], ()=>{});
  }
});

schoolInput.addEventListener("focus", updateSchoolSuggestions);

function updateMajorSuggestions(){
  const q = majorInput.value.trim();

  if (!selectedCampus) {
    majorSug.textContent = "Pick a campus first.";
    renderSuggestions(majorBox, [], ()=>{});
    return;
  }

  if (!majorsForCampus.length) {
    majorSug.textContent = "No majors for this campus/year.";
    renderSuggestions(majorBox, [], ()=>{});
    return;
  }

  if (!q) {
    const top = majorsForCampus.slice(0, 8).map(m => ({
      title: m.pretty,
      sub: "Click to select",
      meta: "major",
      value: m.id
    }));

    majorSug.textContent = "Top majors (start typing to filter).";
    renderSuggestions(majorBox, top, (it) => {
      majorInput.value = it.title;
      majorInput.dataset.majorId = it.value;
      closeAllSuggest();
    });
    return;
  }

  if (!fuseMajors) return;

  const hits = fuseMajors.search(q, { limit: 8 });
  const items = hits.map(h => ({
    title: h.item.label,
    sub: "Click to select",
    meta: "major",
    value: h.item.id
  }));

  majorSug.textContent = `Matches: ${items.length}`;
  renderSuggestions(majorBox, items, (it) => {
    majorInput.value = it.title;
    majorInput.dataset.majorId = it.value;
    closeAllSuggest();
  });
}

majorInput.addEventListener("input", () => {
  delete majorInput.dataset.majorId;
  updateMajorSuggestions();
});
majorInput.addEventListener("focus", updateMajorSuggestions);

retryBtn.addEventListener("click", loadIndex);
clearBtn.addEventListener("click", clearUI);

loadBtn.addEventListener("click", async () => {
  parsedArea.innerHTML = "";
  finalOut.textContent = "";
  results.style.display = "none";

  if (!fuseCampus || !indexJson) { alert("Data not loaded."); return; }

  if (!selectedCampus) {
    const campusQ = schoolInput.value.trim();
    const campusHit = fuseCampus.search(campusQ, { limit: 1 })[0];
    if (!campusHit) { alert("Type a campus like UCSD, UCLA, UCB..."); return; }
    selectCampus(campusHit.item.id);
  }

  if (!selectedCampus || !selectedYear || !majorsForCampus.length) {
    alert("Campus selection failed. Re-pick the campus.");
    return;
  }

  let chosenMajorId = majorInput.dataset.majorId || "";
  let chosenMajorPretty = majorInput.value.trim();

  if (!chosenMajorId) {
    const majQ = majorInput.value.trim();
    if (!majQ) {
      chosenMajorId = majorsForCampus[0].id;
      chosenMajorPretty = majorsForCampus[0].pretty;
    } else if (fuseMajors) {
      const majHit = fuseMajors.search(majQ, { limit: 1 })[0];
      chosenMajorId = majHit ? majHit.item.id : majorsForCampus[0].id;
      chosenMajorPretty = majHit ? majHit.item.label : majorsForCampus[0].pretty;
    } else {
      chosenMajorId = majorsForCampus[0].id;
      chosenMajorPretty = majorsForCampus[0].pretty;
    }
  }

  const majorEntry = majorsForCampus.find(m => m.id === chosenMajorId) || majorsForCampus[0];
  if (!majorEntry?.path) {
    alert("Major path missing in index.json. Rebuild index.");
    return;
  }

  let majorJson;
  try{
    const res = await fetch("./" + majorEntry.path, { cache:"no-store" });
    const text = await res.text();
    if (!res.ok) {
      console.error("Major fetch failed:", res.status, text);
      alert(`Failed to load major file (HTTP ${res.status}).`);
      return;
    }
    majorJson = JSON.parse(text);
  } catch (e){
    console.error(e);
    alert("Failed to load major JSON. Check console.");
    return;
  }

  results.style.display = "block";
  parsedArea.innerHTML =
    `<div class="req"><b>Campus:</b> ${selectedCampus.replaceAll("_"," ")} <span class="tag"><i></i>${selectedYear}</span><br/>` +
    `<b>Major:</b> ${chosenMajorPretty || chosenMajorId}</div>`;

  const result = majorJson?.result || majorJson || {};
  const articulations = result.articulations || [];

  const orSelects = [];
  const autoPicked = new Map();

  for (const entry of articulations) {
    const art = entry.articulation || {};
    const target = art.course || {};
    const t_prefix = target.prefix || "";
    const t_num = target.courseNumber || "";
    const t_desc = target.courseTitle || "";
    if (!(t_prefix || t_num || t_desc)) continue;

    const card = document.createElement("div");
    card.className = "req";
    card.innerHTML = `<b>UC Requirement:</b> ${t_prefix} ${t_num} - ${t_desc}<div class="small">De Anza options below</div><hr class="hr"/>`;
    parsedArea.appendChild(card);

    const sending = art.sendingArticulation || {};
    const groups = sending.items || [];
    if (!groups.length) {
      const msg = document.createElement("div");
      msg.className = "small";
      msg.textContent = "(no articulation listed)";
      card.appendChild(msg);
      continue;
    }

    const posToConj = {};
    for (const gc of (sending.courseGroupConjunctions || [])) {
      const begin = gc.sendingCourseGroupBeginPosition;
      const conj = gc.groupConjunction;
      if (begin != null && conj) posToConj[begin] = conj;
    }

    const groupsSorted = groups.slice().sort((a,b)=>(a.position||0)-(b.position||0));
    const groupOptionNums = [];
    const choiceTypes = [];
    const optionMap = {};
    let optNum = 1;

    let currentChoiceSet = [];
    let currentChoiceType = "And";

    for (let i = 0; i < groupsSorted.length; i++) {
      const g = groupsSorted[i];
      const label = g.courseConjunction || "And";
      const groupOpts = [];

      for (const cls of (g.items || [])) {
        const c_prefix = cls.prefix || "";
        const c_num = cls.courseNumber || "";
        const c_title = cls.courseTitle || "";
        if (String(c_title).includes("HONORS")) continue;

        optionMap[optNum] = { prefix:c_prefix, number:c_num, title:c_title, group:label };

        const line = document.createElement("div");
        line.textContent = `${optNum} [${label}] ${c_prefix} ${c_num} - ${c_title}`;
        card.appendChild(line);

        groupOpts.push(optNum);
        optNum++;
      }

      if (i < groupsSorted.length - 1) {
        const conj = posToConj[g.position] || "And";
        const between = document.createElement("div");
        between.className = "small";
        between.textContent = `- [${conj}]`;
        card.appendChild(between);
      }

      currentChoiceSet = currentChoiceSet.concat(groupOpts);
      if (label === "Or") currentChoiceType = "Or";

      if (i < groupsSorted.length - 1) {
        const conj = posToConj[g.position] || "And";
         if (conj === "Or") {
          currentChoiceType = "Or"; // critical fix
          continue;
      }
    }

      groupOptionNums.push(currentChoiceSet.slice());
      choiceTypes.push(currentChoiceType);
      currentChoiceSet = [];
      currentChoiceType = "And";
    }

    for (let gi = 0; gi < groupOptionNums.length; gi++) {
      const opts = groupOptionNums[gi];
      const type = choiceTypes[gi] || "And";

      if (type === "And") {
        const note = document.createElement("div");
        note.className = "small";
        note.textContent = "Auto-picked (AND):";
        card.appendChild(note);

        for (const n of opts) {
          const c = optionMap[n];
          const key = `${c.prefix}::${c.number}`;
          if (!autoPicked.has(key)) autoPicked.set(key, c.title);
          const bullet = document.createElement("div");
          bullet.textContent = `• ${c.prefix} ${c.number} - ${c.title}`;
          card.appendChild(bullet);
        }
      } else {
        const wrap = document.createElement("div");
        wrap.className = "row";

        const labelEl = document.createElement("div");
        labelEl.className = "small";
        labelEl.textContent = "Pick one (OR group):";
        labelEl.style.minWidth = "220px";

        const sel = document.createElement("select");
        const ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "-- choose one --";
        sel.appendChild(ph);

        for (const n of opts) {
          const c = optionMap[n];
          const o = document.createElement("option");
          o.value = n;
          o.textContent = `${c.prefix} ${c.number} - ${c.title}`;
          sel.appendChild(o);
        }

        wrap.appendChild(labelEl);
        wrap.appendChild(sel);
        card.appendChild(wrap);

        orSelects.push({ sel, optionMap });
      }
    }
  }

  finalBtn.onclick = () => {
    const final = new Map(autoPicked);
    for (const { sel, optionMap } of orSelects) {
      if (!sel.value) continue;
      const c = optionMap[parseInt(sel.value,10)];
      if (!c) continue;
      const key = `${c.prefix}::${c.number}`;
      if (!final.has(key)) final.set(key, c.title);
    }

    finalOut.textContent = final.size
      ? Array.from(final.entries()).map(([k,title]) => {
          const [p,n] = k.split("::");
          return `${p} ${n} - ${title}`;
        }).join("\n")
      : "No classes picked yet.";
  };
});

copyBtn.addEventListener("click", async () => {
  const text = finalOut.textContent || "";
  if (!text.trim()) return;
  try{
    await navigator.clipboard.writeText(text);
    copyBtn.textContent = "Copied!";
    setTimeout(()=> copyBtn.textContent = "Copy", 900);
  } catch {
    alert("Copy failed (browser blocked). Select the text and copy manually.");
  }
});

loadIndex();
majorSug.textContent = "Pick a campus first to see major suggestions.";