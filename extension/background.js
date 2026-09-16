'use strict';
/* The UI calls this background page directly. No content scripts, external messages,
   token getters, token logging, or persistent document storage are exposed. */
(() => {
  const C = Core,
    sources = new Map(),
    jobs = new Map(),
    batches = new Map();
  let config,
    catalog = null,
    helper = null,
    nextRequest = 0,
    authRevision = 0,
    checkQueue = Promise.resolve(),
    cloudRevision = 0,
    deckQueue = Promise.resolve();
  // Only the last accepted assignment, in memory for the current login.
  // Never retain titles, file paths, sharing, deletion or Deck actions here.
  let series = { enabled: false, inherit: true, assignment: null };
  function clearSeries() {
    series = { enabled: false, inherit: true, assignment: null };
  }
  const defaults = {
    base: '',
    allowHttp: false,
    eraseHistory: false,
    theme: 'auto',
    profiles: [],
    nextcloud: null
  };
  const jobShareRequests = new Map();
  let assignmentQueue = Promise.resolve();
  let previewQueue = Promise.resolve();
  let titleQueue = Promise.resolve();
  function queueTitles(action) {
    const task = titleQueue.then(action);
    titleQueue = task.catch(() => {});
    return task;
  }
  function shareOptions(raw) {
    if (raw == null) return null;
    if (
      typeof raw !== 'object' ||
      ![0, 1, 7, 30].includes(raw.days) ||
      typeof raw.archive !== 'boolean'
    )
      throw new Error('Ungültige Freigabeoptionen.');
    return { days: raw.days, archive: raw.archive };
  }
  function cleanNextcloud(raw) {
    if (!raw || typeof raw !== 'object') return null;
    try {
      const base = C.baseURL(raw.base),
        username = String(raw.username || '').trim();
      const boardId = Number(raw.boardId),
        stackId = Number(raw.stackId);
      if (
        !username ||
        /[:\r\n]/.test(username) ||
        !Number.isSafeInteger(boardId) ||
        boardId <= 0 ||
        !Number.isSafeInteger(stackId) ||
        stackId <= 0
      )
        return null;
      return {
        base,
        username,
        boardId,
        boardName: String(raw.boardName || '').slice(0, 100),
        stackId,
        stackName: String(raw.stackName || '').slice(0, 100)
      };
    } catch (_) {
      return null;
    }
  }
  const ready = browser.storage.local.get('settings').then((x) => {
    const stored =
      x.settings && typeof x.settings === 'object' ? x.settings : {};
    config = {
      ...defaults,
      base: String(stored.base || ''),
      allowHttp: !!stored.allowHttp,
      eraseHistory: !!stored.eraseHistory,
      theme: ['auto', 'light', 'dark'].includes(stored.theme)
        ? stored.theme
        : 'auto',
      profiles: Array.isArray(stored.profiles) ? stored.profiles : [],
      nextcloud: cleanNextcloud(stored.nextcloud),
      shortcuts: stored.shortcuts || { ...Shortcuts.defaults },
      fastTabs: stored.fastTabs !== false
    };
  });
  async function token() {
    const x = (await browser.storage.session.get('auth')).auth;
    return x?.base === config.base ? x.token : null;
  }
  function api(base = config.base) {
    return new C.API(base, async () => {
      if (config.base !== base)
        throw new Error('Die Paperless-Adresse hat sich geändert.');
      return token();
    });
  }
  function active() {
    return [...jobs.values()].some((j) => j.busy || j.manualShareBusy);
  }
  async function badge() {
    const list = [...jobs.values()],
      count = list.filter((j) => j.busy).length;
    const completed = list.some((j) => j.state === 'success' && j.unread);
    const warning = list.some(
      (j) =>
        [
          'failed',
          'pending',
          'uncertain',
          'duplicate',
          'duplicate_rejected',
          'check_failed'
        ].includes(j.state) ||
        j.cleanupWarning ||
        j.deckWarning ||
        j.shareWarning ||
        j.inboxWarning
    );
    try {
      await browser.browserAction.setBadgeText({
        text: count ? String(count) : warning ? '!' : completed ? '✓' : ''
      });
      await browser.browserAction.setBadgeBackgroundColor({
        color: warning && !count ? '#b02a37' : '#17541f'
      });
      await browser.browserAction.setTitle({
        title: count
          ? `Paperless Send · ${count} laufende Aufträge`
          : warning
            ? 'Paperless Send · Auftrag benötigt Aufmerksamkeit'
            : completed
              ? 'Paperless Send · Archivierung abgeschlossen'
              : 'Paperless Send · Aufträge'
      });
    } catch (_) {}
  }
  async function notify(message) {
    try {
      await browser.notifications.create({
        type: 'basic',
        iconUrl: browser.runtime.getURL('icons/paperless-send-48.png'),
        title: 'Paperless Send',
        message
      });
    } catch (_) {}
  }
  async function writeClipboard(raw) {
    const text = String(raw || '');
    if (!text || text.length > 100000)
      throw new Error('Der Paperless-Link kann nicht kopiert werden.');
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    try {
      if (!document.execCommand('copy'))
        throw new Error('Zwischenablage nicht verfügbar.');
    } finally {
      area.remove();
    }
  }
  function resultLink(job) {
    return job.share ? job.shareURL : job.documentURL;
  }
  async function syncBatchClipboard(id) {
    const batch = batches.get(id);
    if (!batch?.sealed) return;
    const list = [...batch.ids].map((jobId) => jobs.get(jobId)).filter(Boolean);
    if (!list.length || list.some((job) => job.busy)) return;
    const links = [...new Set(list.map(resultLink).filter(Boolean))],
      text = links.join('\n');
    if (!text || text === batch.lastText) return;
    try {
      await writeClipboard(text);
      batch.lastText = text;
      for (const job of list.filter(
        (item) => resultLink(item) && links.includes(resultLink(item))
      )) {
        job.linkCopied = true;
        delete job.linkCopyError;
      }
    } catch (_) {
      for (const job of list.filter((item) => resultLink(item))) {
        job.linkCopied = false;
        job.linkCopyError =
          'Automatisches Kopieren nicht möglich. „Link kopieren“ verwenden.';
      }
    }
  }
  function queueBatchClipboard(id) {
    const batch = batches.get(id);
    if (!batch) return Promise.resolve();
    const next = batch.copyQueue.then(() => syncBatchClipboard(id));
    batch.copyQueue = next.catch(() => {});
    return next;
  }
  function finished(job) {
    job.busy = false;
    job.finishedAt = Date.now();
    job.unread = true;
    void badge();
    void queueBatchClipboard(job.batchId);
    const titles = {
      success: job.inboxWarning
        ? 'Archiviert · Zuordnung offen'
        : job.shareWarning
          ? 'Archiviert · Freigabe offen'
          : job.deckWarning
            ? 'Archiviert · Deck offen'
            : job.cleanupWarning
              ? 'Archiviert · Original erhalten'
              : 'Archivierung abgeschlossen',
      duplicate: 'Dublettenentscheidung erforderlich',
      duplicate_rejected: 'Dublettenimport vom Server abgelehnt',
      cancelled: 'Auftrag abgebrochen',
      pending: 'Archivierung noch nicht bestätigt',
      check_failed: 'Dublettenprüfung fehlgeschlagen',
      failed: 'Verarbeitung fehlgeschlagen',
      uncertain: 'Upload-Ergebnis unklar'
    };
    const signature = `${job.state}:${job.message}`;
    if (job.lastNotification === signature) return;
    job.lastNotification = signature;
    void browser.notifications
      .create('paperless-job:' + job.id, {
        type: 'basic',
        iconUrl: browser.runtime.getURL('icons/paperless-send-48.png'),
        title: titles[job.state] || 'Paperless Send',
        message: `${job.name}: ${job.message}`
      })
      .catch(() => {});
  }
  function connectHelper() {
    if (helper) return helper;
    const port = browser.runtime.connectNative('paperless_send_api');
    const waiting = new Map();
    const connection = {
      call(action, fields = {}) {
        return new Promise((resolve, reject) => {
          const id = ++nextRequest;
          const timer = setTimeout(
            () => {
              waiting.delete(id);
              reject(new Error('Dateihelfer antwortet nicht.'));
            },
            action === 'choose' ? 300000 : 60000
          );
          waiting.set(id, { resolve, reject, timer });
          port.postMessage({ id, action, ...fields });
        });
      }
    };
    port.onMessage.addListener((m) => {
      const w = waiting.get(m.id);
      if (!w) return;
      waiting.delete(m.id);
      clearTimeout(w.timer);
      m.ok
        ? w.resolve(m)
        : w.reject(new Error(m.error || 'Dateihelfer meldet einen Fehler.'));
    });
    port.onDisconnect.addListener(() => {
      if (helper === connection) helper = null;
      const detail = port.error?.message || 'Verbindung beendet';
      for (const w of waiting.values()) {
        clearTimeout(w.timer);
        w.reject(
          new Error(
            `Dateihelfer: ${detail}. Den optionalen Helfer aus dem Paket installieren und Firefox neu starten. API-Uploads benötigen diesen Helfer nicht.`
          )
        );
      }
      waiting.clear();
    });
    helper = connection;
    return connection;
  }
  async function fileFetch(url) {
    // Firefox can reject file:// access. The UI then offers explicit selection or the helper.
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', url);
      xhr.responseType = 'blob';
      xhr.timeout = 30000;
      xhr.onload = () =>
        xhr.response?.size
          ? resolve(xhr.response)
          : reject(
              new Error(
                'Lokale PDF nicht lesbar. Datei auswählen oder Dateihelfer verwenden.'
              )
            );
      xhr.onerror = xhr.ontimeout = () =>
        reject(
          new Error(
            'Firefox erlaubt hier keinen Dateizugriff. Datei auswählen oder Dateihelfer verwenden.'
          )
        );
      xhr.send();
    });
  }
  async function fromHelper(path = null) {
    if (
      !(await browser.permissions.contains({
        permissions: ['nativeMessaging']
      }))
    )
      throw new Error(
        'Bitte den Dateihelfer zuerst in den Einstellungen aktivieren.'
      );
    const conn = connectHelper(),
      opened = await conn.call(path ? 'open' : 'choose', path ? { path } : {});
    if (opened.cancelled) return null;
    try {
      const parts = [];
      for (let offset = 0; offset < opened.size; ) {
        const r = await conn.call('read', { ref: opened.ref, offset });
        const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
        if (!bytes.length || offset + bytes.length > C.MAX_BYTES)
          throw new Error('Unvollständige Antwort vom Dateihelfer.');
        parts.push(bytes);
        offset += bytes.length;
      }
      const blob = new Blob(parts, { type: 'application/pdf' });
      await C.checkPDF(blob);
      if (blob.size !== opened.size || (await C.sha256(blob)) !== opened.sha256)
        throw new Error('Die lokale Datei wurde während des Lesens verändert.');
      return addSource(blob, opened.filename, {
        path: opened.path,
        ref: opened.ref,
        conn,
        hash: opened.sha256,
        kind: 'helper'
      });
    } catch (e) {
      await conn.call('release', { ref: opened.ref }).catch(() => {});
      throw e;
    }
  }
  function sourceFingerprints(source) {
    if (!source.fingerprints)
      source.fingerprints = C.fingerprints(source.blob).catch((e) => {
        delete source.fingerprints;
        throw e;
      });
    return source.fingerprints;
  }
  function publicSource(s) {
    return {
      id: s.id,
      name: s.name,
      size: s.blob.size,
      kind: s.kind,
      canDelete: !!s.ref || Number.isInteger(s.downloadId),
      path: s.path || '',
      url: s.url || ''
    };
  }
  function addSource(blob, name, extra = {}) {
    const source = {
      id: crypto.randomUUID(),
      blob,
      name: C.safeName(name),
      kind: 'picker',
      ...extra
    };
    sources.set(source.id, source);
    return publicSource(source);
  }
  async function release(s) {
    if (s.ref) await s.conn.call('release', { ref: s.ref }).catch(() => {});
    sources.delete(s.id);
  }
  async function removeOriginal(s) {
    if (s.ref) {
      await s.conn.call('delete', { ref: s.ref, sha256: s.hash });
      return;
    }
    if (!Number.isInteger(s.downloadId))
      throw new Error(
        'Für diese Datei ist kein sicherer Löschzugriff vorhanden.'
      );
    const list = await browser.downloads.search({ id: s.downloadId });
    if (
      list.length !== 1 ||
      list[0].filename !== s.path ||
      list[0].state !== 'complete' ||
      list[0].exists === false
    )
      throw new Error(
        'Die ursprüngliche Download-Datei ist nicht mehr eindeutig verfügbar.'
      );
    const current = await fileFetch(C.pathURL(s.path));
    if ((await C.sha256(current)) !== s.hash)
      throw new Error(
        'Die Download-Datei wurde verändert und wird nicht gelöscht.'
      );
    await browser.downloads.removeFile(s.downloadId);
    if (config.eraseHistory)
      await browser.downloads.erase({ id: s.downloadId }).catch(() => {});
  }
  async function cloudPassword(target) {
    const auth = (await browser.storage.session.get('nextcloudAuth'))
      .nextcloudAuth;
    return auth?.base === target.base && auth?.username === target.username
      ? auth.password
      : null;
  }
  async function finishArchive(job) {
    if (job.completeTagging && !job.inboxDone) {
      job.state = 'tagging';
      job.message = 'Archiviert. Posteingangs-Tags werden entfernt …';
      try {
        await api(job.base).removeInboxTags(job.documentId);
        job.inboxDone = true;
        delete job.inboxWarning;
      } catch (e) {
        job.inboxWarning =
          'Posteingangs-Tags konnten nicht bestätigt entfernt werden. ' +
          e.message;
        job.state = 'success';
        job.message =
          'In Paperless archiviert. Zuordnung noch offen; weitere Folgeschritte warten. Original bleibt erhalten.';
        return;
      }
    }
    if (job.share && !job.shareURL) {
      job.state = 'sharing';
      job.message = 'Archiviert. Öffentlicher Link wird erzeugt …';
      try {
        const link = await api(job.base).createShareLink(
          job.documentId,
          job.share
        );
        job.shareURL = link.url;
        job.shareExpiration = link.expiration;
      } catch (e) {
        job.shareWarning =
          'Öffentliche Freigabe nicht bestätigt. Bitte die Share Links am Dokument in Paperless prüfen. ' +
          e.message;
        job.state = 'success';
        job.message =
          'In Paperless archiviert. Freigabe offen; ausgewählte Deck-Karten wurden noch nicht angelegt. Original bleibt erhalten.';
        return;
      }
    }
    if (job.deck) {
      job.state = 'deck';
      job.message = 'Archiviert. Deck-Karten werden angelegt …';
      const create = deckQueue.then(async () => {
        const target = job.deck.target;
        const client = new Nextcloud.Client(target.base, target.username, () =>
          cloudPassword(target)
        );
        job.deckLinks ||= [];
        for (const card of job.deck.cards) {
          if (card.done) continue;
          const data = Nextcloud.cardData({
            ...card,
            title: job.metadata.title || job.name,
            url: resultLink(job)
          });
          const url = await client.ensureCard(
            target,
            card,
            data,
            job.allowDeckCreate === true
          );
          card.done = true;
          job.deckLinks.push({ name: card.name, url });
        }
      });
      deckQueue = create.catch(() => {});
      try {
        await create;
        job.deckWarning = false;
        job.deckUncertain = false;
      } catch (e) {
        job.deckWarning = true;
        job.deckUncertain = !!e.uncertain;
        job.state = 'success';
        const count = job.deck.cards.filter((c) => c.done).length;
        job.message = `In Paperless archiviert. Deck: ${count}/${job.deck.cards.length} Karten bestätigt. ${e.message} Original bleibt erhalten.`;
        return;
      } finally {
        delete job.allowDeckCreate;
      }
    }
    let message = 'In Paperless archiviert.';
    if (job.shareURL) message += ' Öffentlicher Freigabelink erstellt.';
    if (job.inboxDone)
      message += ' Fertig zugeordnet; keine Posteingangs-Tags gesetzt.';
    if (job.deck)
      message += ` ${job.deck.cards.length} Deck-Karte(n) mit Dokumentlink angelegt.`;
    if (job.deleteLocal) {
      job.state = 'cleanup';
      job.message = 'Archiviert. Lokales Original wird geprüft und gelöscht …';
      try {
        await removeOriginal(job.source);
        message += ' Lokales Original gelöscht.';
      } catch (e) {
        message += ` Original bleibt erhalten: ${e.message}`;
        job.cleanupWarning = true;
      }
    } else
      message +=
        publicSource(job.source).kind === 'web'
          ? ''
          : ' Lokales Original beibehalten.';
    await release(job.source);
    delete job.source;
    job.state = 'success';
    job.message = message;
  }
  async function monitor(job, maxChecks = 90) {
    job.busy = true;
    job.state = 'processing';
    job.message = 'Paperless verarbeitet die PDF …';
    void badge();
    try {
      for (let i = 0; i < maxChecks; i++) {
        const state = await api(job.base).task(job.taskId);
        if (
          ['failed', 'cancelled', 'duplicate_rejected'].includes(state.state)
        ) {
          job.state = state.state;
          job.message =
            state.state === 'duplicate_rejected'
              ? 'Paperless hat die identische Datei abgelehnt. Ein erneuter Upload kann diese Serversperre nicht erzwingen. Original bleibt erhalten.'
              : state.state === 'cancelled'
                ? 'Verarbeitung durch Paperless abgebrochen. Original bleibt erhalten.'
                : 'Verarbeitung in Paperless fehlgeschlagen. Original bleibt erhalten.';
          return;
        }
        if (state.state === 'success') {
          job.state = 'confirming';
          job.message = 'Archiviertes Dokument wird bestätigt …';
          const doc = await api(job.base).request(
            `documents/${state.documentId}/`
          );
          if (Number(doc.id) !== state.documentId)
            throw new Error(
              'Das archivierte Dokument konnte nicht bestätigt werden.'
            );
          if (!job.assignmentRemembered) {
            job.assignmentRemembered = true;
            void window.Paperless.rememberAssignment(
              job.metadata,
              job.base
            ).catch(() => {});
          }
          job.documentId = state.documentId;
          job.documentURL = new URL(
            `documents/${state.documentId}/details`,
            job.base
          ).href;
          await finishArchive(job);
          return;
        }
        job.state = 'processing';
        job.message = 'Paperless verarbeitet die PDF …';
        if (i < maxChecks - 1)
          await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      job.state = 'pending';
      job.message =
        'Noch keine bestätigte Archivierung. Original bleibt erhalten. Status später erneut prüfen.';
    } catch (e) {
      job.state = 'pending';
      job.message = e.message + ' Original bleibt erhalten.';
    } finally {
      finished(job);
    }
  }
  async function uploadJob(job) {
    job.busy = true;
    job.unread = false;
    job.state = 'uploading';
    job.message = 'PDF wird übertragen …';
    void badge();
    try {
      job.taskId = await api(job.base).upload(
        job.source.blob,
        job.name,
        job.metadata
      );
      await monitor(job);
    } catch (e) {
      job.state = 'uncertain';
      job.message = e.message + ' Vor erneutem Senden in Paperless prüfen.';
      finished(job);
    }
  }
  async function run(job) {
    job.busy = true;
    job.unread = false;
    job.state = 'checking';
    job.message = 'Datei wird auf Dubletten geprüft …';
    void badge();
    // Serialize preflights so two copies submitted together also see each other.
    const check = checkQueue.then(async () => {
      if (config.base !== job.base)
        throw new Error('Die Zieladresse wurde geändert.');
      const hashes = await sourceFingerprints(job.source);
      job.checksum = hashes.sha256;
      const matches = await api(job.base).duplicates(hashes);
      for (const prior of jobs.values()) {
        if (prior.id === job.id) break;
        if (
          prior.base === job.base &&
          prior.checksum === job.checksum &&
          ![
            'failed',
            'cancelled',
            'duplicate_rejected',
            'check_failed'
          ].includes(prior.state)
        ) {
          if (!matches.some((m) => m.id && m.id === prior.documentId))
            matches.push({
              title: prior.name + ' · bereits in dieser Sitzung',
              url: prior.documentURL || '',
              sessionJobId: prior.id
            });
        }
      }
      return matches;
    });
    checkQueue = check.then(
      () => {},
      () => {}
    );
    try {
      const matches = await check;
      const approved =
        matches.length &&
        matches.every((m) =>
          job.approvedDuplicates?.includes(
            m.id
              ? 'document:' + m.id
              : m.sessionJobId
                ? 'job:' + m.sessionJobId
                : ''
          )
        );
      if (approved) job.duplicateApproved = true;
      if (matches.length && !approved) {
        job.duplicates = matches;
        job.state = 'duplicate';
        job.message =
          'Identische Datei gefunden. Trotzdem als weiteres Dokument übernehmen?';
        finished(job);
        return;
      }
    } catch (e) {
      job.state = 'check_failed';
      job.message =
        e.message + ' Es wurde nichts hochgeladen. Original bleibt erhalten.';
      finished(job);
      return;
    }
    await uploadJob(job);
  }
  function usableSource(raw) {
    try {
      const u = new URL(raw);
      return ['http:', 'https:', 'file:', 'blob:'].includes(u.protocol) &&
        !u.username &&
        !u.password
        ? u.href
        : '';
    } catch (_) {
      return '';
    }
  }
  function contextSource(info = {}, tab = {}) {
    // A link or an embedded document is the explicit target; never substitute
    // the outer mail page. Firefox's internal PDF viewer URL is not fetchable.
    if (info.linkUrl) return info.linkUrl;
    const frame = usableSource(info.frameUrl);
    if (info.frameId > 0 && frame) return frame;
    return (
      usableSource(info.pageUrl) ||
      usableSource(tab?.url) ||
      info.pageUrl ||
      tab?.url ||
      ''
    );
  }
  function looksLikePDF(raw, title = '') {
    try {
      return (
        /\.pdf$/i.test(new URL(raw).pathname) || /\.pdf(?:$|\s)/i.test(title)
      );
    } catch (_) {
      return false;
    }
  }
  function pdfName(raw = '', title = '') {
    const titled = String(title || '')
      .split(/[|—–]/)
      .map((part) => part.trim())
      .find((part) => /\.pdf$/i.test(part));
    if (titled) return C.safeName(titled);
    try {
      const name = decodeURIComponent(
        new URL(raw).pathname.split('/').pop() || ''
      );
      if (/\.pdf$/i.test(name)) return C.safeName(name);
    } catch (_) {}
    const match = String(title || '').match(/([^/\\]+?\.pdf)(?:\s|$)/i);
    return match ? C.safeName(match[1].trim()) : '';
  }
  function comparablePDFName(raw = '') {
    return String(raw)
      .split(/[\\/]/)
      .pop()
      .normalize('NFKC')
      .toLocaleLowerCase('de')
      .replace(/\.pdf$/i, '')
      .replace(/\s*\(\d+\)$/, '')
      .trim();
  }
  function viewerSource(info = {}, tab = {}, sourceURL = '') {
    if (info.linkUrl) return false;
    return (
      String(info.pageUrl || '').startsWith('resource://pdf.js/') ||
      looksLikePDF(sourceURL, tab?.title || '')
    );
  }
  async function openUI(
    sourceURL = '',
    profileId = '',
    fromPDFViewer = false,
    sourceName = ''
  ) {
    const ticket = crypto.randomUUID();
    if (sourceURL)
      await browser.storage.session.set({
        ['intent:' + ticket]: {
          url: sourceURL,
          name: pdfName(sourceURL, sourceName),
          profileId,
          viewerSource: !!fromPDFViewer
        }
      });
    try {
      await browser.windows.create({
        type: 'popup',
        width: 560,
        height: 820,
        url:
          browser.runtime.getURL('app.html') +
          '?compact=1' +
          (sourceURL ? '&intent=' + ticket : '')
      });
    } catch (e) {
      if (sourceURL) await browser.storage.session.remove('intent:' + ticket);
      throw e;
    }
  }
  async function rebuildMenus() {
    await ready;
    await browser.contextMenus.removeAll();
    browser.contextMenus.create({
      id: 'send',
      title: 'An Paperless senden …',
      contexts: ['page', 'link']
    });
    for (const p of config.profiles)
      browser.contextMenus.create({
        id: 'profile:' + p.id,
        parentId: 'send',
        title: p.name + ' …',
        contexts: ['page', 'link']
      });
    if (config.profiles.length)
      browser.contextMenus.create({
        id: 'custom',
        parentId: 'send',
        title: 'Tags auswählen …',
        contexts: ['page', 'link']
      });
  }
  window.Paperless = {
    async openComposer() {
      // Capture the tab before creating the composer, which changes focus.
      const tabs = await browser.tabs.query({
        active: true,
        lastFocusedWindow: true
      });
      const tab = tabs[0];
      const raw = contextSource({}, tab);
      const pdf = looksLikePDF(raw, tab?.title || '');
      return openUI(pdf ? raw : '', '', pdf, tab?.title || '');
    },
    async openPage(view = 'history') {
      await browser.tabs.create({
        url:
          browser.runtime.getURL('app.html') +
          '#' +
          (view === 'settings' ? 'settings' : 'history')
      });
    },
    async state() {
      await ready;
      const unlocked = !!(await token());
      return {
        previewRevision: authRevision,
        config: structuredClone(config),
        unlocked,
        series: unlocked
          ? structuredClone(series)
          : { enabled: false, inherit: true, assignment: null },
        busy: active(),
        helperAllowed: await browser.permissions.contains({
          permissions: ['nativeMessaging']
        }),
        nextcloudUnlocked: !!(
          config.nextcloud && (await cloudPassword(config.nextcloud))
        )
      };
    },
    async saveSeriesOptions(raw, expectedBase, expectedRevision) {
      await ready;
      if (
        !(await token()) ||
        expectedBase !== config.base ||
        expectedRevision !== authRevision
      )
        throw new Error('Die Sitzung wurde geändert. Bitte erneut entsperren.');
      series.enabled = raw.enabled === true;
      series.inherit = raw.inherit !== false;
    },
    async saveKeyboard(raw) {
      await ready;
      const shortcuts = Shortcuts.validate(raw.shortcuts);
      const next = { ...config, shortcuts, fastTabs: raw.fastTabs !== false };
      await browser.storage.local.set({ settings: next });
      config = next;
      return this.state();
    },
    async saveSettings(raw) {
      await ready;
      if (active()) throw new Error('Bitte die laufende Übertragung abwarten.');
      const base = C.baseURL(raw.base, !!raw.allowHttp),
        changed = base !== config.base;
      config = {
        base,
        allowHttp: !!raw.allowHttp,
        eraseHistory: !!raw.eraseHistory,
        theme: ['auto', 'light', 'dark'].includes(raw.theme)
          ? raw.theme
          : 'auto',
        profiles: changed ? [] : config.profiles,
        nextcloud: config.nextcloud,
        shortcuts: config.shortcuts,
        fastTabs: config.fastTabs
      };
      // Whitelist only non-secret preferences. Tokens can never reach local storage here.
      await browser.storage.local.set({ settings: config });
      if (changed) {
        authRevision++;
        clearSeries();
        await browser.storage.session.remove('auth');
        catalog = null;
      }
      await rebuildMenus();
      return this.state();
    },
    async unlock(rawToken) {
      await ready;
      if (!config.base)
        throw new Error('Bitte zuerst die Paperless-Adresse speichern.');
      const key = String(rawToken).trim();
      if (!key || /\s/.test(key))
        throw new Error(
          'Bitte einen gültigen API-Token ohne Leerzeichen eingeben.'
        );
      const base = config.base,
        rev = ++authRevision;
      clearSeries();
      const client = new C.API(base, async () => key);
      const tags = await client.list('tags');
      if (rev !== authRevision || base !== config.base)
        throw new Error(
          'Anmeldung verworfen, weil die Sitzung oder Adresse geändert wurde.'
        );
      await browser.storage.session.set({ auth: { base, token: key } });
      catalog = null;
      return { tags };
    },
    async lock() {
      authRevision++;
      clearSeries();
      cloudRevision++;
      await browser.storage.session.remove('auth');
      await browser.storage.session.remove('nextcloudAuth');
      catalog = null;
    },
    async connectNextcloud(raw) {
      await ready;
      const rev = ++cloudRevision,
        base = C.baseURL(raw.base),
        username = String(raw.username || '').trim(),
        password = String(raw.password || '');
      if (!password || /[\r\n]/.test(password) || password.length > 4096)
        throw new Error('Bitte ein gültiges Nextcloud-App-Passwort eingeben.');
      const client = new Nextcloud.Client(base, username, async () => password),
        boards = await client.boards();
      if (!boards.length)
        throw new Error(
          'Keine bearbeitbaren Deck-Boards gefunden. Deck aktivieren und ein Board mit Liste anlegen.'
        );
      if (rev !== cloudRevision)
        throw new Error(
          'Nextcloud-Anmeldung wurde verworfen, weil die Sitzung geändert wurde.'
        );
      await browser.storage.session.set({
        nextcloudAuth: { base, username, password, boards }
      });
      return boards;
    },
    async deckStacks(boardId) {
      const auth = (await browser.storage.session.get('nextcloudAuth'))
        .nextcloudAuth;
      if (!auth?.boards.some((b) => b.id === Number(boardId)))
        throw new Error(
          'Zuerst mit Nextcloud verbinden und ein Board auswählen.'
        );
      const client = new Nextcloud.Client(auth.base, auth.username, () =>
        cloudPassword(auth)
      );
      return (await client.stacks(Number(boardId))).map((s) => ({
        id: s.id,
        name: s.name
      }));
    },
    async saveNextcloud(raw) {
      await ready;
      if (active()) throw new Error('Bitte laufende Aufträge abwarten.');
      const base = C.baseURL(raw.base),
        username = String(raw.username || '').trim(),
        rev = cloudRevision;
      const auth = (await browser.storage.session.get('nextcloudAuth'))
        .nextcloudAuth;
      const board =
        auth?.base === base && auth?.username === username
          ? auth.boards.find((b) => b.id === Number(raw.boardId))
          : null;
      if (!board)
        throw new Error(
          'Zuerst mit Nextcloud verbinden und ein Board auswählen.'
        );
      const stack = (await this.deckStacks(board.id)).find(
        (s) => s.id === Number(raw.stackId)
      );
      if (!stack)
        throw new Error('Bitte eine vorhandene Deck-Liste auswählen.');
      if (rev !== cloudRevision || active())
        throw new Error(
          'Sitzung hat sich geändert oder ein Auftrag läuft. Bitte erneut speichern.'
        );
      config.nextcloud = cleanNextcloud({
        base,
        username,
        boardId: board.id,
        boardName: board.name,
        stackId: stack.id,
        stackName: stack.name
      });
      await browser.storage.local.set({ settings: config });
      return this.state();
    },
    async lockNextcloud() {
      cloudRevision++;
      await browser.storage.session.remove('nextcloudAuth');
      return this.state();
    },
    async metadata(refresh = false) {
      await ready;
      if (!(await token()))
        throw new Error(
          'Bitte zuerst den API-Token für diese Sitzung eingeben.'
        );
      if (catalog && !refresh) return structuredClone(catalog);
      const base = config.base,
        revision = authRevision,
        client = api();
      const keys = [
        'tags',
        'correspondents',
        'document_types',
        'storage_paths',
        'custom_fields'
      ];
      const lists = await Promise.allSettled(
        keys.map((key) => client.list(key))
      );
      if (lists[0].status === 'rejected') throw lists[0].reason;
      const result = { warnings: [] };
      keys.forEach((key, i) => {
        result[key] = lists[i].status === 'fulfilled' ? lists[i].value : [];
        if (lists[i].status === 'rejected')
          result.warnings.push(
            `${key}: keine Leseberechtigung oder nicht verfügbar.`
          );
      });
      result.custom_fields_error = lists[4].status === 'rejected';
      if (base !== config.base || revision !== authRevision)
        throw new Error('Sitzung hat sich geändert.');
      catalog = result;
      return structuredClone(result);
    },
    async titleHistory() {
      await ready;
      await titleQueue;
      const data = (await browser.storage.local.get('titleHistory'))
        .titleHistory;
      const titles = data?.[config.base];
      return Array.isArray(titles)
        ? titles
            .filter((t) => typeof t === 'string' && t.length <= 200)
            .slice(0, 50)
        : [];
    },
    async rememberTitle(value, expectedBase = config.base) {
      await ready;
      if (expectedBase !== config.base)
        throw new Error('Die Paperless-Adresse hat sich geändert.');
      const base = config.base,
        title = String(value || '')
          .trim()
          .slice(0, 200);
      if (!base || !title) return;
      return queueTitles(async () => {
        const stored = (await browser.storage.local.get('titleHistory'))
          .titleHistory;
        const data =
          stored && typeof stored === 'object' && !Array.isArray(stored)
            ? stored
            : {};
        const previous = Array.isArray(data[base]) ? data[base] : [];
        data[base] = [
          title,
          ...previous.filter(
            (t) =>
              typeof t === 'string' &&
              t.toLocaleLowerCase('de') !== title.toLocaleLowerCase('de')
          )
        ].slice(0, 50);
        await browser.storage.local.set({ titleHistory: data });
      });
    },
    async clearTitleHistory() {
      await ready;
      const base = config.base;
      return queueTitles(async () => {
        const stored = (await browser.storage.local.get('titleHistory'))
          .titleHistory;
        if (!stored || typeof stored !== 'object') return;
        delete stored[base];
        await browser.storage.local.set({ titleHistory: stored });
      });
    },
    async createTag(name, color) {
      const clean = String(name).trim();
      if (!clean) throw new Error('Tag-Name fehlt.');
      const tag = await api().request('tags/', {
        method: 'POST',
        json: true,
        body: JSON.stringify({
          name: clean,
          color: /^#[a-f0-9]{6}$/i.test(color) ? color : '#17541f'
        })
      });
      catalog = null;
      return tag;
    },
    async saveProfile(name, raw, existingId = null) {
      const clean = String(name).trim().slice(0, 70);
      if (!clean) throw new Error('Profilnamen eingeben.');
      const old = existingId
        ? config.profiles.find((p) => p.id === existingId)
        : null;
      if (existingId && !old)
        throw new Error('Das Profil existiert nicht mehr.');
      const profile = {
        id: old?.id || crypto.randomUUID(),
        name: clean,
        ...C.metadata(raw),
        share: shareOptions(raw.share),
        complete_tagging: raw.complete_tagging === true
      };
      delete profile.title;
      delete profile.created;
      delete profile.custom_fields;
      const profiles = old
        ? config.profiles.map((p) => (p.id === old.id ? profile : p))
        : [...config.profiles, profile];
      await browser.storage.local.set({ settings: { ...config, profiles } });
      config.profiles = profiles;
      await rebuildMenus();
      return profile;
    },
    async assignmentSuggestions(correspondent) {
      await ready;
      await assignmentQueue;
      const history = (await browser.storage.local.get('assignmentHistory'))
        .assignmentHistory;
      return structuredClone(
        (history?.[config.base]?.[String(correspondent)] || []).slice(0, 3)
      );
    },
    async rememberAssignment(metadata, base) {
      const correspondent = metadata.correspondent;
      if (!correspondent) return;
      const choice = {
        tags: C.ids(metadata.tags).sort((a, b) => a - b),
        document_type: metadata.document_type || null
      };
      const key = JSON.stringify(choice),
        task = assignmentQueue.then(async () => {
          const history =
            (await browser.storage.local.get('assignmentHistory'))
              .assignmentHistory || {};
          const byServer = history[base] || {},
            old = byServer[String(correspondent)] || [],
            prior = old.find(
              (x) =>
                JSON.stringify({
                  tags: x.tags,
                  document_type: x.document_type
                }) === key
            );
          const next = {
            ...choice,
            count: (prior?.count || 0) + 1,
            lastUsed: Date.now()
          };
          byServer[String(correspondent)] = [
            next,
            ...old.filter((x) => x !== prior)
          ]
            .sort((a, b) => b.count - a.count || b.lastUsed - a.lastUsed)
            .slice(0, 5);
          history[base] = byServer;
          await browser.storage.local.set({ assignmentHistory: history });
        });
      assignmentQueue = task.catch(() => {});
      return task;
    },
    async clearAssignmentHistory() {
      await ready;
      const base = config.base,
        task = assignmentQueue.then(async () => {
          const history =
            (await browser.storage.local.get('assignmentHistory'))
              .assignmentHistory || {};
          delete history[base];
          await browser.storage.local.set({ assignmentHistory: history });
        });
      assignmentQueue = task.catch(() => {});
      return task;
    },
    async useExistingDuplicate(
      sourceId,
      documentId,
      share = null,
      expectedBase = config.base
    ) {
      await ready;
      const source = sources.get(sourceId),
        base = config.base,
        revision = authRevision;
      if (
        base !== expectedBase ||
        !source ||
        source.used ||
        source.existingBusy
      )
        throw new Error('Auswahl oder Zieladresse geändert.');
      if (!(await token())) throw new Error('Bitte Sitzung entsperren.');
      const options = shareOptions(share);
      source.existingBusy = true;
      try {
        const hashes = await sourceFingerprints(source),
          matches = await api(base).duplicates(hashes);
        if (
          base !== config.base ||
          revision !== authRevision ||
          sources.get(sourceId) !== source ||
          source.used
        )
          throw new Error('Auswahl oder Sitzung geändert.');
        const match = matches.find((m) => m.id === Number(documentId));
        if (!match)
          throw new Error(
            'Dieses Dokument wurde nicht als identische Dublette bestätigt.'
          );
        const documentURL = match.url;
        let url = documentURL;
        if (options) {
          source.existingShares ||= new Map();
          const key = JSON.stringify([documentId, options]);
          if (!source.existingShares.has(key))
            source.existingShares.set(
              key,
              api(base)
                .createShareLink(Number(documentId), options)
                .catch(() => {
                  throw new Error(
                    'Freigabe nicht bestätigt. Bitte Share Links in Paperless prüfen; kein automatischer erneuter Versuch.'
                  );
                })
            );
          url = (await source.existingShares.get(key)).url;
        }
        let copied = true;
        try {
          await writeClipboard(url);
        } catch (_) {
          copied = false;
        }
        return { url, documentURL, copied };
      } finally {
        source.existingBusy = false;
      }
    },
    async removeProfile(id) {
      config.profiles = config.profiles.filter((p) => p.id !== id);
      await browser.storage.local.set({ settings: config });
      await rebuildMenus();
    },
    async intent(id) {
      const key = 'intent:' + id,
        x = (await browser.storage.session.get(key))[key];
      await browser.storage.session.remove(key);
      return x;
    },
    async chooseFile(file) {
      await C.checkPDF(file);
      return addSource(file, file.name);
    },
    async helperFile(path) {
      return fromHelper(path);
    },
    async testHelper() {
      return connectHelper().call('ping');
    },
    async sourceURL(raw) {
      const u = new URL(raw);
      if (u.protocol === 'file:') {
        const blob = await fileFetch(u.href);
        await C.checkPDF(blob);
        return addSource(blob, C.urlName(u.href), {
          kind: 'local',
          url: u.href
        });
      }
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password)
        throw new Error(
          'Diese URL lässt sich nicht direkt laden. PDF speichern und über die Dateiauswahl hinzufügen.'
        );
      let response;
      try {
        response = await fetch(u.href, {
          credentials: 'include',
          cache: 'no-store',
          signal: AbortSignal.timeout(60000)
        });
      } catch (_) {
        throw new Error(
          'PDF-Link nicht abrufbar. Bei geschützten PDFs Datei speichern und auswählen.'
        );
      }
      if (!response.ok) {
        const error = new Error(
          `PDF-Download fehlgeschlagen (HTTP ${response.status}).`
        );
        if ([401, 403].includes(response.status))
          error.code = 'PDF_SOURCE_PROTECTED';
        throw error;
      }
      if (Number(response.headers.get('Content-Length')) > C.MAX_BYTES)
        throw new Error('PDF ist größer als 100 MiB.');
      if (/text\/html/i.test(response.headers.get('Content-Type') || '')) {
        const error = new Error(
          'Der geschützte Viewer liefert beim direkten Abruf die Webmail-Seite statt der PDF.'
        );
        error.code = 'PDF_SOURCE_PROTECTED';
        throw error;
      }
      const reader = response.body.getReader(),
        parts = [];
      let total = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > C.MAX_BYTES) {
          await reader.cancel();
          throw new Error('PDF ist größer als 100 MiB.');
        }
        parts.push(value);
      }
      const blob = new Blob(parts, { type: 'application/pdf' });
      try {
        await C.checkPDF(blob);
      } catch (error) {
        if (/^\s*</.test(await blob.slice(0, 64).text())) {
          const protectedError = new Error(
            'Der geschützte Viewer liefert beim direkten Abruf eine Webseite statt der PDF.'
          );
          protectedError.code = 'PDF_SOURCE_PROTECTED';
          throw protectedError;
        }
        throw error;
      }
      let name = C.urlName(response.url || u.href);
      const disposition = response.headers.get('Content-Disposition') || '';
      const utf = disposition.match(/filename\*=UTF-8''([^;]+)/i),
        plain = disposition.match(/filename="([^"]+)"/i);
      try {
        if (utf) name = decodeURIComponent(utf[1]);
        else if (plain) name = plain[1];
      } catch (_) {}
      if (!/\.pdf$/i.test(name)) name += '.pdf';
      return addSource(blob, name, { kind: 'web', url: u.href });
    },
    async downloads() {
      return (
        await browser.downloads.search({
          state: 'complete',
          exists: true,
          orderBy: ['-startTime'],
          limit: 100
        })
      )
        .filter((d) => /\.pdf$/i.test(d.filename))
        .map((d) => ({
          id: d.id,
          path: d.filename,
          name: d.filename.split(/[\\/]/).pop()
        }));
    },
    async waitForPDFDownload(rawSince, rawExpectedName = '') {
      const since = Number(rawSince),
        now = Date.now();
      if (!Number.isFinite(since) || since < now - 10000 || since > now + 1000)
        throw new Error(
          'Die Download-Überwachung konnte nicht sicher gestartet werden. Bitte erneut versuchen.'
        );
      const startedAfter = new Date(since).toISOString(),
        expected = comparablePDFName(
          String(rawExpectedName || '').slice(0, 180)
        );
      for (let attempt = 0; attempt < 120; attempt++) {
        const list = await browser.downloads.search({
          state: 'complete',
          exists: true,
          startedAfter,
          orderBy: ['-startTime'],
          limit: 10
        });
        const pdfs = list.filter((d) => /\.pdf$/i.test(d.filename || ''));
        const item = expected
          ? pdfs.find(
              (d) =>
                comparablePDFName(d.filename) === expected ||
                comparablePDFName(C.urlName(d.url || '')) === expected
            )
          : pdfs[0];
        if (item)
          return {
            id: item.id,
            path: item.filename,
            name: item.filename.split(/[\\/]/).pop()
          };
        if (attempt < 119)
          await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error(
        'Innerhalb von zwei Minuten wurde kein neuer PDF-Download gefunden. Bitte erneut starten oder die gespeicherte PDF auswählen.'
      );
    },
    async chooseDownload(id) {
      const items = await browser.downloads.search({ id });
      if (
        items.length !== 1 ||
        items[0].exists === false ||
        items[0].state !== 'complete'
      )
        throw new Error('Download nicht mehr vorhanden.');
      const d = items[0],
        blob = await fileFetch(C.pathURL(d.filename));
      await C.checkPDF(blob);
      return addSource(blob, d.filename.split(/[\\/]/).pop(), {
        downloadId: id,
        path: d.filename,
        kind: 'download',
        hash: await C.sha256(blob)
      });
    },
    async precheckSource(id, expectedBase = config.base) {
      await ready;
      const source = sources.get(id),
        base = config.base,
        revision = authRevision;
      if (!source || source.used)
        throw new Error('Dateiauswahl nicht mehr verfügbar.');
      if (expectedBase !== base)
        throw new Error('Die Paperless-Adresse hat sich geändert.');
      if (!(await token())) return { state: 'locked', matches: [] };
      const current = () =>
        sources.get(id) === source &&
        !source.used &&
        base === config.base &&
        revision === authRevision;
      const task = previewQueue.then(async () => {
        if (!current())
          throw new Error(
            'Dublettenprüfung verworfen: Auswahl oder Sitzung geändert.'
          );
        const hashes = await sourceFingerprints(source);
        if (!current())
          throw new Error(
            'Dublettenprüfung verworfen: Auswahl oder Sitzung geändert.'
          );
        const matches = await api(base).duplicates(hashes);
        if (!current())
          throw new Error(
            'Dublettenprüfung verworfen: Auswahl oder Sitzung geändert.'
          );
        for (const job of jobs.values()) {
          if (
            job.base === base &&
            job.checksum === hashes.sha256 &&
            ![
              'failed',
              'cancelled',
              'duplicate_rejected',
              'check_failed'
            ].includes(job.state)
          ) {
            if (!matches.some((m) => m.id && m.id === job.documentId))
              matches.push({
                title: job.name + ' · bereits in dieser Sitzung',
                url: job.documentURL || '',
                sessionJobId: job.id
              });
          }
        }
        return { state: matches.length ? 'duplicate' : 'clear', matches };
      });
      previewQueue = task.catch(() => {});
      return task;
    },
    async removeSource(id) {
      const s = sources.get(id);
      if (s?.existingBusy)
        throw new Error('Bitte die laufende Linkerzeugung abwarten.');
      if (s && !s.used) await release(s);
    },
    async beginBatch() {
      const id = crypto.randomUUID();
      batches.set(id, {
        ids: new Set(),
        sealed: false,
        lastText: '',
        copyQueue: Promise.resolve()
      });
      return id;
    },
    async sealBatch(id) {
      const batch = batches.get(id);
      if (!batch) throw new Error('Versandgruppe nicht mehr verfügbar.');
      batch.sealed = true;
      if (!batch.ids.size) {
        batches.delete(id);
        return;
      }
      await queueBatchClipboard(id);
    },
    async start(
      id,
      raw,
      deleteLocal,
      expectedBase = config.base,
      requestedBatch = '',
      approvedDuplicates = []
    ) {
      await ready;
      const revision = authRevision;
      if (expectedBase !== config.base)
        throw new Error(
          'Die Zieladresse hat sich geändert. Zuordnung erneut prüfen.'
        );
      if (!(await token())) throw new Error('Bitte API-Token eingeben.');
      const metadata = C.metadata(raw);
      const share = shareOptions(raw.share);
      let definitions = [];
      if (metadata.custom_fields) {
        const data = await this.metadata();
        if (data.custom_fields_error)
          throw new Error(
            'Benutzerdefinierte Felder konnten nicht geladen werden. Bitte aktualisieren.'
          );
        definitions = data.custom_fields;
        metadata.custom_fields = CustomFields.validate(
          metadata.custom_fields,
          data.custom_fields
        );
      }
      const deckIDs = C.ids(raw.deck_fields),
        target = config.nextcloud ? structuredClone(config.nextcloud) : null;
      let deck = null;
      if (deckIDs.length) {
        if (!target || !(await cloudPassword(target)))
          throw new Error(
            'Bitte Nextcloud in den Einstellungen verbinden und ein Deck-Board mit Liste speichern.'
          );
        const cards = deckIDs.map((id) => {
          const field = definitions.find((f) => Number(f.id) === id),
            date = metadata.custom_fields?.[id];
          if (!field || field.data_type !== 'date' || !date)
            throw new Error(
              'Für jeden ausgewählten Deck-Auftrag muss ein Datumsfeld ausgefüllt sein.'
            );
          CustomFields.dateOnly(date);
          return {
            fieldId: id,
            name: field.name,
            date,
            due: Nextcloud.dueDate(date),
            done: false
          };
        });
        deck = { target, cards };
      }
      if (expectedBase !== config.base || revision !== authRevision)
        throw new Error(
          'Die Zieladresse hat sich geändert. Bitte neu zuordnen.'
        );
      const s = sources.get(id);
      if (!s || s.used || s.existingBusy)
        throw new Error(
          'Datei nicht mehr verfügbar oder bereits in Verarbeitung.'
        );
      if (deleteLocal && !publicSource(s).canDelete)
        throw new Error(
          'Zum Löschen die Datei über den Dateihelfer oder die Firefox-Downloadliste auswählen.'
        );
      let batchId = String(requestedBatch || '');
      if (batchId) {
        const batch = batches.get(batchId);
        if (!batch || batch.sealed)
          throw new Error(
            'Versandgruppe ist nicht mehr verfügbar. Bitte erneut starten.'
          );
      } else {
        batchId = crypto.randomUUID();
        batches.set(batchId, {
          ids: new Set(),
          sealed: true,
          lastText: '',
          copyQueue: Promise.resolve()
        });
      }
      if (
        !Array.isArray(approvedDuplicates) ||
        approvedDuplicates.some((k) => typeof k !== 'string' || !k)
      )
        throw new Error('Ungültige Dublettenentscheidung.');
      s.used = true;
      const job = {
        id: crypto.randomUUID(),
        source: s,
        name: s.name,
        base: config.base,
        metadata,
        deck,
        share,
        approvedDuplicates: [...approvedDuplicates],
        completeTagging: raw.complete_tagging === true,
        deleteLocal: !!deleteLocal,
        batchId
      };
      jobs.set(job.id, job);
      batches.get(batchId).ids.add(job.id);
      series.assignment = structuredClone({
        tags: metadata.tags,
        correspondent: metadata.correspondent || null,
        document_type: metadata.document_type || null,
        storage_path: metadata.storage_path || null,
        custom_fields: metadata.custom_fields || {},
        created: metadata.created || '',
        complete_tagging: job.completeTagging
      });
      void this.rememberTitle(metadata.title, job.base).catch(() => {});
      void run(job);
      return job.id;
    },
    async decideDuplicate(id, accept) {
      if (typeof accept !== 'boolean')
        throw new Error('Bitte Ja oder Nein wählen.');
      await ready;
      if (accept && !(await token()))
        throw new Error('Bitte zuerst die Sitzung entsperren.');
      const j = jobs.get(id);
      if (!j || j.busy || j.state !== 'duplicate')
        throw new Error('Diese Dublettenentscheidung ist nicht mehr offen.');
      if (accept) {
        if (j.base !== config.base)
          throw new Error(
            'Die Zieladresse wurde geändert. Bitte neu zuordnen.'
          );
        j.duplicateApproved = true;
        void uploadJob(j);
      } else {
        j.busy = true;
        await release(j.source);
        delete j.source;
        j.state = 'cancelled';
        j.message = 'Nicht übernommen. Lokales Original bleibt erhalten.';
        finished(j);
      }
    },
    async retryDeck(id, allowCreate = false) {
      if (typeof allowCreate !== 'boolean')
        throw new Error('Ungültige Bestätigung.');
      const j = jobs.get(id);
      if (j?.state === 'success' && j.deckWarning && !j.busy) {
        j.busy = true;
        j.allowDeckCreate = allowCreate;
        void badge();
        void finishArchive(j)
          .catch((e) => {
            j.state = 'success';
            j.deckWarning = true;
            j.message = 'In Paperless archiviert. ' + e.message;
          })
          .finally(() => finished(j));
      }
    },
    async retryCheck(id) {
      const j = jobs.get(id);
      if (j?.state === 'check_failed' && !j.busy) void run(j);
    },
    async acknowledgeJob(id) {
      const j = jobs.get(id);
      if (j?.state === 'success') {
        j.unread = false;
        void badge();
      }
    },
    async retryStatus(id) {
      const j = jobs.get(id);
      if (j?.taskId && !j.busy && !['success', 'failed'].includes(j.state))
        void monitor(j);
    },
    async copyJobLink(id) {
      const job = jobs.get(id);
      if (!job?.documentURL)
        throw new Error(
          'Für diesen Auftrag ist noch kein Paperless-Link verfügbar.'
        );
      await writeClipboard(job.documentURL);
      job.linkCopied = true;
      delete job.linkCopyError;
      return job.documentURL;
    },
    async retryInbox(id) {
      const j = jobs.get(id);
      if (j?.state !== 'success' || !j.inboxWarning || j.busy) return;
      j.busy = true;
      void badge();
      void finishArchive(j)
        .catch((e) => {
          j.state = 'success';
          j.inboxWarning = e.message;
        })
        .finally(() => finished(j));
    },
    async documentAssignment(documentId, expectedBase = config.base) {
      await ready;
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      const base = config.base,
        revision = authRevision;
      if (base !== expectedBase || !(await token()))
        throw new Error(
          'Bitte die Sitzung für diese Paperless-Adresse entsperren.'
        );
      const doc = await api(base).request(`documents/${documentId}/`);
      if (revision !== authRevision || base !== config.base || !(await token()))
        throw new Error(
          'Die Sitzung wurde geändert. Zuordnung nicht übernommen.'
        );
      if (
        Number(doc.id) !== documentId ||
        !Array.isArray(doc.tags) ||
        doc.tags.some((id) => !Number.isSafeInteger(id) || id <= 0)
      )
        throw new Error('Tags konnten nicht sicher gelesen werden.');
      const result = { tags: [...new Set(doc.tags)], custom_fields: {} };
      for (const key of ['correspondent', 'document_type', 'storage_path']) {
        const value = doc[key] ?? null;
        if (value !== null && (!Number.isSafeInteger(value) || value <= 0))
          throw new Error('Ungültige Dokumentzuordnung.');
        result[key] = value;
      }
      if (doc.custom_fields !== undefined && !Array.isArray(doc.custom_fields))
        throw new Error('Ungültige benutzerdefinierte Felder.');
      for (const entry of doc.custom_fields || []) {
        if (!Number.isSafeInteger(entry.field) || entry.field <= 0)
          throw new Error('Ungültige Feld-ID.');
        result.custom_fields[entry.field] = entry.value;
      }
      result.custom_fields = CustomFields.cleanMap(result.custom_fields);
      return result;
    },
    async documentPDF(documentId, expectedBase = config.base) {
      await ready;
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      const base = config.base,
        revision = authRevision;
      if (base !== expectedBase || !(await token())) return null;
      const blob = await api(base).request(
        `documents/${documentId}/preview/?original=true`,
        { pdf: true, timeout: 60000 }
      );
      if (revision !== authRevision || base !== config.base || !(await token()))
        return null;
      return blob;
    },
    async documentPageCount(documentId, expectedBase = config.base) {
      await ready;
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      const base = config.base,
        revision = authRevision;
      if (base !== expectedBase || !(await token())) return null;
      const document = await api(base).request(`documents/${documentId}/`);
      if (revision !== authRevision || base !== config.base || !(await token()))
        return null;
      return Number.isSafeInteger(document.page_count) &&
        document.page_count > 0
        ? document.page_count
        : null;
    },
    async documentThumbnail(documentId, expectedBase = config.base) {
      await ready;
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      const base = config.base,
        revision = authRevision;
      if (base !== expectedBase || !(await token())) return null;
      const blob = await api(base).request(`documents/${documentId}/thumb/`, {
        image: true,
        timeout: 15000
      });
      if (revision !== authRevision || base !== config.base || !(await token()))
        return null;
      return blob;
    },
    async jobThumbnail(id) {
      await ready;
      const j = jobs.get(id),
        base = config.base,
        revision = authRevision;
      if (
        j?.state !== 'success' ||
        !Number.isSafeInteger(j.documentId) ||
        j.documentId <= 0 ||
        j.base !== base ||
        !(await token())
      )
        return null;
      const blob = await api(base).request(`documents/${j.documentId}/thumb/`, {
        image: true,
        timeout: 15000
      });
      if (
        revision !== authRevision ||
        base !== config.base ||
        jobs.get(id) !== j ||
        !(await token())
      )
        return null;
      return blob;
    },
    async createJobShare(id, raw) {
      await ready;
      const j = jobs.get(id),
        options = shareOptions(raw);
      if (
        !j?.documentId ||
        j.state !== 'success' ||
        j.busy ||
        j.manualShareBusy ||
        !options
      )
        throw new Error('Bitte die bestätigte Archivierung abwarten.');
      if (j.base !== config.base || !(await token()))
        throw new Error(
          'Bitte die Sitzung für die Paperless-Adresse dieses Auftrags entsperren.'
        );
      if (j.shareWarning && !j.shareURL)
        throw new Error(
          'Frühere Freigabe ist unklar. Bitte Share Links in Paperless prüfen.'
        );
      j.manualShareBusy = true;
      try {
        if (!j.shareURL) {
          const doc = await api(j.base).request(`documents/${j.documentId}/`);
          if (Number(doc.id) !== j.documentId)
            throw new Error('Dokument konnte nicht bestätigt werden.');
          if (!jobShareRequests.has(id))
            jobShareRequests.set(
              id,
              api(j.base)
                .createShareLink(j.documentId, options)
                .catch(() => {
                  throw new Error(
                    'Freigabe nicht bestätigt. Bitte Share Links in Paperless prüfen; kein automatischer erneuter Versuch.'
                  );
                })
            );
          const link = await jobShareRequests.get(id);
          j.shareURL = link.url;
          j.shareExpiration = link.expiration;
        }
        try {
          await writeClipboard(j.shareURL);
          j.linkCopied = true;
          delete j.linkCopyError;
        } catch (_) {
          j.linkCopyError =
            'Link erstellt. Automatisches Kopieren nicht möglich; öffentlichen Link manuell kopieren.';
        }
        delete j.manualShareError;
        return j.shareURL;
      } catch (e) {
        j.manualShareError = e.message;
        throw e;
      } finally {
        j.manualShareBusy = false;
      }
    },
    async copyShareLink(id) {
      const j = jobs.get(id);
      if (!j?.shareURL)
        throw new Error('Noch kein öffentlicher Link verfügbar.');
      await writeClipboard(j.shareURL);
      return j.shareURL;
    },
    jobs() {
      return [...jobs.values()].map(
        ({
          source,
          metadata,
          deck,
          checksum,
          lastNotification,
          batchId,
          ...j
        }) => structuredClone(j)
      );
    },
    async discardJob(id) {
      const j = jobs.get(id);
      if (!j || j.busy || j.manualShareBusy) return;
      if (j.source) await release(j.source);
      jobs.delete(id);
      jobShareRequests.delete(id);
      const batch = batches.get(j.batchId);
      if (batch) {
        batch.ids.delete(id);
        if (!batch.ids.size) batches.delete(j.batchId);
      }
      void badge();
    }
  };
  browser.contextMenus.onClicked.addListener((info, tab) => {
    const source = contextSource(info, tab),
      profile = String(info.menuItemId).startsWith('profile:')
        ? String(info.menuItemId).slice(8)
        : '';
    void openUI(
      source,
      profile,
      viewerSource(info, tab, source),
      info.linkText || tab?.title || ''
    ).catch(() =>
      notify(
        'Versandfenster konnte nicht geöffnet werden. Bitte das Plugin-Symbol verwenden.'
      )
    );
  });

  browser.notifications.onClicked.addListener((id) => {
    if (!id.startsWith('paperless-job:')) return;
    const job = jobs.get(id.slice('paperless-job:'.length));
    const url = job?.state === 'success' ? job.documentURL : '';
    if (url) {
      void window.Paperless.acknowledgeJob(job.id);
      void browser.tabs.create({ url }).catch(() => {});
    } else void window.Paperless.openPage('history').catch(() => {});
  });
  browser.runtime.onInstalled.addListener(() => {
    void rebuildMenus();
  });
  void rebuildMenus();
})();
