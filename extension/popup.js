'use strict';
(async () => {
  const P = (await browser.runtime.getBackgroundPage()).Paperless;
  const duplicatePreviews = new DuplicatePreview(P);
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, cls = '') => {
    const n = document.createElement(tag);
    n.textContent = text;
    n.className = cls;
    return n;
  };
  const action = async (fn) => {
    try {
      await fn();
    } catch (e) {
      $('error').textContent = e.message;
    }
  };
  const button = (text, fn) => {
    const b = node('button', text, 'quiet');
    b.onclick = () => action(fn);
    return b;
  };
  $('compose').onclick = () =>
    action(async () => {
      await P.openComposer();
      window.close();
    });
  $('settings').onclick = () =>
    action(async () => {
      await P.openPage('settings');
      window.close();
    });
  $('history').onclick = () =>
    action(async () => {
      await P.openPage('history');
      window.close();
    });
  $('lock-session').onclick = () =>
    action(async () => {
      await P.lock();
      await render();
    });
  let signature = '';
  const pendingShares = new Set(),
    thumbnails = new Map();
  let previewContext = '',
    previewGeneration = 0;
  function hideZoom() {
    for (const tile of document.querySelectorAll('.job-thumbnail'))
      tile.dataset.zoomDismissed = 'true';
  }
  window.addEventListener(
    'keydown',
    (event) => {
      if (event.key !== 'Escape') return;
      const active = document.querySelector(
        '.job-thumbnail:not([data-zoom-dismissed]):is(:hover,:focus-visible)'
      );
      if (active) {
        event.preventDefault();
        event.stopPropagation();
        hideZoom();
      }
    },
    true
  );
  window.addEventListener('blur', hideZoom);
  function clearThumbnails() {
    hideZoom();
    previewGeneration++;
    for (const item of thumbnails.values())
      if (item.url) URL.revokeObjectURL(item.url);
    thumbnails.clear();
  }
  function thumbnail(j, top) {
    const link = node('div', '', 'job-thumbnail'),
      img = node('img');
    img.alt = 'PDF-Vorschau: ' + j.name;
    img.width = 120;
    img.height = 160;
    link.hidden = true;
    link.append(img);
    top.append(link);
    const zoom = node('div', '', 'thumbnail-zoom'),
      large = node('img');
    large.alt = '';
    zoom.setAttribute('aria-hidden', 'true');
    zoom.append(large);
    link.append(zoom);
    duplicatePreviews.pages.attach(link, zoom, large, j.documentId, j.base);
    link.onmouseenter =
      link.onfocus =
      link.onmouseleave =
      link.onblur =
        () => {
          delete link.dataset.zoomDismissed;
        };
    const generation = previewGeneration;
    if (!thumbnails.has(j.id)) {
      const item = { url: null, error: '' };
      thumbnails.set(j.id, item);
      item.promise = Promise.resolve()
        .then(() => P.jobThumbnail(j.id))
        .then((blob) => {
          if (
            !blob ||
            generation !== previewGeneration ||
            thumbnails.get(j.id) !== item
          )
            return null;
          item.url = URL.createObjectURL(blob);
          return item.url;
        })
        .catch((e) => {
          item.error = e.message || 'Bildabruf fehlgeschlagen.';
          return null;
        });
    }
    thumbnails.get(j.id).promise.then((url) => {
      if (generation !== previewGeneration) return;
      if (!url) {
        const error = thumbnails.get(j.id)?.error;
        if (error) {
          const hint = node(
            'p',
            'PDF-Vorschau nicht verfügbar: ' + error,
            'muted small thumbnail-error'
          );
          top.append(hint);
        }
        return;
      }
      img.onload = () => {
        if (generation === previewGeneration) {
          link.hidden = false;
          top.classList.add('has-thumbnail');
          link.tabIndex = 0;
          link.setAttribute('aria-label', 'PDF-Vorschau vergrößern: ' + j.name);
          large.src = url;
        }
      };
      img.onerror = () => {
        link.hidden = true;
        top.classList.remove('has-thumbnail');
        top.append(
          node(
            'p',
            'PDF-Vorschau konnte nicht angezeigt werden.',
            'muted small thumbnail-error'
          )
        );
      };
      img.src = url;
    });
  }
  async function render() {
    const state = await P.state();
    duplicatePreviews.sync(state);
    document.documentElement.dataset.theme =
      state.config.theme === 'auto'
        ? matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : state.config.theme;
    $('session').textContent = state.unlocked
      ? 'Sitzung verbunden · Token nur im Speicher'
      : 'Sitzung gesperrt';
    $('lock-session').disabled = !state.unlocked || state.busy;
    const context = JSON.stringify([
      state.unlocked,
      state.config.base,
      state.previewRevision
    ]);
    if (context !== previewContext) {
      clearThumbnails();
      previewContext = context;
    }
    const list = P.jobs().reverse(),
      next = JSON.stringify([context, list, [...pendingShares]]);
    const ids = new Set(list.map((j) => j.id));
    for (const [id, item] of thumbnails)
      if (!ids.has(id)) {
        if (item.url) URL.revokeObjectURL(item.url);
        thumbnails.delete(id);
      }

    $('job-summary').textContent =
      `${list.filter((j) => j.busy).length} laufend · ${list.filter((j) => j.state === 'success').length} archiviert · ${list.filter((j) => ['duplicate', 'check_failed', 'duplicate_rejected', 'pending', 'uncertain', 'failed'].includes(j.state) || j.deckWarning || j.cleanupWarning || j.shareWarning || j.inboxWarning).length} mit Rückmeldung`;
    if (next === signature) return;
    signature = next;
    $('popup-jobs').replaceChildren();
    if (!list.length)
      $('popup-jobs').append(
        node(
          'p',
          'Noch keine Aufträge. Rechtsklick auf eine PDF oder einen PDF-Link → An Paperless senden.',
          'empty'
        )
      );
    const labels = {
      tagging: 'Posteingangs-Tags werden entfernt',
      sharing: 'Freigabelink wird erzeugt',
      checking: 'Dublettenprüfung',
      uploading: 'Wird gesendet',
      processing: 'In Verarbeitung',
      confirming: 'Wird bestätigt',
      deck: 'Deck-Karten werden angelegt',
      cleanup: 'Original wird gelöscht',
      success: 'Archiviert',
      failed: 'Fehlgeschlagen',
      pending: 'Status offen',
      uncertain: 'Ergebnis unklar',
      duplicate: 'Entscheidung erforderlich',
      duplicate_rejected: 'Duplikat abgelehnt',
      check_failed: 'Prüfung fehlgeschlagen',
      cancelled: 'Abgebrochen'
    };
    for (const j of list) {
      const card = node('article', '', 'card job ' + j.state),
        top = node('div', '', 'job-top');
      if (
        state.unlocked &&
        j.state === 'success' &&
        j.documentId &&
        j.documentURL
      )
        thumbnail(j, top);
      top.append(
        node('h3', j.name),
        node(
          'span',
          j.inboxWarning
            ? 'Archiviert · Zuordnung offen'
            : j.shareWarning
              ? 'Archiviert · Freigabe offen'
              : j.deckWarning
                ? 'Archiviert · Deck offen'
                : j.cleanupWarning
                  ? 'Archiviert · Original erhalten'
                  : j.linkCopied
                    ? 'Archiviert · Link kopiert'
                    : labels[j.state] || 'Wartet',
          'badge'
        )
      );
      card.append(top);
      if (j.busy) {
        const progress = document.createElement('progress');
        progress.setAttribute('aria-label', labels[j.state] || 'Auftrag läuft');
        card.append(progress);
      }
      card.append(node('p', j.message || 'Auftrag gestartet.'));
      if (j.linkCopied)
        card.append(
          node(
            'p',
            j.shareURL
              ? 'Öffentlicher Link automatisch kopiert · mit Strg+V einfügen.'
              : 'Paperless-Link automatisch kopiert · mit Strg+V einfügen.',
            'muted small'
          )
        );
      if (j.linkCopyError)
        card.append(node('p', j.linkCopyError, 'muted small'));
      const actions = node('div', '', 'job-actions');
      if (j.documentURL) {
        const a = node('a', 'In Paperless öffnen');
        a.href = j.documentURL;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        actions.append(
          a,
          button('Link kopieren', async () => {
            await P.copyJobLink(j.id);
            await render();
          })
        );
      }
      if (j.shareURL) {
        const a = node('a', 'Öffentliches Dokument öffnen');
        a.href = j.shareURL;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        actions.append(
          a,
          button('Öffentlichen Link kopieren', () => P.copyShareLink(j.id))
        );
      }
      if (
        j.documentURL &&
        j.state === 'success' &&
        !j.shareURL &&
        !j.shareWarning
      ) {
        const panel = node('div', '', 'popup-share'),
          choices = node('div', '', 'popup-share-choices');
        const busy = !!j.busy || !!j.manualShareBusy || pendingShares.has(j.id);
        panel.append(
          node(
            'span',
            busy ? 'Link wird erzeugt …' : 'Öffentlicher Link:',
            'popup-share-label'
          )
        );
        const controls = [];
        for (const [days, label] of [
          [7, '7 Tage'],
          [30, '30 Tage'],
          [0, 'Unbefristet']
        ]) {
          const create = button(label, async () => {
            if (create.disabled || pendingShares.has(j.id)) return;
            pendingShares.add(j.id);
            controls.forEach((b) => {
              b.disabled = true;
            });
            try {
              await P.createJobShare(j.id, { days, archive: false });
              $('error').textContent = '';
            } finally {
              pendingShares.delete(j.id);
              signature = '';
              await render();
            }
          });
          create.type = 'button';
          create.className = 'quiet share-shortcut';
          create.disabled = busy || !state.unlocked;
          create.title = `Öffentlichen Link (${label}) erzeugen und kopieren. Ohne Anmeldung zugänglich.`;
          create.setAttribute(
            'aria-label',
            `Öffentlichen Link für ${label} erzeugen und kopieren`
          );
          controls.push(create);
          choices.append(create);
        }
        panel.append(choices);
        if (!state.unlocked)
          panel.append(
            node(
              'p',
              'Zum Erzeugen zuerst die Sitzung in den Einstellungen entsperren.',
              'muted small'
            )
          );
        card.append(panel);
      }
      if (j.manualShareError)
        card.append(node('p', j.manualShareError, 'error'));
      if (j.inboxWarning) {
        card.append(node('p', j.inboxWarning, 'error'));
        if (!j.busy)
          actions.append(
            button('Posteingangs-Tags erneut entfernen', () =>
              P.retryInbox(j.id)
            )
          );
      }
      if (j.shareWarning) card.append(node('p', j.shareWarning, 'error'));
      if (!j.busy && j.taskId && ['pending', 'uncertain'].includes(j.state))
        actions.append(
          button('Status prüfen', async () => {
            await P.retryStatus(j.id);
            await render();
          })
        );
      if (j.state === 'duplicate') {
        const matches = node('ul', '', 'duplicate-matches');
        for (const match of j.duplicates || []) {
          const item = node('li', '');
          if (match.url) {
            const a = node('a', match.title);
            a.href = match.url;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            duplicatePreviews.bind(a, match.id, j.base);
            item.append(a);
          } else item.textContent = match.title;
          matches.append(item);
        }
        card.append(
          matches,
          node(
            'p',
            'Ja sendet die unveränderte PDF. Paperless muss Duplikate erlauben.',
            'muted small'
          )
        );
        const no = button('Nein, nicht übernehmen', async () => {
          await P.decideDuplicate(j.id, false);
          await render();
        });
        no.className = 'secondary';
        const yes = button('Ja, trotzdem übernehmen', async () => {
          await P.decideDuplicate(j.id, true);
          await render();
        });
        yes.className = 'primary';
        actions.append(no, yes);
      }
      if (j.state === 'check_failed' && !j.busy)
        actions.append(
          button('Prüfung wiederholen', async () => {
            await P.retryCheck(j.id);
            await render();
          })
        );
      for (const item of j.deckLinks || []) {
        const a = node('a', 'Deck: ' + item.name);
        a.href = item.url;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        actions.append(a);
      }
      if (j.deckWarning && !j.busy) {
        actions.append(button('Deck erneut prüfen', () => P.retryDeck(j.id)));
        if (j.deckUncertain)
          actions.append(
            button('Kartenanlage erneut zulassen', async () => {
              if (
                window.confirm(
                  'Die letzte Kartenanlage ist unklar. Bitte zuerst in Deck prüfen. Wenn weiterhin keine passende Karte gefunden wird, erneut anlegen? Es könnte eine zweite Karte entstehen.'
                )
              )
                await P.retryDeck(j.id, true);
            })
          );
      }
      if (j.state === 'success' && j.unread)
        actions.append(
          button('Als gelesen markieren', async () => {
            await P.acknowledgeJob(j.id);
            await render();
          })
        );
      if (!j.busy && !j.manualShareBusy)
        actions.append(
          button('Entfernen', async () => {
            await P.discardJob(j.id);
            await render();
          })
        );
      card.append(actions);
      $('popup-jobs').append(card);
    }
  }
  await render();
  const timer = setInterval(() => action(render), 750);
  window.addEventListener('unload', () => {
    clearInterval(timer);
    clearThumbnails();
  });
})().catch(() => {
  document.getElementById('error').textContent =
    'Hintergrundseite nicht verfügbar. Erweiterung neu laden.';
});
