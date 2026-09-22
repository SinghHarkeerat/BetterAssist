'use strict';

const $ = id => document.getElementById(id);
const STORAGE_KEY = 'better-assist.plans.v1';
let colleges = [],
  active = null,
  rows = [],
  plan = [],
  requestVersion = 0,
  controller;
let saved = {
    plans: {},
    last: null
  },
  storageAvailable = true,
  toastTimer,
  progressMode = 'planned';
try {
  const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
  if (data && typeof data.plans === 'object' && data.plans && !Array.isArray(data.plans)) saved = data;
} catch {
  storageAvailable = false;
}

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const sorted = items => [...(items || [])].sort((a, b) => (a.position || 0) - (b.position || 0));
const decode = value => {
  try {
    return typeof value === 'string' ? JSON.parse(value) : value || {};
  } catch {
    return {};
  }
};
const college = () => colleges.find(c => c.id === $('collegeInput').value);
const campus = () => college()?.campuses.find(c => c.id === $('schoolInput').value);
const majors = () => campus()?.yearMap[$('yearInput').value] || [];
const courseCode = c => `${c.prefix || ''} ${c.courseNumber || ''}`.trim();
const courseKey = c => courseCode(c).toUpperCase();
// Strip an honors suffix only when the course is actually labeled honors.
const courseFamily = c => `${String(c.prefix || '').toUpperCase()} ${String(c.courseNumber || '').toUpperCase().replace(/H$/, /honors/i.test(c.courseTitle || '') ? '' : 'H')}`.trim();
const yearLabel = year => /^\d{4}/.test(year) ? `${year.slice(0, 4)}–${Number(year.slice(0, 4)) + 1}` : year;
const normalize = text => String(text).normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const hasCourse = c => Boolean(c && courseCode(c));
const units = c => Number.isFinite(c.minUnits) ? (Number.isFinite(c.maxUnits) && c.maxUnits !== c.minUnits ? `${c.minUnits}–${c.maxUnits}` : String(c.minUnits)) : '';

function options(select, placeholder, list) {
  select.replaceChildren(new Option(placeholder, ''));
  for (const [value, label] of list) select.add(new Option(label, value));
}

function createCombobox(input, list, getItems, onPick, settings = {}) {
  const listeners = new AbortController();
  const on = (target, type, handler) => target.addEventListener(type, handler, {
    signal: listeners.signal
  });
  let matches = [],
    highlighted = -1;
  const close = () => {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    highlighted = -1;
  };

  function highlight(index) {
    highlighted = index;
    [...list.querySelectorAll('[role="option"]')].forEach((node, i) => node.setAttribute('aria-selected', String(i === index)));
    const node = list.querySelectorAll('[role="option"]')[index];
    if (node) {
      input.setAttribute('aria-activedescendant', node.id);
      node.scrollIntoView({
        block: 'nearest'
      });
    }
  }

  function choose(item) {
    if (item.disabled || onPick(item) === false) return;
    input.focus();
    close();
  }

  function render() {
    if (input.disabled) {
      close();
      return;
    }
    matches = getItems();
    highlighted = -1;
    input.removeAttribute('aria-activedescendant');
    list.replaceChildren();
    matches.forEach((item, index) => {
      const option = el('div', 'combo-option');
      option.id = `${list.id}-${index}`;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      if (item.disabled) option.setAttribute('aria-disabled', 'true');
      option.append(el('strong', '', item.label));
      if (item.detail) option.append(el('small', '', item.detail));
      option.addEventListener('mousedown', event => event.preventDefault());
      option.addEventListener('click', () => choose(item));
      list.append(option);
    });
    if (!matches.length) list.append(el('div', 'combo-empty', settings.emptyMessage || 'No matches. Try a different search.'));
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    $(settings.statusId || 'suggestionStatus').textContent = `${matches.length} suggestions. Use the arrow keys and Enter to choose.`;
  }
  on(input, 'focus', render);
  on(input, 'click', render);
  on(input, 'keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === 'Tab') {
      close();
      return;
    }
    if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault();
      if (list.hidden) render();
      if (matches.length) {
        const direction = event.key === 'ArrowDown' ? 1 : -1;
        let next = highlighted < 0 ? (direction === 1 ? 0 : matches.length - 1) : (highlighted + direction + matches.length) % matches.length;
        for (let attempts = 0; attempts < matches.length; attempts++) {
          if (!matches[next].disabled) {
            highlight(next);
            break;
          }
          next = (next + direction + matches.length) % matches.length;
        }
      }
    } else if (event.key === 'Enter' && !list.hidden) {
      event.preventDefault();
      if (highlighted >= 0) choose(matches[highlighted]);
      else if (matches.length === 1) choose(matches[0]);
    }
  });
  on(input, 'blur', close);
  on(document, 'pointerdown', event => {
    if (!input.parentElement.contains(event.target)) close();
  });
  return {
    render,
    close,
    destroy() {
      close();
      listeners.abort();
    }
  };
}

