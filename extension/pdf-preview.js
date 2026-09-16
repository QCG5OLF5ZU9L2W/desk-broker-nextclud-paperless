'use strict';
// Firefox renders validated PDF bytes in an isolated frame. No renderer is bundled.
class PdfPreview {
  constructor(P) {
    this.P = P;
    this.cache = new Map();
    this.bindings = new Set();
    this.active = null;
    this.context = '';
    this.generation = 0;
    window.addEventListener(
      'wheel',
      (e) => {
        const b = this.current();
        if (!b || e.ctrlKey || e.altKey || e.metaKey || !e.deltaY) return;
        e.preventDefault();
        e.stopPropagation();
        const now = Date.now();
        if (now - (b.lastWheel || 0) < 180) return;
        b.wheel = (b.wheel || 0) + e.deltaY * (e.deltaMode === 1 ? 16 : 1);
        if (Math.abs(b.wheel) < 24) return;
        b.lastWheel = now;
        const delta = b.wheel > 0 ? 1 : -1;
        b.wheel = 0;
        this.turn(b, delta);
      },
      { capture: true, passive: false }
    );
    window.addEventListener(
      'keydown',
      (e) => {
        const b = this.current();
        if (
          !b ||
          e.isComposing ||
          e.ctrlKey ||
          e.altKey ||
          e.metaKey ||
          e.target.closest?.('input,textarea,select,[contenteditable="true"]')
        )
          return;
        const moves = {
          ArrowRight: 1,
          ArrowDown: 1,
          PageDown: 1,
          ArrowLeft: -1,
          ArrowUp: -1,
          PageUp: -1
        };
        if (!(e.key in moves)) return;
        e.preventDefault();
        e.stopPropagation();
        this.turn(b, moves[e.key]);
      },
      true
    );
    window.addEventListener('unload', () => this.clear());
  }
  current() {
    const visible = (b) =>
      b.trigger.isConnected &&
      b.trigger.matches(':hover,:focus-visible') &&
      !b.trigger.hasAttribute('data-preview-dismissed') &&
      !b.trigger.hasAttribute('data-zoom-dismissed');
    if (this.active && visible(this.active)) return this.active;
    this.active = [...this.bindings].find(visible) || null;
    return this.active;
  }
  reset(binding) {
    clearTimeout(binding.timer);
    clearTimeout(binding.loadTimer);
    binding.frame.onload = null;
    binding.ready = false;
    binding.frame.remove();
    binding.frame.removeAttribute('src');
    binding.frame.hidden = true;
    binding.entry = null;
    binding.placeholder.hidden = false;
    binding.wanted = 1;
    delete binding.box.dataset.page;
    delete binding.box.dataset.pages;
    binding.footer.textContent = 'Seite 1 · PDF wird beim Verweilen geladen …';
  }
  dispose(entry) {
    entry.disposed = true;
    for (const binding of this.bindings)
      if (binding.entry === entry) this.reset(binding);
    if (entry.url) URL.revokeObjectURL(entry.url);
  }
  clear() {
    this.generation++;
    for (const entry of this.cache.values()) this.dispose(entry);
    this.cache.clear();
    for (const binding of this.bindings) {
      this.reset(binding);
      if (!binding.trigger.isConnected) this.bindings.delete(binding);
    }
    this.active = null;
  }
  sync(state) {
    const key = JSON.stringify([
      state.config.base,
      state.unlocked,
      state.previewRevision
    ]);
    if (key !== this.context) {
      this.clear();
      this.context = key;
    }
  }
  attach(trigger, box, placeholder, id, base) {
    if (!Number.isSafeInteger(id) || id <= 0) return;
    for (const prior of this.bindings)
      if (!prior.trigger.isConnected) {
        this.reset(prior);
        this.bindings.delete(prior);
      }
    box.classList.add('pdf-pager');
    const body = document.createElement('span'),
      frame = document.createElement('iframe'),
      footer = document.createElement('span');
    body.className = 'pdf-page-body';
    frame.className = 'pdf-page-frame';
    frame.title = 'PDF-Seitenvorschau';
    frame.tabIndex = -1;
    frame.hidden = true;
    // The built-in viewer needs scripts. The frame gets no add-on origin,
    // forms, popups, downloads or permission to navigate the parent window.
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.setAttribute('referrerpolicy', 'no-referrer');
    footer.className = 'pdf-page-footer';
    footer.textContent = 'Seite 1 · PDF wird beim Verweilen geladen …';
    body.append(placeholder);
    box.append(body, footer);
    const binding = {
      trigger,
      box,
      placeholder,
      body,
      frame,
      footer,
      id,
      base,
      wanted: 1,
      entry: null,
      timer: null
    };
    this.bindings.add(binding);
    const start = () => {
      this.active = binding;
      clearTimeout(binding.timer);
      binding.timer = setTimeout(
        () => {
          if (this.current() === binding) void this.load(binding);
        },
        binding.entry?.url ? 0 : 180
      );
    };
    const leave = () => {
      clearTimeout(binding.timer);
      if (this.active === binding) this.active = null;
    };
    trigger.addEventListener('mouseenter', start);
    trigger.addEventListener('focus', start);
    trigger.addEventListener('mouseleave', leave);
    trigger.addEventListener('blur', leave);
  }
  async load(binding) {
    let generation = this.generation;
    try {
      const state = await this.P.state(),
        wanted = binding.wanted;
      this.sync(state);
      binding.wanted = wanted;
      if (this.current() !== binding) return;
      if (
        !state.unlocked ||
        (binding.base && state.config.base !== binding.base)
      )
        throw new Error('Sitzung gesperrt.');
      // Do not turn a hover into a download when the user disabled the viewer.
      if (!navigator.pdfViewerEnabled) {
        binding.footer.textContent =
          'Weitere Seiten: PDF-Anzeige in Firefox aktivieren.';
        return;
      }
      generation = this.generation;
      const base = binding.base || state.config.base,
        key = base + '|' + binding.id;
      let entry = this.cache.get(key);
      if (!entry) {
        entry = { url: null, pages: null, disposed: false };
        this.cache.set(key, entry);
        entry.promise = (async () => {
          const [blob, count] = await Promise.all([
            this.P.documentPDF(binding.id, base),
            this.P.documentPageCount(binding.id, base).catch(() => null)
          ]);
          if (!blob || entry.disposed || generation !== this.generation)
            throw new Error('PDF nicht verfügbar.');
          entry.pages = Number.isSafeInteger(count) && count > 0 ? count : null;
          entry.url = URL.createObjectURL(blob);
        })();
        entry.promise.catch(() => {
          if (this.cache.get(key) === entry) this.cache.delete(key);
          this.dispose(entry);
        });
        while (this.cache.size > 3) {
          const [oldKey, old] = this.cache.entries().next().value;
          this.cache.delete(oldKey);
          this.dispose(old);
        }
      } else {
        this.cache.delete(key);
        this.cache.set(key, entry);
      }
      binding.entry = entry;
      binding.footer.textContent = 'PDF wird geladen …';
      await entry.promise;
      if (generation !== this.generation || this.current() !== binding) return;
      this.render(binding);
    } catch (error) {
      if (generation === this.generation && binding.trigger.isConnected)
        binding.footer.textContent =
          'Weitere Seiten nicht verfügbar · erneut darüberfahren';
    }
  }
  turn(binding, delta) {
    binding.wanted = Math.max(
      1,
      Math.min(
        binding.entry?.pages || Number.MAX_SAFE_INTEGER,
        binding.wanted + delta
      )
    );
    clearTimeout(binding.timer);
    if (binding.entry?.url && !binding.entry.disposed) this.render(binding);
    else void this.load(binding);
  }
  render(binding) {
    const entry = binding.entry;
    if (!entry?.url || entry.disposed) return;
    binding.wanted = Math.max(
      1,
      Math.min(entry.pages || Number.MAX_SAFE_INTEGER, binding.wanted)
    );
    // Only the fragment changes when turning a page. The PDF is fetched once.
    // A fresh fragment also restores page position after a hidden hover frame
    // becomes visible again. Firefox may otherwise retain an old scroll offset.
    // This uses ordinary PDF navigation, never the viewer's privileged DOM/API.
    const url =
      entry.url +
      '#page=' +
      binding.wanted +
      '&zoom=Fit&pagemode=none&preview=' +
      (binding.navigation = (binding.navigation || 0) + 1);
    if (!binding.frame.isConnected) {
      binding.ready = false;
      binding.frame.onload = () => {
        if (entry.disposed || binding.entry !== entry) return;
        binding.ready = true;
        clearTimeout(binding.loadTimer);
        this.render(binding);
      };
      binding.frame.setAttribute('src', url);
      binding.body.append(binding.frame);
      binding.loadTimer = setTimeout(() => {
        if (!binding.ready && binding.entry === entry)
          binding.footer.textContent =
            'Weitere Seiten: PDFs in Firefox mit „In Firefox öffnen“ anzeigen.';
      }, 8000);
    } else if (binding.frame.getAttribute('src') !== url) {
      binding.frame.setAttribute('src', url);
    }
    binding.frame.hidden = !binding.ready;
    binding.placeholder.hidden = binding.ready;
    binding.box.dataset.page = String(binding.wanted);
    if (entry.pages) binding.box.dataset.pages = String(entry.pages);
    if (!binding.ready) {
      binding.footer.textContent = 'PDF wird geladen …';
      return;
    }
    binding.footer.textContent = entry.pages
      ? `Seite ${binding.wanted} von ${entry.pages} · Mausrad / ← →`
      : 'Mausrad / ← → · Seitenzahl in der PDF-Anzeige';
  }
}
