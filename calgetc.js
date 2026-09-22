'use strict';

// Approved-course suggestions are pinned to the checklist's academic year.
// Selecting a course plans it; completion and certification are separate.
const GE_YEAR = '2025-2026';
let geCatalog = null,
  geLoading = true,
  geLoadError = false,
  geCombos = [];
const GE_SOURCES = {
  deanza: 'https://www.csueastbay.edu/aps/cccge2526/de-anza-college-cal-getc-2025-26.pdf',
  foothill: 'https://fhweb.foothill.edu/articulation/pdf/25-26-FH-calgetc-course-list.pdf'
};
const GE_AREAS = [{
  name: '1 · English communication',
  note: 'One course in each subject.',
  items: [
    ['1A', 'English composition'],
    ['1B', 'Critical thinking & composition'],
    ['1C', 'Oral communication']
  ]
}, {
  name: '2 · Mathematics',
  note: 'One approved math or quantitative reasoning course.',
  items: [
    ['2', 'Mathematics / quantitative reasoning']
  ]
}, {
  name: '3 · Arts & humanities',
  note: 'One arts course and one humanities course.',
  items: [
    ['3A', 'Arts'],
    ['3B', 'Humanities']
  ]
}, {
  name: '4 · Social & behavioral sciences',
  note: 'Two courses from different disciplines. Confirm any approved interdisciplinary sequence with your counselor.',
  items: [
    ['4A', 'First discipline'],
    ['4B', 'Second discipline']
  ]
}, {
  name: '5 · Physical & biological sciences',
  note: 'One physical science, one biological science, and an associated lab. An included lab can meet the lab checkpoint.',
  items: [
    ['5A', 'Physical science'],
    ['5B', 'Biological science'],
    ['5C', 'Science laboratory']
  ]
}, {
  name: '6 · Ethnic studies',
  note: 'One approved ethnic studies course.',
  items: [
    ['6', 'Ethnic studies']
  ]
}];

function geState() {
  if (!saved.ge || typeof saved.ge !== 'object' || Array.isArray(saved.ge)) saved.ge = {};
  const key = JSON.stringify([$('collegeInput').value, GE_YEAR]);
  if (!saved.ge[key] || typeof saved.ge[key] !== 'object' || Array.isArray(saved.ge[key])) saved.ge[key] = {};
  return saved.ge[key];
}

const geArea = id => ['4A', '4B'].includes(id) ? '4' : id;
const geCourses = () => geCatalog?.colleges[$('collegeInput').value]?.courses || [];
const geCourse = (id, state = geState()) => geCourses().find(c => c.code === state[id]?.selectedCode && c.areas.includes(geArea(id)));
const geCodeKey = code => normalize(code).replace(/\s+/g, '');
const geComponents = course => course.components.map(geCodeKey);
const geFamilies = course => [...course.components, ...(course.crossListed || [])].map(code => geCodeKey(code).replace(/h(?=l?$)/, course.honors ? '' : 'h'));

function geConflict(course, id, state = geState()) {
  for (const [otherId] of GE_AREAS.flatMap(area => area.items)) {
    if (otherId === id) continue;
    const other = geCourse(otherId, state);
    if (!other) continue;
    const overlap = geFamilies(course).some(key => geFamilies(other).includes(key));
    if (overlap) {
      const labPair = (id === '5C' && ['5A', '5B'].includes(otherId)) || (otherId === '5C' && ['5A', '5B'].includes(id));
      const differentVersions = course.components.some(code => other.components.some(otherCode => {
        const a = geCodeKey(code),
          b = geCodeKey(otherCode);
        return a !== b && a.replace(/h(?=l?$)/, '') === b.replace(/h(?=l?$)/, '');
      }));
      if (labPair && !differentVersions && geComponents(course).some(key => geComponents(other).includes(key))) continue;
      return `Already allocated to ${otherId}: ${other.code}. Choose a different course.`;
    }
    if (geArea(id) === '4' && geArea(otherId) === '4' && course.prefix === other.prefix) {
      return `Choose a different discipline from ${other.prefix} in ${otherId}.`;
    }
  }
  return '';
}