function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => {
    $('toast').hidden = true;
  }, 3500);
}

function error(message = '') {
  $('formError').textContent = message;
  $('formError').hidden = !message;
}

function save() {
  saved.college = $('collegeInput').value;
  if (active) {
    saved.plans[active.key] = plan;
    saved.last = {
      college: active.college.id,
      campus: active.campus.id,
      year: active.year,
      major: active.major.id
    };
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  } catch {
    storageAvailable = false;
  }
  $('saveNote').textContent = storageAvailable ? 'Saved in this browser as you go.' : 'Browser storage is unavailable. Copy your plan to keep it.';
}

function invalidate() {
  requestVersion++;
  controller?.abort();
  active = null;
  rows = [];
  plan = [];
  $('results').hidden = true;
  $('welcome').hidden = false;
  $('loadBtn').textContent = 'Show my course matches →';
  $('loadBtn').disabled = !$('majorSelect').value;
  $('finderForm').removeAttribute('aria-busy');
  error();
  renderPlan();
}

function changeCollege() {
  invalidate();
  const available = Boolean(college()?.campuses.length);
  $('collegeNotice').hidden = available;
  if (!available) {
    $('collegeNotice').replaceChildren(document.createTextNode(`${college()?.name || 'This college'} agreements aren’t included yet. Look them up on `));
    const link = el('a', '', 'ASSIST ↗');
    link.href = 'https://assist.org';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    $('collegeNotice').append(link);
  }
  options($('schoolInput'), available ? 'Choose a campus' : 'No agreements available', (college()?.campuses || []).map(c => [c.id, `${c.code} · ${c.pretty}`]));
  $('schoolInput').disabled = !available;
  $('schoolSearch').disabled = !available;
  $('schoolSearch').value = '';
  changeCampus();
  if (typeof renderCalGetc === 'function') renderCalGetc();
}

function changeCampus() {
  invalidate();
  const c = campus();
  schoolCombo.close();
  if (c) $('schoolSearch').value = `${c.code} · ${c.pretty}`;
  options($('yearInput'), c ? 'Choose a year' : 'Choose a campus first', (c?.years || []).map(y => [y, yearLabel(y)]));
  $('yearInput').disabled = !c;
  if (c) $('yearInput').value = c.latestYear;
  changeYear();
}

function changeYear() {
  invalidate();
  $('majorInput').value = '';
  $('majorInput').disabled = !majors().length;
  majorCombo.close();
  filterMajors();
}

function filterMajors() {
  invalidate();
  const words = normalize($('majorInput').value.trim()).split(/\s+/).filter(Boolean);
  const matches = majors().filter(m => words.every(word => normalize(`${m.pretty} ${m.id}`).includes(word)));
  options($('majorSelect'), !campus() ? 'Choose a campus first' : matches.length ? 'Choose a major' : 'No matching majors', matches.map(m => [m.id, m.pretty]));
  $('majorSelect').disabled = !matches.length;
  $('loadBtn').disabled = true;
  $('majorHint').textContent = !campus() ? 'Choose a campus to see its majors.' : matches.length ? `${matches.length} majors match. Choose a suggestion.` : 'No matches. Try a broader search, such as “biology”.';
  if (document.activeElement === $('majorInput')) majorCombo.render();
}

