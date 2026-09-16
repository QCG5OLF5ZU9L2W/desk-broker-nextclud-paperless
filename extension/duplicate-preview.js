'use strict';
// Hover-only previews of existing documents. No upload, public link or clipboard action.
class DuplicatePreview {
  constructor(P) {
    this.pages = new PdfPreview(P);
    this.P = P;
    this.cache = new Map();
    this.context = '';
    this.generation = 0;
    this.active = null;
    this.interaction = 0;
    window.addEventListener(
      'keydown',
      (e) => {
        if (e.key === 'Escape' && this.active) {
          e.preventDefault();
          e.stopPropagation();
          this.interaction++;
          this.active.dataset.previewDismissed = 'true';
          this.active = null;
        }
      },
      true
    );
    const reposition = () => {
      if (this.active) this.position(this.active);
    };
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('blur', () => {
      this.interaction++;
      if (this.active) this.active.dataset.previewDismissed = 'true';
      this.active = null;
    });
    const timer = setInterval(() => {
      if (this.active)
        void this.P.state()
          .then((s) => this.sync(s))
          .catch(() => this.clear());
    }, 750);
    window.addEventListener('unload', () => {
      clearInterval(timer);
      this.clear();
    });
  }
  clear() {
    this.pages.clear();
    this.generation++;
    for (const item of this.cache.values())
      if (item.url) URL.revokeObjectURL(item.url);
    this.cache.clear();
    for (const link of document.querySelectorAll(
      '.duplicate-preview-trigger'
    )) {
      link.dataset.previewDismissed = 'true';
      const img = link.querySelector('.duplicate-thumb-image');
      if (img) {
        img.hidden = true;
        img.removeAttribute('src');
      }
    }
    this.active = null;
  }
  sync(state) {
    this.pages.sync(state);
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
  position(link) {
    const box = link.querySelector('.duplicate-thumb'),
      r = link.getBoundingClientRect();
    const width = Math.min(300, window.innerWidth - 24),
      height = Math.min(420, window.innerHeight - 24);
    let left = r.right + 12;
    if (left + width > window.innerWidth - 12) left = r.left - width - 12;
    left = Math.max(12, Math.min(left, window.innerWidth - width - 12));
    const top = Math.max(12, Math.min(r.top, window.innerHeight - height - 12));
    Object.assign(box.style, {
      left: left + 'px',
      top: top + 'px',
      width: width + 'px',
      height: height + 'px'
    });
  }
  bind(link, id, base) {
    if (!Number.isSafeInteger(id) || id <= 0) return;
    link.classList.add('duplicate-preview-trigger');
    const box = document.createElement('span'),
      img = document.createElement('img'),
      status = document.createElement('span');
    box.className = 'duplicate-thumb';
    box.setAttribute('aria-hidden', 'true');
    img.className = 'duplicate-thumb-image';
    img.alt = '';
    img.hidden = true;
    status.className = 'duplicate-thumb-status';
    status.textContent = 'Vorschau wird geladen …';
    box.append(img, status);
    link.append(box);
    this.pages.attach(link, box, img, id, base);
    const load = async () => {
      const interaction = ++this.interaction;
      delete link.dataset.previewDismissed;
      this.active = link;
      this.position(link);
      const state = await this.P.state();
      this.sync(state);
      // sync can invalidate older images, so reactivate only if the pointer/focus is still here.
      if (
        interaction !== this.interaction ||
        !link.isConnected ||
        !link.matches(':hover,:focus-visible')
      )
        return;
      delete link.dataset.previewDismissed;
      this.active = link;
      if (!state.unlocked || state.config.base !== base) {
        img.hidden = true;
        status.hidden = false;
        status.textContent =
          'Vorschau erst mit verbundener Paperless-Sitzung verfügbar.';
        return;
      }
      const generation = this.generation,
        key = base + '|' + id;
      let item = this.cache.get(key);
      if (!item) {
        item = { url: null };
        this.cache.set(key, item);
        item.promise = this.P.documentThumbnail(id, base)
          .then((blob) => {
            if (!blob || generation !== this.generation) return null;
            item.url = URL.createObjectURL(blob);
            return item.url;
          })
          .catch(() => null);
      }
      const url = await item.promise;
      if (generation !== this.generation || !link.isConnected) return;
      if (!url) {
        if (this.cache.get(key) === item) this.cache.delete(key);
        img.hidden = true;
        status.hidden = false;
        status.textContent = 'Vorschau nicht verfügbar.';
        return;
      }
      img.onload = () => {
        if (generation === this.generation) {
          img.hidden = false;
          status.hidden = true;
        }
      };
      img.onerror = () => {
        img.hidden = true;
        status.hidden = false;
        status.textContent = 'Vorschau nicht verfügbar.';
      };
      if (img.src !== url) img.src = url;
      else if (img.complete && img.naturalWidth) {
        img.hidden = false;
        status.hidden = true;
      }
    };
    const start = () => {
      void load().catch(() => {
        status.textContent = 'Vorschau nicht verfügbar.';
      });
    };
    link.addEventListener('mouseenter', start);
    link.addEventListener('focus', start);
    const leave = () => {
      this.interaction++;
      if (this.active === link) this.active = null;
      delete link.dataset.previewDismissed;
    };
    link.addEventListener('mouseleave', leave);
    link.addEventListener('blur', leave);
  }
}