function geSuggestions(id, query) {
  const words = normalize(query).trim().split(/\s+/).filter(Boolean);
  return geCourses().filter(course => course.areas.includes(geArea(id))).filter(course => {
    const text = normalize(`${course.code} ${course.title}`);
    return words.every(word => text.includes(word)) || geCodeKey(course.code).includes(geCodeKey(query));
  }).sort((a, b) => a.code.localeCompare(b.code, undefined, {
    numeric: true
  })).map(course => {
    const conflict = geConflict(course, id);
    const unitLabel = course.minUnits == null ? '' : ` · ${course.minUnits === course.maxUnits ? course.minUnits : course.minUnits + '–' + course.maxUnits} quarter units`;
    return {
      id: course.code,
      label: course.code,
      disabled: Boolean(conflict),
      detail: conflict || `${course.title === course.code ? 'Approved course' : course.title}${unitLabel}${course.components.length > 1 ? ' · Take both courses' : ''}`,
      course
    };
  });
}

function updateGeSelectionHints() {
  const state = geState();
  for (const [id] of GE_AREAS.flatMap(area => area.items)) {
    const hint = $(`ge-hint-${id}`),
      selected = geCourse(id, state);
    if (!hint) continue;
    if (selected) {
      const conflict = geConflict(selected, id, state);
      hint.textContent = conflict || `${selected.title === selected.code ? selected.code : selected.title} · Listed for Area ${geArea(id)}${selected.components.length > 1 ? ' · Both courses required' : ''}${selected.limitedCredit ? ' · Check transfer-credit limits in the source' : ''}`;
      hint.classList.toggle('ge-selected', !conflict);
    } else {
      hint.classList.remove('ge-selected');
      const count = geCourses().filter(c => c.areas.includes(geArea(id))).length;
      hint.textContent = geLoading ? 'Loading approved courses…' : geLoadError ? 'Course suggestions are unavailable. Retry above.' : state[id]?.course ? 'Choose a suggestion to match this entry. Other college or exam credit needs counselor review.' : `${count} approved options. Type a code or title, or click to browse.`;
    }
    $(`ge-${id}`).checked = state[id]?.completed === true;
  }
}

async function loadGeCourses() {
  if (geLoading && geCatalog) return;
  geLoading = true;
  geLoadError = false;
  $('geRetry').hidden = true;
  $('geDataStatus').textContent = 'Loading approved courses…';
  try {
    const response = await fetch('./data/calgetc-2025-2026.json', {
      cache: 'no-store'
    });
    if (!response.ok) throw new Error('Course list unavailable');
    const data = await response.json();
    if (data.year !== GE_YEAR || !['deanza', 'foothill'].every(id => Array.isArray(data.colleges?.[id]?.courses) && data.colleges[id].courses.length > 0)) throw new Error('Invalid course list');
    geCatalog = data;
  } catch {
    geLoadError = true;
  } finally {
    geLoading = false;
    renderCalGetc();
  }
}

function updateGeProgress() {
  const state = geState();
  const done = GE_AREAS.flatMap(area => area.items).filter(([id]) => state[id]?.completed === true).length;
  const planned = GE_AREAS.flatMap(area => area.items).filter(([id]) => geCourse(id, state)).length;
  $('gePercent').textContent = `${Math.round(done / 12 * 100)}%`;
  $('geProgress').value = done;
  $('geCount').textContent = `${done}/12 completed · ${planned}/12 planned${done === 12 ? ' · Review with your counselor' : ''}`;
  $('geSaveStatus').textContent = storageAvailable ? 'Saved for this college and checklist year.' : 'Browser storage is unavailable. Print this checklist to keep a copy.';
  document.querySelectorAll('.ge-area').forEach((node, index) => {
    const items = GE_AREAS[index].items;
    const count = items.filter(([id]) => state[id]?.completed === true).length;
    node.querySelector('.ge-area-count').textContent = `${count}/${items.length}`;
  });
}