// Imported agreement HTML is converted to text, never inserted into the live page.
function plainText(html) {
  const doc = new DOMParser().parseFromString(String(html), 'text/html');
  doc.querySelectorAll('script,style,iframe,object,img').forEach(node => node.remove());
  doc.querySelectorAll('br').forEach(node => node.replaceWith('\n'));
  doc.querySelectorAll('p,li,div,h1,h2,h3,tr').forEach(node => node.append('\n'));
  return doc.body.textContent.replace(/[ \t]+/g, ' ').replace(/\n\s*\n\s*\n/g, '\n\n').trim();
}

function instructionText(instruction) {
  if (!instruction) return '';
  if (instruction.type === 'Following') return `${instruction.selectionType || 'Complete'} the following group of courses; see the full agreement for context.`;
  if (instruction.amount != null) return `${instruction.selectionType || 'Complete'} ${instruction.amountQuantifier && instruction.amountQuantifier !== 'None' ? instruction.amountQuantifier + ' ' : ''}${instruction.amount} ${instruction.amountUnitType || 'course(s)'} from this group in the agreement.`;
  return 'This group has additional selection instructions. Review the full agreement on ASSIST.';
}

function collectNotes(value, output = []) {
  if (Array.isArray(value)) {
    sorted(value).forEach(item => collectNotes(item, output));
    return output;
  }
  if (!value || typeof value !== 'object') return output;
  for (const [key, child] of Object.entries(value)) {
    if (['content', 'text', 'description'].includes(key) && typeof child === 'string') {
      const text = plainText(child);
      if (text) output.push(text);
    } else if (key === 'instruction') {
      const text = instructionText(child);
      if (text) output.push(text);
    } else if (typeof child === 'object') collectNotes(child, output);
  }
  return [...new Set(output)];
}

function contextMap(assets) {
  const map = new Map();

  function walk(value, inherited = []) {
    if (Array.isArray(value)) {
      value.forEach(v => walk(v, inherited));
      return;
    }
    if (!value || typeof value !== 'object') return;
    const notes = [...inherited, instructionText(value.instruction), ...collectNotes(value.attributes), ...collectNotes(value.advisements)].filter(Boolean);
    if (value.id) map.set(value.id, [...new Set(notes)]);
    for (const key of ['sections', 'rows', 'cells'])
      if (value[key]) walk(value[key], notes);
  }
  walk(assets);
  return map;
}

function normalizeRows(result) {
  const contexts = contextMap(result.templateAssets || []);
  return (result.articulations || []).map((entry, index) => {
    const art = entry.articulation || {},
      sending = art.sendingArticulation || {};
    const targets = art.course ? [art.course] : sorted(art.series?.courses || art.generalEducationArea?.courses || []);
    const title = art.series?.name || art.requirement?.name || art.generalEducationArea?.name || art.transferability?.name || art.type || 'Agreement item';
    const groups = sorted(sending.items).map(group => ({
      ...group,
      items: sorted(group.items).filter(hasCourse)
    })).filter(g => g.items.length);
    const review = !groups.length || Boolean(sending.noArticulationReason) || sending.type === 'TemplateOverride';
    return {
      index,
      art,
      sending,
      targets,
      title,
      groups,
      review,
      notes: [...new Set([...(contexts.get(entry.templateCellId) || []), ...collectNotes(art)])],
      search: normalize([title, ...targets.map(c => `${courseCode(c)} ${c.courseTitle}`), ...groups.flatMap(g => g.items.map(c => `${courseCode(c)} ${c.courseTitle}`))].join(' '))
    };
  });
}

