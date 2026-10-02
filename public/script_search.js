function makeSearchableSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select) {
    console.warn('makeSearchableSelect: select not found:', selectId);
    return;
  }
  

  const isMultiple = select.multiple;

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
  if (selectId === 'districtSelect') {
    wrapper.classList.add('searchable-select-district');
  }
  wrapper.style.boxSizing = 'border-box';

  const display = document.createElement('div');
  display.className = 'selected-display';
  display.innerHTML = `<span class="text"></span><span class="caret">▾</span>`;
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

  function getSelectedLabels(sel) {
    return Array.from(sel.selectedOptions)
      .filter(opt => opt.value)
      .map(opt => opt.textContent || opt.value);
  }

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
    const textEl = w.querySelector('.text');
    const labels = getSelectedLabels(sel);

    if (sel.multiple) {
      if (!labels.length) {
        textEl.textContent = '-- Chọn xã/phường --';
      } else if (labels.length === 1) {
        textEl.textContent = labels[0];
      } else {
        textEl.textContent = `${labels.length} xã/phường đã chọn`;
      }
      return;
    }

    textEl.textContent = sel.options[sel.selectedIndex]?.text || '-- Chọn --';
  }

  // apply initial position
  copyPositionToWrapper(select);
  // hiển thị nhãn/caret ban đầu theo trạng thái đã chọn
  refreshSelectedDisplay(select);

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
    input.placeholder = select.multiple ? 'Tìm xã/phường...' : 'Tìm...';
    input.className = 'search-input';
    dropdown.appendChild(input);

    const ul = document.createElement('ul');
    ul.className = 'options-list';
    dropdown.appendChild(ul);

    function buildList(filter = '') {
      ul.innerHTML = '';
      const filterLower = filter.trim().toLowerCase();
      Array.from(select.options).forEach(opt => {
        if (!opt.value) return; // skip placeholder
        const label = opt.textContent || opt.value;
        if (filterLower && !label.toLowerCase().includes(filterLower)) return;
        const li = document.createElement('li');
        li.dataset.value = opt.value;
        if (select.multiple) {
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.checked = opt.selected;
          checkbox.tabIndex = -1;
          checkbox.style.marginRight = '8px';
          const text = document.createElement('span');
          text.textContent = label;
          li.appendChild(checkbox);
          li.appendChild(text);
        } else {
          li.textContent = label;
        }
        if (opt.selected) li.classList.add('active');
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
        if (!option) return;
        option.selected = !option.selected;
        const checkbox = li.querySelector('input[type="checkbox"]');
        if (checkbox) checkbox.checked = option.selected;
        li.classList.toggle('active', option.selected);
        refreshSelectedDisplay(select);
        select.dispatchEvent(new Event('change', { bubbles: true }));
        return;
      }

      select.value = li.dataset.value;
      refreshSelectedDisplay(select);
      select.dispatchEvent(new Event('change', { bubbles: true }));
      closeDropdown();
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
            if (!option) return;
            option.selected = !option.selected;
            const checkbox = cur.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = option.selected;
            refreshSelectedDisplay(select);
            select.dispatchEvent(new Event('change', { bubbles: true }));
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