function renderCalGetc() {
  const openAreas = [...document.querySelectorAll('.ge-area')].map(node => node.open);
  geCombos.forEach(combo => combo.destroy());
  geCombos = [];
  const state = geState();
  $('geContext').textContent = `${college()?.name || $('collegeInput').selectedOptions[0]?.textContent || 'Your college'} · ${GE_YEAR} · Personal area checklist`;
  $('geSource').href = GE_SOURCES[$('collegeInput').value] || 'https://assist.org';
  $('geRetry').hidden = !geLoadError;
  $('geDataStatus').textContent = geLoading ? 'Loading approved courses…' : geLoadError ? 'Could not load course suggestions. Your saved checklist is still here.' : `${geCourses().length} approved courses and course sets · ${GE_YEAR}. Suggestions are specific to each area.`;
  const fragment = document.createDocumentFragment();
  GE_AREAS.forEach((area, index) => {
    const section = el('details', 'ge-area');
    section.open = openAreas[index] || false;
    const summary = el('summary');
    summary.append(el('span', '', area.name), el('span', 'ge-area-count'));
    section.append(summary, el('p', 'field-hint', area.note));
    area.items.forEach(([id, title]) => {
      const record = state[id] && typeof state[id] === 'object' ? state[id] : {
        completed: false,
        course: ''
      };
      state[id] = record;
      const row = el('div', 'ge-item'),
        label = el('label'),
        checkbox = el('input');
      checkbox.type = 'checkbox';
      checkbox.checked = record.completed === true;
      checkbox.id = `ge-${id}`;
      checkbox.setAttribute('aria-label', `Mark Cal-GETC ${id} ${title} completed`);
      checkbox.addEventListener('change', () => {
        record.completed = checkbox.checked;
        save();
        updateGeProgress();
      });
      label.append(checkbox, document.createTextNode(`${id} · ${title}`));
      const courseLabel = el('label', 'sr-only', `Search approved courses for Cal-GETC ${id}`);
      const course = el('input');
      course.id = `ge-course-${id}`;
      courseLabel.htmlFor = course.id;
      course.type = 'search';
      course.autocomplete = 'off';
      course.disabled = geLoading || geLoadError;
      course.maxLength = 160;
      course.placeholder = id === '5C' ? 'Search labs or lab-inclusive courses…' : 'Search course code or title…';
      course.value = typeof record.course === 'string' ? record.course : '';
      course.setAttribute('role', 'combobox');
      course.setAttribute('aria-autocomplete', 'list');
      course.setAttribute('aria-expanded', 'false');
      course.setAttribute('aria-controls', `ge-options-${id}`);
      course.setAttribute('aria-describedby', `ge-hint-${id}`);
      const wrap = el('div', 'combo-wrap'),
        list = el('div', 'combo-options');
      list.id = `ge-options-${id}`;
      list.hidden = true;
      list.setAttribute('role', 'listbox');
      list.setAttribute('aria-label', `Approved options for Cal-GETC ${id}`);
      const hint = el('p', 'field-hint ge-course-hint');
      hint.id = `ge-hint-${id}`;
      const combo = createCombobox(course, list, () => geSuggestions(id, record.selectedCode === record.course ? '' : course.value), item => {
        if (geConflict(item.course, id)) return false;
        if (record.selectedCode !== item.id) record.completed = false;
        record.selectedCode = item.id;
        record.course = item.id;
        course.value = item.id;
        save();
        updateGeSelectionHints();
        updateGeProgress();
      }, {
        statusId: 'geSuggestionStatus',
        emptyMessage: 'No approved courses match this search in this area. Try a subject, course code, or another title.'
      });
      geCombos.push(combo);
      course.addEventListener('input', () => {
        record.course = course.value;
        delete record.selectedCode;
        record.completed = false;
        save();
        updateGeSelectionHints();
        updateGeProgress();
        combo.render();
      });
      wrap.append(course, list);
      row.append(label, courseLabel, wrap, hint);
      section.append(row);
    });
    fragment.append(section);
  });
  $('geAreas').replaceChildren(fragment);
  updateGeSelectionHints();
  updateGeProgress();
}

renderCalGetc();
$('geRetry').addEventListener('click', loadGeCourses);
loadGeCourses();

let gePrintState = [];
window.addEventListener('beforeprint', () => {
  gePrintState = [...document.querySelectorAll('.ge-area')].map(node => [node, node.open]);
  gePrintState.forEach(([node]) => {
    node.open = true;
  });
});
window.addEventListener('afterprint', () => {
  gePrintState.forEach(([node, wasOpen]) => {
    node.open = wasOpen;
  });
  gePrintState = [];
});