function courseNode(c) {
  const node = el('div', 'course-item');
  node.append(el('strong', 'course-code', courseCode(c)), el('div', 'course-title', c.courseTitle || 'Course title unavailable'));
  if (units(c)) node.append(el('div', 'course-units', `${units(c)} units`));
  if (/honors/i.test(c.courseTitle || '')) node.append(el('span', 'course-tag', 'Honors option'));
  const crossListed = (c.visibleCrossListedCourses || []).map(item => courseCode(item.course || item)).filter(Boolean);
  if (crossListed.length) node.append(el('div', 'row-note', `Cross-listed as ${crossListed.join(', ')}. See the agreement for details.`));
  return node;
}

function groupLink(row, left, right) {
  return (row.sending.courseGroupConjunctions || []).find(c => c.sendingCourseGroupBeginPosition === left.position && c.sendingCourseGroupEndPosition === right.position)?.groupConjunction;
}

function alternativeKeys(row, groupIndex, chosen) {
  let start = groupIndex,
    end = groupIndex;
  while (start > 0 && groupLink(row, row.groups[start - 1], row.groups[start]) === 'Or') start--;
  while (end < row.groups.length - 1 && groupLink(row, row.groups[end], row.groups[end + 1]) === 'Or') end++;
  const selected = new Set(chosen.map(courseKey));
  return row.groups.slice(start, end + 1).flatMap(g => g.items.map(courseKey)).filter(key => !selected.has(key));
}

function conflictingCourses(courses, excluded = []) {
  const selected = new Set(courses.map(courseKey));
  return plan.filter(p => !selected.has(courseKey(p)) && (excluded.includes(courseKey(p)) || courses.some(c => courseFamily(c) === courseFamily(p))));
}

function addButton(courses, excluded = []) {
  const button = el('button', 'add-course');
  button.type = 'button';
  button.dataset.courses = JSON.stringify(courses.map(courseKey));
  button.courseChoices = courses;
  button.excludedChoices = excluded;
  button.dataset.label = courses.length > 1 ? `+ Add ${courses.length} courses` : '+ Add to plan';
  button.setAttribute('aria-label', `Add ${courses.map(courseCode).join(' and ')} to your plan`);
  button.addEventListener('click', () => {
    const removed = conflictingCourses(courses, excluded);
    plan = plan.filter(p => !removed.includes(p));
    let added = 0;
    for (const c of courses)
      if (!plan.some(p => courseKey(p) === courseKey(c))) {
        plan.push({
          prefix: c.prefix,
          courseNumber: c.courseNumber,
          courseTitle: c.courseTitle || '',
          minUnits: c.minUnits,
          maxUnits: c.maxUnits,
          completed: false
        });
        added++;
      }
    save();
    renderPlan();
    updateAddButtons();
    toast(removed.length ? `Choice updated. Replaced ${removed.map(courseCode).join(', ')}.` : added ? `${added} ${added === 1 ? 'course added' : 'courses added'} to your plan.` : 'These courses are already in your plan.');
  });
  return button;
}

function updateAddButtons() {
  document.querySelectorAll('.add-course').forEach(button => {
    const included = JSON.parse(button.dataset.courses).every(key => plan.some(c => courseKey(c) === key));
    const conflicts = conflictingCourses(button.courseChoices, button.excludedChoices);
    button.textContent = included ? '✓ In your plan' : conflicts.length ? (button.courseChoices.length > 1 ? '⇄ Switch to this set' : '⇄ Switch to this course') : button.dataset.label;
    button.title = conflicts.length ? `Replaces ${conflicts.map(courseCode).join(', ')} in your plan` : '';
    button.setAttribute('aria-label', `${included ? 'In your plan:' : conflicts.length ? 'Switch to' : 'Add'} ${button.courseChoices.map(courseCode).join(' and ')}${conflicts.length ? '; replaces ' + conflicts.map(courseCode).join(', ') : ''}`);
    button.classList.toggle('added', included);
    button.disabled = included;
  });
}

