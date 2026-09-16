'use strict';
(function (root) {
  const defaults = {
    send: 'Ctrl+S',
    profile: 'Ctrl+Shift+S',
    tags: 'Alt+T',
    calendar: 'Alt+D',
    share: 'Alt+L'
  };
  const labels = {
    send: 'Auftrag an Paperless senden',
    profile: 'Zuordnung als Profil speichern',
    tags: 'Tagsuche fokussieren',
    calendar: 'Kalender öffnen',
    share: 'Öffentlichen Link umschalten'
  };
  function normalize(value) {
    if (!String(value || '').trim()) return '';
    const parts = String(value)
      .trim()
      .replace(/strg/gi, 'Ctrl')
      .split('+')
      .map((x) => x.trim().toUpperCase());
    const key = parts.pop(),
      mods = new Set(parts);
    if (
      parts.length !== mods.size ||
      parts.some((x) => !['CTRL', 'ALT', 'SHIFT'].includes(x)) ||
      (!mods.has('CTRL') && !mods.has('ALT')) ||
      (mods.has('CTRL') && mods.has('ALT')) ||
      !/^([A-Z0-9]|ENTER)$/.test(key || '')
    )
      throw new Error(
        'Strg oder Alt, optional Umschalt, plus Buchstabe, Ziffer oder Enter verwenden.'
      );
    const result = ['CTRL', 'ALT', 'SHIFT']
      .filter((x) => mods.has(x))
      .map((x) => ({ CTRL: 'Ctrl', ALT: 'Alt', SHIFT: 'Shift' })[x])
      .concat(key === 'ENTER' ? 'Enter' : key)
      .join('+');
    if (
      [
        'Ctrl+C',
        'Ctrl+V',
        'Ctrl+X',
        'Ctrl+A',
        'Ctrl+Z',
        'Ctrl+Y',
        'Ctrl+W',
        'Ctrl+Q',
        'Ctrl+T',
        'Ctrl+N',
        'Ctrl+L'
      ].includes(result)
    )
      throw new Error(
        'Dieses Kürzel ist für grundlegende Browser- oder Textfunktionen reserviert.'
      );
    return result;
  }
  function validate(raw = {}) {
    const out = {},
      seen = new Set();
    for (const key of Object.keys(defaults)) {
      const value = normalize(
        raw[key] === undefined ? defaults[key] : raw[key]
      );
      if (value && seen.has(value))
        throw new Error('Tastenkürzel doppelt vergeben: ' + value);
      if (value) seen.add(value);
      out[key] = value;
    }
    return out;
  }
  function eventKey(e) {
    if (e.isComposing || e.metaKey || e.getModifierState?.('AltGraph'))
      return '';
    try {
      return normalize(
        [
          e.ctrlKey ? 'Ctrl' : '',
          e.altKey ? 'Alt' : '',
          e.shiftKey ? 'Shift' : '',
          e.key
        ]
          .filter(Boolean)
          .join('+')
      );
    } catch (_) {
      return '';
    }
  }
  function nextStop(stops, target, backward) {
    const index = stops.indexOf(target);
    if (index >= 0) return stops[index + (backward ? -1 : 1)] || null;
    return (
      (backward ? [...stops].reverse() : stops).find(
        (node) => !!(target.compareDocumentPosition(node) & (backward ? 2 : 4))
      ) || null
    );
  }
  root.Shortcuts = {
    defaults,
    labels,
    normalize,
    validate,
    eventKey,
    nextStop
  };
})(globalThis);
