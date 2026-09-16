'use strict';
(function (root) {
  function dateOnly(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
    if (!match || Number(match[1]) < 1)
      throw new Error('Bitte ein gültiges Datum ohne Uhrzeit eingeben.');
    const [year, month, day] = match.slice(1).map(Number),
      date = new Date(0);
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCFullYear(year, month - 1, day);
    if (
      date.getUTCFullYear() !== year ||
      date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day
    )
      throw new Error('Bitte ein gültiges Kalenderdatum eingeben.');
    return date;
  }
  function documentDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return { display: '', iso: '' };
    let match,
      day,
      month,
      year,
      hour = '00',
      minute = '00';
    if ((match = /^(\d{2})(\d{2})(\d{2}|\d{4})$/.exec(raw)))
      [, day, month, year] = match;
    else if (
      (match =
        /^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})(?:[ T](\d{1,2}):(\d{2}))?$/.exec(
          raw
        ))
    ) {
      [, day, month, year] = match;
      hour = match[4] || '00';
      minute = match[5] || '00';
    } else if (
      (match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/.exec(raw))
    ) {
      [, year, month, day] = match;
      hour = match[4] || '00';
      minute = match[5] || '00';
    } else
      throw new Error('Dokumentdatum: z. B. 220826 oder 22.08.2026 eingeben.');
    if (year.length === 2) year = '20' + year;
    day = day.padStart(2, '0');
    month = month.padStart(2, '0');
    hour = hour.padStart(2, '0');
    dateOnly(`${year}-${month}-${day}`);
    if (Number(hour) > 23 || Number(minute) > 59)
      throw new Error('Dokumentdatum: ungültige Uhrzeit.');
    const local = new Date(0);
    local.setFullYear(Number(year), Number(month) - 1, Number(day));
    local.setHours(Number(hour), Number(minute), 0, 0);
    if (
      local.getHours() !== Number(hour) ||
      local.getMinutes() !== Number(minute)
    )
      throw new Error(
        'Diese lokale Uhrzeit existiert wegen der Zeitumstellung nicht.'
      );
    return {
      display:
        `${day}.${month}.${year}` +
        (hour !== '00' || minute !== '00' ? ` ${hour}:${minute}` : ''),
      iso: local.toISOString()
    };
  }
  function today(now = new Date()) {
    return `${String(now.getFullYear()).padStart(4, '0')}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  function shiftDate(value, period, now = new Date()) {
    const date = dateOnly(value || today(now));
    if (period === 'month') {
      const day = date.getUTCDate();
      date.setUTCDate(1);
      date.setUTCMonth(date.getUTCMonth() + 1);
      const last = new Date(date);
      last.setUTCMonth(last.getUTCMonth() + 1);
      last.setUTCDate(0);
      date.setUTCDate(Math.min(day, last.getUTCDate()));
    } else if (period === '4w' || period === '6w')
      date.setUTCDate(date.getUTCDate() + (period === '4w' ? 28 : 42));
    else throw new Error('Unbekannter Zeitraum.');
    if (date.getUTCFullYear() > 9999)
      throw new Error('Das Datum liegt außerhalb des unterstützten Bereichs.');
    return date.toISOString().slice(0, 10);
  }
  function cleanMap(raw) {
    if (raw === undefined) return {};
    if (!raw || typeof raw !== 'object' || Array.isArray(raw))
      throw new Error('Ungültige benutzerdefinierte Felder.');
    const out = {};
    for (const [id, value] of Object.entries(raw)) {
      if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id)))
        throw new Error('Ungültige Custom-Field-ID.');
      if (value === undefined || value === '') continue;
      if (
        value === null ||
        typeof value === 'boolean' ||
        (typeof value === 'string' && value.length <= 20000) ||
        (typeof value === 'number' && Number.isFinite(value))
      )
        out[id] = value;
      else if (
        Array.isArray(value) &&
        value.every((n) => Number.isSafeInteger(n) && n > 0)
      )
        out[id] = [...new Set(value)];
      else
        throw new Error(`Ungültiger Wert für benutzerdefiniertes Feld ${id}.`);
    }
    return out;
  }
  function normalize(field, value) {
    if (value === undefined || value === '' || value === null)
      return value === null ? null : undefined;
    const text = String(value).trim();
    switch (field.data_type) {
      case 'date':
        dateOnly(text);
        return text;
      case 'boolean':
        if (value === true || value === 'true') return true;
        if (value === false || value === 'false') return false;
        throw new Error('Bitte Ja oder Nein auswählen.');
      case 'integer': {
        if (!/^-?\d+$/.test(text))
          throw new Error('Bitte eine ganze Zahl eingeben.');
        const n = Number(text);
        if (!Number.isInteger(n) || n < -2147483648 || n > 2147483647)
          throw new Error(
            'Die ganze Zahl liegt außerhalb des unterstützten Bereichs.'
          );
        return n;
      }
      case 'float': {
        const raw = text.replace(',', '.');
        if (
          !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw) ||
          !Number.isFinite(Number(raw))
        )
          throw new Error('Bitte eine gültige Zahl eingeben.');
        return Number(raw);
      }
      case 'monetary': {
        const match = /^([A-Z]{3})?(-?)(\d+)(?:[.,](\d{1,2}))?$/.exec(
          text.toUpperCase().replace(/\s+/g, '')
        );
        if (!match)
          throw new Error(
            'Bitte einen Betrag eingeben, z. B. 1489 für 14.89 oder EUR14,89.'
          );
        let whole = match[3],
          fraction = match[4];
        if (fraction === undefined) {
          const cents = whole.padStart(3, '0');
          whole = cents.slice(0, -2);
          fraction = cents.slice(-2);
        }
        whole = whole.replace(/^0+(?=\d)/, '');
        return (
          (match[1] || '') + match[2] + whole + '.' + fraction.padEnd(2, '0')
        );
      }
      case 'select':
        if (
          !(field.extra_data?.select_options || []).some(
            (option) => String(option.id) === text
          )
        )
          throw new Error('Bitte eine verfügbare Option auswählen.');
        return text;
      case 'documentlink': {
        const values = Array.isArray(value)
          ? value
          : text.split(/[\s,;]+/).filter(Boolean);
        if (
          !values.every(
            (n) =>
              /^[1-9]\d*$/.test(String(n)) && Number.isSafeInteger(Number(n))
          )
        )
          throw new Error('Bitte Dokument-IDs durch Komma trennen.');
        return [...new Set(values.map(Number))];
      }
      case 'url': {
        const url = new URL(text);
        if (!['http:', 'https:', 'ftp:', 'ftps:'].includes(url.protocol))
          throw new Error('Bitte eine vollständige Webadresse eingeben.');
        return text;
      }
      case 'string':
        if (String(value).length > 128)
          throw new Error('Höchstens 128 Zeichen erlaubt.');
        return String(value);
      case 'longtext':
        if (String(value).length > 20000)
          throw new Error('Höchstens 20000 Zeichen erlaubt.');
        return String(value);
      default:
        throw new Error('Dieser Feldtyp wird noch nicht unterstützt.');
    }
  }
  function validate(values, definitions) {
    const clean = cleanMap(values),
      out = {};
    for (const [id, value] of Object.entries(clean)) {
      const field = definitions.find((f) => String(f.id) === id);
      if (!field)
        throw new Error(
          `Benutzerdefiniertes Feld ${id} ist nicht mehr verfügbar. Bitte die Felder aktualisieren.`
        );
      try {
        const result = normalize(field, value);
        if (result !== undefined) out[id] = result;
      } catch (e) {
        throw new Error(`${field.name}: ${e.message}`);
      }
    }
    return out;
  }
  const SearchList = {
    rank(items, query, name = (item) => item.name) {
      const q = query.trim().toLocaleLowerCase('de'),
        text = (item) => String(name(item)).toLocaleLowerCase('de');
      const rank = (item) =>
        text(item) === q ? 0 : text(item).startsWith(q) ? 1 : 2;
      return items
        .filter((item) => text(item).includes(q))
        .sort((a, b) => rank(a) - rank(b));
    },
    paint(input, list, index) {
      input.setAttribute('role', 'combobox');
      input.setAttribute('aria-autocomplete', 'list');
      input.setAttribute('aria-controls', list.id);
      input.setAttribute('aria-expanded', 'true');
      list.setAttribute('role', 'listbox');
      [...list.children].forEach((node, i) => {
        node.id = list.id + '-option-' + i;
        node.setAttribute('role', 'option');
        node.setAttribute('aria-selected', String(i === index));
        node.setAttribute('data-active', String(i === index));
      });
      input.setAttribute(
        'aria-activedescendant',
        list.children[index]?.id || ''
      );
      if (document.activeElement === input)
        list.children[index]?.scrollIntoView?.({ block: 'nearest' });
    },
    Cursor: class {
      constructor() {
        this.index = 0;
      }
      clamp(length, reset) {
        this.index = reset ? 0 : Math.max(0, Math.min(this.index, length - 1));
      }
      key(event, items, choose, render) {
        if (event.isComposing || event.ctrlKey || event.altKey || event.metaKey)
          return;
        if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
        event.preventDefault();
        if (!items.length) return;
        if (event.key === 'Enter') {
          choose(items[this.index] || items[0]);
          return;
        }
        this.index =
          (this.index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) %
          items.length;
        render(false);
      }
    }
  };
  class Editor {
    constructor(container, onError = () => {}) {
      this.container = container;
      this.onError = onError;
      this.entries = new Map();
      this.deckEnabled = false;
      this.selected = new Set();
    }
    setFields(definitions) {
      const prior = this.entries;
      this.entries = new Map();
      this.container.replaceChildren();
      const make = (tag, text = '', cls = '') => {
        const node = document.createElement(tag);
        node.textContent = text;
        node.className = cls;
        return node;
      };
      const search = make('input'),
        chips = make('div', '', 'selected-tags'),
        list = make('div', '', 'tag-list');
      search.setAttribute('data-tab-stop', '');
      search.type = 'search';
      search.placeholder = 'Felder suchen und hinzufügen …';
      search.setAttribute('aria-label', 'Benutzerdefinierte Felder suchen');
      list.id = 'custom-field-options';
      const cursor = new SearchList.Cursor();
      let available = [];
      this.container.append(search, chips, list);
      this.selected = new Set(
        [...this.selected].filter((id) =>
          definitions.some((f) => String(f.id) === id)
        )
      );
      const render = (reset = true) => {
        chips.replaceChildren();
        list.replaceChildren();
        const query = search.value.toLocaleLowerCase('de');
        for (const [id, entry] of this.entries) {
          entry.row.hidden = !this.selected.has(id);
          const toggle = () => {
            if (this.selected.has(id)) {
              this.selected.delete(id);
              entry.input.value = '';
              if (entry.deck) entry.deck.checked = false;
            } else this.selected.add(id);
            render();
          };
          if (this.selected.has(id)) {
            const chip = make('button', entry.field.name + ' ×', 'tag-chip');
            chip.type = 'button';
            chip.addEventListener('click', toggle);
            chips.append(chip);
          }
        }
        available = SearchList.rank(
          [...this.entries].filter(([id]) => !this.selected.has(id)),
          query,
          ([, e]) => e.field.name
        );
        cursor.clamp(available.length, reset);
        for (const [id, entry] of available) {
          const label = make('label', '', 'tag-option'),
            check = make('input');
          check.type = 'checkbox';
          check.checked = false;
          check.addEventListener('change', () => {
            this.selected.add(id);
            search.value = '';
            render();
            entry.input.focus();
          });
          label.append(check, make('span', entry.field.name));
          list.append(label);
        }
        SearchList.paint(search, list, cursor.index);
        if (!list.children.length)
          list.append(make('p', 'Keine passenden Felder.', 'empty'));
      };
      search.addEventListener('input', render);
      search.addEventListener('keydown', (event) =>
        cursor.key(
          event,
          available,
          ([id, entry]) => {
            this.selected.add(id);
            search.value = '';
            render();
            entry.input.focus();
          },
          render
        )
      );
      for (const field of definitions) {
        if (!Number.isSafeInteger(Number(field.id)) || Number(field.id) <= 0)
          continue;
        const row = make('div', '', 'custom-field'),
          label = make('label', field.name),
          id = 'custom-field-' + field.id;
        const type = field.data_type,
          input = make(
            ['boolean', 'select'].includes(type)
              ? 'select'
              : type === 'longtext'
                ? 'textarea'
                : 'input'
          );
        input.id = id;
        input.setAttribute('data-tab-stop', '');
        label.htmlFor = id;
        row.append(label, input);
        if (type === 'boolean' || type === 'select') {
          const options =
            type === 'boolean'
              ? [
                  { id: 'true', label: 'Ja' },
                  { id: 'false', label: 'Nein' }
                ]
              : field.extra_data?.select_options || [];
          input.append(new Option('Keine Vorgabe', ''));
          for (const option of options)
            input.append(new Option(option.label, String(option.id)));
        } else {
          input.type =
            type === 'date' ? 'date' : type === 'url' ? 'url' : 'text';
          if (type === 'date') {
            input.min = '0001-01-01';
            input.max = '9999-12-31';
          }
          if (type === 'integer' || type === 'float' || type === 'monetary')
            input.inputMode = type === 'integer' ? 'numeric' : 'decimal';
          if (type === 'string') input.maxLength = 128;
          if (type === 'longtext') {
            input.rows = 3;
            input.maxLength = 20000;
          }
          if (type === 'monetary') {
            input.placeholder = '1489 → 14.89';
            input.title =
              'Ohne Dezimaltrennzeichen: Centbetrag, z. B. 1489 → 14.89. Währung optional, z. B. EUR1489.';
            input.addEventListener('change', () => {
              if (!input.value.trim()) return;
              try {
                input.value = normalize(field, input.value);
              } catch (e) {
                this.onError(`${field.name}: ${e.message}`);
              }
            });
          }
          if (type === 'documentlink')
            input.placeholder = 'Dokument-IDs, z. B. 12, 34';
        }
        const old = prior.get(String(field.id));
        input.value = old?.field.data_type === type ? old.input.value : '';
        const entry = { field, input, row };
        this.entries.set(String(field.id), entry);
        if (type === 'date') {
          const actions = make('div', '', 'date-shortcuts');
          for (const [text, period] of [
            ['+4 Wochen', '4w'],
            ['+1 Monat', 'month'],
            ['+6 Wochen', '6w'],
            ['Leeren', '']
          ]) {
            const button = make('button', text, 'secondary');
            button.type = 'button';
            button.addEventListener('click', () => {
              try {
                input.value = period ? shiftDate(input.value, period) : '';
                input.focus();
              } catch (e) {
                this.onError(`${field.name}: ${e.message}`);
              }
            });
            actions.append(button);
          }
          row.append(
            actions,
            make(
              'p',
              'Ab eingetragenem Datum, sonst ab heute. Ohne Uhrzeit.',
              'muted small'
            )
          );
          const deckLabel = make('label', '', 'check deck-check'),
            deck = make('input');
          deck.type = 'checkbox';
          deck.checked = old?.deck?.checked || false;
          deck.disabled = !this.deckEnabled;
          deck.title =
            'Nextcloud in den Einstellungen verbinden und Deck-Board mit Liste speichern';
          deckLabel.append(
            deck,
            make('span', 'Deck-Karte mit diesem Fälligkeitsdatum anlegen')
          );
          row.append(deckLabel);
          entry.deck = deck;
        }
        this.container.append(row);
      }
      this.renderSelection = render;
      render();
    }
    importValues(raw) {
      const values = cleanMap(raw),
        prepared = [];
      for (const [id, value] of Object.entries(values)) {
        const entry = this.entries.get(id);
        if (!entry)
          throw new Error(
            `Benutzerdefiniertes Feld ${id} ist nicht verfügbar.`
          );
        // Stored monetary values are amounts, whereas newly typed digits mean cents.
        let input = value;
        if (
          entry.field.data_type === 'monetary' &&
          value !== null &&
          /^([A-Z]{3})?-?\d+$/.test(String(value))
        )
          input = String(value) + '.00';
        const normalized = normalize(entry.field, input);
        prepared.push({
          id,
          entry,
          text:
            normalized == null
              ? ''
              : Array.isArray(normalized)
                ? normalized.join(', ')
                : String(normalized)
        });
      }
      for (const { id, entry, text } of prepared) {
        this.selected.add(id);
        entry.input.value = text;
      }
      this.renderSelection?.();
    }
    resetValues() {
      for (const entry of this.entries.values()) entry.input.value = '';
    }
    setDeckEnabled(enabled) {
      this.deckEnabled = !!enabled;
      for (const entry of this.entries.values())
        if (entry.deck) entry.deck.disabled = !enabled;
    }
    deckFields() {
      return [...this.entries]
        .filter(([, entry]) => entry.deck?.checked)
        .map(([id, entry]) => {
          if (!entry.input.value)
            throw new Error(
              `${entry.field.name}: Für die Deck-Karte ein Datum eingeben.`
            );
          return Number(id);
        });
    }
    read() {
      const values = {},
        definitions = [];
      for (const [id, { field, input }] of this.entries) {
        definitions.push(field);
        if (input.value !== '') values[id] = input.value;
      }
      return validate(values, definitions);
    }
  }
  root.SearchList = SearchList;
  root.CustomFields = {
    documentDate,
    dateOnly,
    today,
    shiftDate,
    cleanMap,
    normalize,
    validate,
    Editor
  };
})(globalThis);