function renderChart() {
  const query = normalize($('courseSearch').value.trim()),
    filter = $('matchFilter').value;
  const visible = rows.filter(row => (!query || row.search.includes(query)) && (filter === 'all' || (filter === 'review' ? row.review : !row.review)));
  const fragment = document.createDocumentFragment();
  for (const row of visible) {
    const tr = el('tr'),
      source = el('td'),
      target = el('td');
    if (row.review) {
      source.append(el('span', 'review-tag', 'Needs review'), el('p', 'no-articulation', row.sending.noArticulationReason || 'No standard course match is listed. Check the agreement notes.'));
    }
    row.groups.forEach((group, index) => {
      if (index > 0) {
        const previous = row.groups[index - 1];
        const connection = (row.sending.courseGroupConjunctions || []).find(c => c.sendingCourseGroupBeginPosition === previous.position && c.sendingCourseGroupEndPosition === group.position);
        // A missing connector is not permission to infer a requirement or alternative.
        source.append(el('div', 'conjunction', connection?.groupConjunction?.toUpperCase() || 'SEE AGREEMENT'));
      }
      const container = el('div', 'course-group');
      const isOr = group.courseConjunction === 'Or';
      if (group.items.length > 1) container.append(el('div', 'group-label', isOr ? 'Choose one of these courses' : 'Take all courses in this set'));
      group.items.forEach(c => {
        const node = courseNode(c);
        if (isOr && !row.review) node.append(addButton([c], alternativeKeys(row, index, [c])));
        container.append(node);
      });
      if (!isOr && !row.review) container.append(addButton(group.items, alternativeKeys(row, index, group.items)));
      source.append(container);
    });
    if (row.art.type === 'Series') target.append(el('div', 'group-label', row.art.series?.conjunction === 'Or' ? 'University alternatives' : 'University course sequence'));
    if (row.targets.length) row.targets.forEach(c => target.append(courseNode(c)));
    else target.append(el('strong', 'course-code', row.title));
    if (row.notes.length) {
      const detail = el('details', 'row-note');
      detail.append(el('summary', '', 'Context & notes'), el('div', '', row.notes.join('\n\n')));
      target.append(detail);
    }
    tr.append(source, target);
    fragment.append(tr);
  }
  $('chartBody').replaceChildren(fragment);
  $('noMatches').hidden = Boolean(visible.length);
  updateAddButtons();
}

function rowIsPlanned(row) {
  if (!row.groups.length || row.review) return false;
  const selected = new Set(plan.map(courseKey));
  const meets = group => group.courseConjunction === 'Or' ? group.items.some(c => selected.has(courseKey(c))) : group.items.every(c => selected.has(courseKey(c)));
  // AND-connected sets must all be present; OR separates complete alternatives.
  let branch = meets(row.groups[0]),
    covered = false;
  for (let i = 1; i < row.groups.length; i++) {
    const link = groupLink(row, row.groups[i - 1], row.groups[i]);
    if (!link) return false; // Don't infer credit when the agreement omits its connector.
    if (link === 'Or') {
      covered ||= branch;
      branch = meets(row.groups[i]);
    } else branch &&= meets(row.groups[i]);
  }
  return covered || branch;
}

