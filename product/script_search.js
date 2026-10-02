function makeSearchableSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select) {
    console.warn('makeSearchableSelect: select not found:', selectId);
    return;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getSelectedOptions(sel) {
    return Array.from(sel.selectedOptions || []).filter(opt => opt.value);
  }

  function getDisplayText(sel) {
    const selected = getSelectedOptions(sel);
    if (!sel.multiple) {
      return sel.options[sel.selectedIndex]?.text || '-- Chọn xã/phường --';
    }
    if (!selected.length) {
      return '-- Chọn xã/phường --';
    }
    return `Đã chọn ${selected.length} xã/phường`;
  }

  function setOptionSelected(sel, value, checked) {
    const option = Array.from(sel.options).find(opt => opt.value === value);
    if (!option || option.disabled) return;
    option.selected = checked;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // nếu đã init thì refresh hiển thị và cập nhật vị trí
  if (select._searchableWrapper) {
    refreshSelectedDisplay(select);
    // cập nhật vị trí (nếu CSS thay đổi)
    copyPositionToWrapper(select);
    return;
  }

  // ẩn select gốc
  select.classList.add('hidden-native-select');

  // tạo wrapper
  const wrapper = document.createElement('div');
  wrapper.className = 'searchable-select map-btn';
  wrapper.style.boxSizing = 'border-box';

  const display = document.createElement('div');
  display.className = 'selected-display';
  display.innerHTML = `<span class="text">${escapeHtml(getDisplayText(select))}</span><span class="caret">▾</span>`;
  wrapper.appendChild(display);

  // copy font style từ select gốc
  const cs = window.getComputedStyle(select);
  wrapper.style.fontFamily = cs.fontFamily;
  wrapper.style.fontSize = cs.fontSize;
  wrapper.style.fontWeight = cs.fontWeight;
  wrapper.style.color = cs.color;
  display.style.fontFamily = cs.fontFamily;
  display.style.fontSize = cs.fontSize;
  display.style.fontWeight = cs.fontWeight;
  display.style.color = cs.color;

  // insert wrapper ngay trước select (giữ cấu trúc DOM)
  select.parentNode.insertBefore(wrapper, select);

  // lưu tham chiếu
  select._searchableWrapper = wrapper;
  select._searchableDropdown = null;

  // Giữ wrapper trong flow của panel controls, cùng độ rộng với select tỉnh
  function copyPositionToWrapper(sel) {
    const w = sel._searchableWrapper;
    if (!w) return;
    w.style.position = 'relative';
    w.style.left = '';
    w.style.top = '';
    w.style.width = '100%';
    w.style.maxWidth = '100%';
    w.style.zIndex = '1';
  }

  function refreshSelectedDisplay(sel) {
    const w = sel._searchableWrapper;
    if (!w) return;
    const txt = getDisplayText(sel);
    w.querySelector('.text').textContent = txt;
  }

  // apply initial position
  copyPositionToWrapper(select);

  // open dropdown function (giống code trước)
  function openDropdown() {
    if (select._searchableDropdown) {
      const inp = select._searchableDropdown.querySelector('.search-input');
      inp && inp.focus();
      return;
    }

    const dropdown = document.createElement('div');
    dropdown.className = 'searchable-dropdown';

    dropdown.style.fontFamily = cs.fontFamily;
    dropdown.style.fontSize = cs.fontSize;
    dropdown.style.fontWeight = cs.fontWeight;
    dropdown.style.color = cs.color;

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Tìm...';
    input.className = 'search-input';
    dropdown.appendChild(input);

    const ul = document.createElement('ul');
    ul.className = 'options-list';
    dropdown.appendChild(ul);

    function buildList(filter = '') {
      ul.innerHTML = '';
      const filterLower = filter.trim().toLowerCase();
      Array.from(select.options).forEach(opt => {
        if (!opt.value || opt.disabled) return; // skip placeholder
        const label = opt.textContent || opt.value;
        if (filterLower && !label.toLowerCase().includes(filterLower)) return;
        const li = document.createElement('li');
        li.dataset.value = opt.value;
        if (select.multiple) {
          li.innerHTML = `
            <label class="option-row">
              <input type="checkbox" ${opt.selected ? 'checked' : ''} />
              <span>${escapeHtml(label)}</span>
            </label>
          `;
        } else {
          li.textContent = label;
          if (opt.selected) li.classList.add('active');
        }
        ul.appendChild(li);
      });
      if (!ul.childElementCount) {
        const li = document.createElement('li');
        li.style.pointerEvents = 'none';
        li.style.opacity = '0.6';
        li.textContent = 'Không tìm thấy';
        ul.appendChild(li);
      }
    }

    buildList();

    document.body.appendChild(dropdown);

    // position dropdown under wrapper (uses wrapper rect)
    const rect = wrapper.getBoundingClientRect();
    dropdown.style.width = rect.width + 'px';
    dropdown.style.minWidth = rect.width + 'px';
    let top = rect.bottom + window.scrollY + 4;
    let left = rect.left + window.scrollX;
    const ddHeight = 300;
    if (top + ddHeight > window.scrollY + window.innerHeight) {
      top = rect.top + window.scrollY - ddHeight - 4;
      if (top < 0) top = rect.bottom + window.scrollY + 4;
    }
    dropdown.style.left = left + 'px';
    dropdown.style.top = top + 'px';

    select._searchableDropdown = dropdown;
    input.focus();

    input.addEventListener('input', () => buildList(input.value));

    ul.addEventListener('click', (ev) => {
      const li = ev.target.closest('li');
      if (!li || !li.dataset.value) return;
      if (select.multiple) {
        const option = Array.from(select.options).find(opt => opt.value === li.dataset.value);
        if (!option || option.disabled) return;
        option.selected = !option.selected;
        refreshSelectedDisplay(select);
        buildList(input.value);
        select.dispatchEvent(new Event('change', { bubbles: true }));
      } else {
        select.value = li.dataset.value;
        refreshSelectedDisplay(select);
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeDropdown();
      }
    });

    let focusedIndex = 0;
    function focusItem(idx) {
      const items = ul.querySelectorAll('li');
      if (!items.length) return;
      items.forEach(it => it.classList.remove('active'));
      focusedIndex = Math.max(0, Math.min(items.length - 1, idx));
      const cur = items[focusedIndex];
      cur && cur.classList.add('active');
      cur && cur.scrollIntoView({ block: 'nearest' });
    }

    input.addEventListener('keydown', (ev) => {
      const items = ul.querySelectorAll('li');
      if (!items.length) return;
      if (ev.key === 'ArrowDown') { ev.preventDefault(); focusItem(focusedIndex + 1); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); focusItem(focusedIndex - 1); }
      else if (ev.key === 'Enter') {
        ev.preventDefault();
        const cur = ul.querySelectorAll('li')[focusedIndex];
        if (cur && cur.dataset.value) {
          if (select.multiple) {
            const option = Array.from(select.options).find(opt => opt.value === cur.dataset.value);
            if (option && !option.disabled) {
              option.selected = !option.selected;
              refreshSelectedDisplay(select);
              buildList(input.value);
              select.dispatchEvent(new Event('change', { bubbles: true }));
            }
          } else {
            select.value = cur.dataset.value;
            refreshSelectedDisplay(select);
            select.dispatchEvent(new Event('change', { bubbles: true }));
            closeDropdown();
          }
        }
      } else if (ev.key === 'Escape') { ev.preventDefault(); closeDropdown(); }
    });

    function onDocClick(e) {
      if (dropdown.contains(e.target) || wrapper.contains(e.target)) return;
      closeDropdown();
    }
    document.addEventListener('mousedown', onDocClick);

    function closeDropdown() {
      if (select._searchableDropdown) {
        document.removeEventListener('mousedown', onDocClick);
        try { select._searchableDropdown.remove(); } catch (err) {}
        select._searchableDropdown = null;
      }
    }
    select._closeSearchableDropdown = closeDropdown;
  }

  wrapper.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (select._searchableDropdown) {
      select._closeSearchableDropdown && select._closeSearchableDropdown();
    } else {
      openDropdown();
    }
  });

  select.addEventListener('change', () => refreshSelectedDisplay(select));

  // nếu window resize hoặc style change, cập nhật vị trí wrapper
  window.addEventListener('resize', () => copyPositionToWrapper(select));
}