function renderPlan() {
  $('mobilePlanBar').hidden = !active;
  $('mobilePlanCount').textContent = `${plan.length} ${plan.length === 1 ? 'course' : 'courses'}`;
  $('planContext').textContent = active ? `${active.college.name} → ${active.campus.code} · ${active.major.pretty} · ${yearLabel(active.year)}` : 'Your next steps, all in one place.';
  const done = plan.filter(c => c.completed).length;
  const mappable = rows.filter(row => !row.review && row.groups.every((g, i) => i === 0 || groupLink(row, row.groups[i - 1], g)));
  const numerator = progressMode === 'planned' ? mappable.filter(rowIsPlanned).length : done;
  const denominator = progressMode === 'planned' ? mappable.length : plan.length;
  const percent = denominator ? Math.round(numerator / denominator * 100) : 0;
  $('plannedView').setAttribute('aria-pressed', String(progressMode === 'planned'));
  $('completedView').setAttribute('aria-pressed', String(progressMode === 'completed'));
  $('progressLabel').textContent = progressMode === 'planned' ? 'planned' : 'completed';
  $('progressPercent').textContent = `${percent}%`;
  $('progressCount').textContent = progressMode === 'planned' ? `${numerator} of ${denominator} matches planned` : `${done} of ${plan.length} courses`;
  $('progressHelp').textContent = progressMode === 'planned' ? 'Complete course sets count as planned. Items needing review are excluded.' : 'Check off the courses you have finished below.';
  $('completionCount').textContent = `${done} of ${plan.length} planned courses completed. Use the checkboxes below.`;
  $('progressRing').style.setProperty('--progress', `${percent}%`);
  $('progressRing').setAttribute('aria-label', `${$('progressCount').textContent}, ${percent} percent`);
  $('savedCount').textContent = plan.length;
  $('planEmpty').hidden = Boolean(plan.length);
  $('copyBtn').disabled = !plan.length;
  $('printBtn').disabled = !plan.length;
  const fragment = document.createDocumentFragment();
  plan.forEach(c => {
    const item = el('li', c.completed ? 'is-complete' : ''),
      label = el('label'),
      input = el('input'),
      text = el('span');
    input.type = 'checkbox';
    input.checked = c.completed;
    input.setAttribute('aria-label', `Mark ${courseCode(c)} completed`);
    input.addEventListener('change', () => {
      c.completed = input.checked;
      save();
      // Keep the focused checkbox in place while updating the progress graphic.
      const key = courseKey(c);
      renderPlan();
      Array.from($('planList').querySelectorAll('input')).find(node => node.dataset.key === key)?.focus();
    });
    input.dataset.key = courseKey(c);
    text.append(el('strong', '', courseCode(c)), el('small', '', c.courseTitle));
    label.append(input, text);
    const remove = el('button', 'remove-course', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', `Remove ${courseCode(c)} from plan`);
    remove.addEventListener('click', () => {
      plan = plan.filter(p => courseKey(p) !== courseKey(c));
      save();
      renderPlan();
      updateAddButtons();
      toast(`${courseCode(c)} removed from your plan.`);
    });
    item.append(label, remove);
    fragment.append(item);
  });
  $('planList').replaceChildren(fragment);
  const known = plan.every(c => Number.isFinite(c.minUnits) && Number.isFinite(c.maxUnits));
  const minimum = plan.reduce((n, c) => n + (Number(c.minUnits) || 0), 0),
    maximum = plan.reduce((n, c) => n + (Number(c.maxUnits) || 0), 0);
  $('planUnits').hidden = !plan.length;
  $('planUnits').textContent = known ? `${minimum === maximum ? minimum : minimum + '–' + maximum} ${active?.termType === 'Quarter' ? 'quarter' : active?.termType === 'Semester' ? 'semester' : ''} units in your plan` : 'Some course unit values are not listed.';
  $('saveNote').textContent = storageAvailable ? 'Saved in this browser as you go.' : 'Browser storage is unavailable. Copy your plan to keep it.';
}
async function loadAgreement({
  scroll = true
} = {}) {
  const c = campus(),
    m = majors().find(item => item.id === $('majorSelect').value),
    source = college(),
    year = $('yearInput').value;
  if (!c || !m || !source) {
    error('Choose a campus, agreement year, and major first.');
    return;
  }
  invalidate();
  const version = requestVersion;
  $('majorInput').value = m.pretty;
  controller = new AbortController();
  $('loadBtn').disabled = true;
  $('loadBtn').textContent = 'Finding your course matches…';
  $('finderForm').setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('./' + m.path.split('/').map(encodeURIComponent).join('/'), {
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`The agreement could not be loaded (HTTP ${response.status}).`);
    const payload = await response.json(),
      result = payload.result || payload;
    if (version !== requestVersion) return;
    if (!Array.isArray(result.articulations)) throw new Error('This file does not contain a course agreement.');
    const sender = decode(result.sendingInstitution);
    if (!(sender.names || []).some(n => n.name === source.name)) throw new Error('This agreement belongs to a different community college.');
    active = {
      college: source,
      campus: c,
      major: m,
      year,
      key: JSON.stringify([source.id, c.id, year, m.id]),
      termType: sender.termType
    };
    const storedPlan = saved.plans[active.key];
    plan = Array.isArray(storedPlan) ? storedPlan.filter(hasCourse).map(c => ({
      ...c,
      completed: c.completed === true
    })) : [];
    // Older saved plans allowed both honors and regular versions. Keep the latest choice.
    plan = [...new Map(plan.map(c => [courseFamily(c), c])).values()];
    rows = normalizeRows(result);
    $('courseSearch').value = '';
    $('matchFilter').value = 'all';
    $('resultCampus').textContent = `${c.code} / ${c.pretty}`;
    $('resultMajor').textContent = result.name || m.pretty;
    $('resultYear').textContent = decode(result.academicYear).code || yearLabel(year);
    $('resultMeta').textContent = `From ${source.name} · ${rows.length} agreement items`;
    $('sourceHeading').textContent = `AT ${source.name.replace(' College', '').toUpperCase()}`;
    $('targetHeading').textContent = `AT ${c.code}`;
    $('matchCount').textContent = rows.filter(r => !r.review).length;
    $('reviewCount').textContent = rows.filter(r => r.review).length;
    $('agreementNotes').textContent = collectNotes(result.templateAssets).join('\n\n') || 'No additional notes are included in this file. Review the full agreement on ASSIST.';
    $('results').hidden = false;
    $('welcome').hidden = true;
    renderChart();
    renderPlan();
    save();
    if (!rows.length) {
      $('noMatches').hidden = false;
      $('noMatches').textContent = 'This agreement contains no course matches. Read the agreement notes or open ASSIST for details.';
    } else $('noMatches').textContent = 'No matches here. Try another subject or clear the filters.';
    if (scroll && matchMedia('(max-width: 760px)').matches) $('results').scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start'
    });
  } catch (e) {
    if (version !== requestVersion || e.name === 'AbortError') return;
    error(`${e.message} Please try again.`);
  } finally {
    if (version === requestVersion) {
      $('loadBtn').disabled = !$('majorSelect').value;
      $('loadBtn').textContent = 'Show my course matches →';
      $('finderForm').removeAttribute('aria-busy');
    }
  }
}
async function loadIndex() {
  $('retryBtn').hidden = true;
  $('statusText').textContent = 'Loading available agreements…';
  error();
  try {
    const response = await fetch('./data/index.json', {
      cache: 'no-store'
    });
    if (!response.ok) throw new Error('Data unavailable');
    const data = await response.json();
    // A static host may briefly serve an index from the previous deployment.
    colleges = Array.isArray(data.colleges) ? data.colleges : [{
      id: 'deanza',
      name: 'De Anza College',
      campuses: data.campuses || []
    }, {
      id: 'foothill',
      name: 'Foothill College',
      campuses: []
    }];
    if (!colleges.some(c => c.campuses?.length)) throw new Error('No agreements found');
    const last = saved.last;
    $('collegeInput').replaceChildren(...colleges.map(c => new Option(c.name, c.id)));
    const preferredCollege = saved.college || last?.college;
    if (colleges.some(c => c.id === preferredCollege)) $('collegeInput').value = preferredCollege;
    changeCollege();
    $('statusText').textContent = `${colleges.reduce((n,c) => n + c.campuses.length, 0)} campus routes · saved agreements`;
    if (last && last.college === college()?.id && college()?.campuses.some(c => c.id === last.campus)) {
      $('schoolInput').value = last.campus;
      changeCampus();
      if (campus().years.includes(last.year)) {
        $('yearInput').value = last.year;
        changeYear();
      }
      if (majors().some(m => m.id === last.major)) {
        $('majorSelect').value = last.major;
        await loadAgreement({
          scroll: false
        });
      }
    }
  } catch {
    $('statusText').textContent = 'Agreements could not be loaded.';
    $('retryBtn').hidden = false;
    error(location.protocol === 'file:' ? 'Open this app through a local web server so its course data can load.' : 'Check your connection and try again. Your saved plans are still in this browser.');
  }
}
const schoolCombo = createCombobox($('schoolSearch'), $('schoolOptions'), () => {
  const query = campus() ? '' : normalize($('schoolSearch').value.trim());
  return (college()?.campuses || []).filter(c => query.split(/\s+/).every(word => normalize(`${c.code} ${c.pretty} ${c.id}`).includes(word)))
    .map(c => ({
      id: c.id,
      label: c.code,
      detail: c.pretty
    }));
}, item => {
  $('schoolInput').value = item.id;
  changeCampus();
});
const majorCombo = createCombobox($('majorInput'), $('majorOptions'), () => {
  const words = $('majorSelect').value ? [] : normalize($('majorInput').value.trim()).split(/\s+/);
  return majors().filter(m => words.every(word => normalize(`${m.pretty} ${m.id}`).includes(word)))
    .map(m => ({
      id: m.id,
      label: m.pretty
    }));
}, item => {
  $('majorSelect').value = item.id;
  $('majorSelect').dispatchEvent(new Event('change'));
});
$('schoolSearch').addEventListener('input', () => {
  $('schoolInput').value = '';
  changeCampus();
  schoolCombo.render();
});
$('collegeInput').addEventListener('change', () => {
  changeCollege();
  save();
});
$('schoolInput').addEventListener('change', changeCampus);
$('yearInput').addEventListener('change', changeYear);
$('majorInput').addEventListener('input', filterMajors);
$('majorSelect').addEventListener('change', () => {
  invalidate();
  $('majorInput').value = majors().find(m => m.id === $('majorSelect').value)?.pretty || '';
  majorCombo.close();
  $('loadBtn').disabled = !$('majorSelect').value;
});
$('finderForm').addEventListener('submit', event => {
  event.preventDefault();
  loadAgreement();
});
$('retryBtn').addEventListener('click', loadIndex);
$('clearBtn').addEventListener('click', () => {
  saved.last = null;
  changeCollege();
  save();
  $('schoolSearch').focus();
  toast('Search reset. Your saved course plans are kept.');
});
$('courseSearch').addEventListener('input', renderChart);
$('matchFilter').addEventListener('change', renderChart);
$('plannedView').addEventListener('click', () => {
  progressMode = 'planned';
  saved.progressMode = progressMode;
  save();
  renderPlan();
});
$('completedView').addEventListener('click', () => {
  progressMode = 'completed';
  saved.progressMode = progressMode;
  save();
  renderPlan();
});
$('printBtn').addEventListener('click', () => window.print());
$('copyBtn').addEventListener('click', async () => {
  if (!active || !plan.length) return;
  const text = [`Better Assist — my course plan`, `${active.college.name} → ${active.campus.pretty}`, `${active.major.pretty} | ${yearLabel(active.year)}`, '', ...plan.map(c => `[${c.completed ? 'x' : ' '}] ${courseCode(c)} — ${c.courseTitle}${units(c) ? ' (' + units(c) + ' units)' : ''}`), '', 'Personal planning checklist. Review the full agreement and requirements at https://assist.org.'].join('\n');
  try {
    await navigator.clipboard.writeText(text);
    toast('Course plan copied.');
  } catch {
    const area = el('textarea');
    area.value = text;
    area.setAttribute('aria-label', 'Course plan to copy');
    area.style.cssText = 'position:fixed;left:10px;bottom:10px;width:calc(100% - 20px);height:180px;z-index:30';
    document.body.append(area);
    area.focus();
    area.select();
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch {
      /* Manual copy remains available. */
    }
    if (copied) {
      area.remove();
      $('copyBtn').focus();
      toast('Course plan copied.');
    } else {
      toast('Press Ctrl+C or ⌘C to copy the selected plan. Press Escape to close.');
      area.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          area.remove();
          $('copyBtn').focus();
        }
      });
      area.addEventListener('blur', () => area.remove(), {
        once: true
      });
    }
  }
});
progressMode = saved.progressMode === 'completed' ? 'completed' : 'planned';
renderPlan();
loadIndex();
