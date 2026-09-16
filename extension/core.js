'use strict';
(function (root) {
  const MAX_BYTES = 100 * 1024 * 1024;
  function baseURL(raw, allowHttp = false) {
    const u = new URL(String(raw).trim());
    if (
      !['https:', 'http:'].includes(u.protocol) ||
      u.username ||
      u.password ||
      u.search ||
      u.hash
    ) {
      throw new Error(
        'Eine vollständige Paperless-URL ohne Zugangsdaten, Suchparameter oder Fragment eingeben.'
      );
    }
    if (
      u.protocol !== 'https:' &&
      !allowHttp &&
      !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname)
    ) {
      throw new Error(
        'HTTPS verwenden oder HTTP im vertrauenswürdigen Netz ausdrücklich aktivieren.'
      );
    }
    u.pathname = u.pathname.replace(/\/+$/, '') + '/';
    return u.href;
  }
  function apiURL(base, relative) {
    const prefix = new URL('api/', base),
      u = new URL(relative, prefix);
    if (
      u.origin !== prefix.origin ||
      !u.pathname.startsWith(prefix.pathname) ||
      u.username ||
      u.password ||
      u.hash
    ) {
      throw new Error(
        'Paperless lieferte einen API-Link außerhalb der konfigurierten Adresse.'
      );
    }
    return u.href;
  }
  function safeName(name) {
    return (
      String(name || 'Dokument.pdf')
        .replace(/[\\/:*?"<>|\x00-\x1f]/g, '_')
        .slice(0, 180) || 'Dokument.pdf'
    );
  }
  function urlName(url) {
    try {
      return safeName(
        decodeURIComponent(new URL(url).pathname.split('/').pop()) ||
          'Dokument.pdf'
      );
    } catch (_) {
      return 'Dokument.pdf';
    }
  }
  function pathURL(path) {
    let s = String(path).replace(/\\/g, '/');
    if (s.startsWith('//')) {
      const [host, ...rest] = s.slice(2).split('/');
      return 'file://' + host + '/' + rest.map(encodeURIComponent).join('/');
    }
    if (/^[A-Za-z]:\//.test(s)) s = '/' + s;
    return (
      'file://' +
      s
        .split('/')
        .map((x, i) =>
          i === 1 && /^[A-Za-z]:$/.test(x) ? x : encodeURIComponent(x)
        )
        .join('/')
    );
  }
  function ids(values) {
    return [
      ...new Set(
        (values || [])
          .map(Number)
          .filter((x) => Number.isSafeInteger(x) && x > 0)
      )
    ];
  }
  function metadata(raw = {}) {
    const out = {
      title: String(raw.title || '')
        .trim()
        .slice(0, 200),
      tags: ids(raw.tags)
    };
    if (raw.created) {
      const date = new Date(raw.created);
      if (
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/.test(
          String(raw.created)
        ) ||
        !Number.isFinite(date.getTime())
      )
        throw new Error(
          'Ungültiges Dokumentdatum. Bitte Datum und Uhrzeit prüfen.'
        );
      out.created = date.toISOString();
    }
    for (const k of ['correspondent', 'document_type', 'storage_path']) {
      const n = Number(raw[k]);
      if (Number.isSafeInteger(n) && n > 0) out[k] = n;
    }
    const custom = CustomFields.cleanMap(raw.custom_fields);
    if (Object.keys(custom).length) out.custom_fields = custom;
    return out;
  }
  function taskID(data) {
    const id = typeof data === 'string' ? data : data?.task_id;
    if (
      !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
        id || ''
      )
    ) {
      throw new Error(
        'Upload möglicherweise angenommen, aber keine gültige Task-ID erhalten. In Paperless prüfen; Original bleibt erhalten.'
      );
    }
    return id;
  }
  function taskState(data, id) {
    const rows = Array.isArray(data)
      ? data
      : Array.isArray(data?.results)
        ? data.results
        : [data];
    const task = rows.find((x) => x && x.task_id === id);
    if (!task) return { state: 'pending' };
    const status = String(task.status).toUpperCase();
    const result =
      task.result_data && typeof task.result_data === 'object'
        ? task.result_data
        : {};
    if (['FAILURE', 'REVOKED'].includes(status)) {
      const duplicate =
        Number(result.duplicate_of) > 0 ||
        (Array.isArray(task.duplicate_documents) &&
          task.duplicate_documents.length > 0) ||
        /(?:it is a duplicate of|duplicate document|document already exists)/i.test(
          String(task.result || result.error_message || '')
        );
      return {
        state: duplicate
          ? 'duplicate_rejected'
          : status === 'REVOKED'
            ? 'cancelled'
            : 'failed'
      };
    }
    // API v9 exposes related_document; v10 uses result_data / related_document_ids.
    const doc = Number(
      result.document_id ||
        task.related_document ||
        (task.related_document_ids?.length === 1
          ? task.related_document_ids[0]
          : null)
    );
    if (status === 'SUCCESS' && Number.isSafeInteger(doc) && doc > 0)
      return { state: 'success', documentId: doc };
    return { state: 'pending' };
  }
  async function sha256(blob) {
    const hash = await crypto.subtle.digest(
      'SHA-256',
      await blob.arrayBuffer()
    );
    return Array.from(new Uint8Array(hash), (x) =>
      x.toString(16).padStart(2, '0')
    ).join('');
  }
  async function md5(bytes) {
    // Compatibility fingerprint for older Paperless instances; deletion uses SHA-256.
    const length = bytes.length,
      padded = new Uint8Array(Math.ceil((length + 9) / 64) * 64);
    padded.set(bytes);
    padded[length] = 0x80;
    const view = new DataView(padded.buffer);
    view.setUint32(padded.length - 8, (length * 8) >>> 0, true);
    view.setUint32(padded.length - 4, Math.floor(length / 0x20000000), true);
    const shift = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
    const constants = Array.from(
      { length: 64 },
      (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 0x100000000) >>> 0
    );
    let a0 = 0x67452301,
      b0 = 0xefcdab89,
      c0 = 0x98badcfe,
      d0 = 0x10325476;
    for (let offset = 0; offset < padded.length; offset += 64) {
      let a = a0,
        b = b0,
        c = c0,
        d = d0;
      for (let i = 0; i < 64; i++) {
        let f, g;
        if (i < 16) {
          f = (b & c) | (~b & d);
          g = i;
        } else if (i < 32) {
          f = (d & b) | (~d & c);
          g = (5 * i + 1) % 16;
        } else if (i < 48) {
          f = b ^ c ^ d;
          g = (3 * i + 5) % 16;
        } else {
          f = c ^ (b | ~d);
          g = (7 * i) % 16;
        }
        const n =
            (a + f + constants[i] + view.getUint32(offset + g * 4, true)) >>> 0,
          k = shift[Math.floor(i / 16) * 4 + (i % 4)];
        a = d;
        d = c;
        c = b;
        b = (b + ((n << k) | (n >>> (32 - k)))) >>> 0;
      }
      a0 = (a0 + a) >>> 0;
      b0 = (b0 + b) >>> 0;
      c0 = (c0 + c) >>> 0;
      d0 = (d0 + d) >>> 0;
      if (offset && offset % 1048576 === 0)
        await new Promise((resolve) => setTimeout(resolve, 0));
    }
    const out = new DataView(new ArrayBuffer(16));
    [a0, b0, c0, d0].forEach((n, i) => out.setUint32(i * 4, n, true));
    return Array.from(new Uint8Array(out.buffer), (n) =>
      n.toString(16).padStart(2, '0')
    ).join('');
  }
  async function fingerprints(blob) {
    return {
      sha256: await sha256(blob),
      md5: await md5(new Uint8Array(await blob.arrayBuffer()))
    };
  }
  async function checkPDF(blob) {
    if (!blob.size || blob.size > MAX_BYTES)
      throw new Error('Bitte eine PDF zwischen 1 Byte und 100 MiB auswählen.');
    const header = new TextDecoder().decode(
      await blob.slice(0, 1024).arrayBuffer()
    );
    if (!header.includes('%PDF-'))
      throw new Error(
        'Die geladene Datei ist keine PDF. Bei geschützten Links die PDF speichern und auswählen.'
      );
  }
  class API {
    constructor(base, tokenProvider, fetcher = fetch) {
      this.base = base;
      this.tokenProvider = tokenProvider;
      // WebIDL fetch requires a Window/Worker receiver. Node's fetch and arrow
      // mocks also accept an API instance, which concealed this browser bug.
      this.fetcher = fetcher.bind(root);
    }
    async request(relative, options = {}) {
      const token = await this.tokenProvider();
      if (!token)
        throw new Error(
          'Sitzung gesperrt. Bitte den API-Token erneut eingeben.'
        );
      const url = apiURL(this.base, relative),
        method = options.method || 'GET';
      let response;
      try {
        response = await this.fetcher(url, {
          method,
          body: options.body,
          credentials: 'omit',
          redirect: 'error',
          cache: 'no-store',
          headers: {
            Authorization: `Token ${token}`,
            Accept: options.image || options.pdf ? '*/*' : 'application/json',
            ...(options.json ? { 'Content-Type': 'application/json' } : {})
          },
          signal: AbortSignal.timeout(options.timeout || 30000)
        });
      } catch (err) {
        // Do not include the raw exception: invalid-header errors may contain
        // header values. Report only a fixed classification and the API URL.
        const reason = ['TimeoutError', 'AbortError'].includes(err?.name)
          ? 'Zeitüberschreitung beim API-Aufruf.'
          : 'Firefox konnte die API-Anfrage nicht ausführen. Netzwerk, TLS-Zertifikat, Erweiterungsberechtigungen oder eine Serverweiterleitung prüfen.';
        const upload =
          new URL(url).pathname.endsWith('/documents/post_document/') &&
          method === 'POST';
        throw new Error(
          `${reason} Anfrage: ${method} ${url}.${upload ? ' Upload-Ergebnis unklar: vor erneutem Senden in Paperless prüfen. Original bleibt erhalten.' : ''}`
        );
      }
      if (!response.ok) {
        const reasons = {
          401: 'API-Token ungültig oder abgelaufen.',
          403: 'Keine Berechtigung für diese Aktion.',
          400: 'Paperless hat die Angaben abgelehnt. Tags und Metadaten prüfen.',
          413: 'Die Datei ist für den Paperless-Server zu groß.'
        };
        throw new Error(
          `${reasons[response.status] || 'API-Anfrage abgelehnt.'} (HTTP ${response.status}; ${method} ${url})`
        );
      }
      if (options.pdf) {
        const length = Number(response.headers.get('Content-Length'));
        if (length > MAX_BYTES) {
          await response.body?.cancel();
          throw new Error('PDF-Vorschau auf 100 MiB begrenzt.');
        }
        const reader = response.body?.getReader();
        let blob;
        if (reader) {
          const chunks = [];
          let size = 0;
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              size += value.byteLength;
              if (size > MAX_BYTES) {
                await reader.cancel();
                throw new Error('PDF-Vorschau auf 100 MiB begrenzt.');
              }
              chunks.push(value);
            }
          } finally {
            reader.releaseLock();
          }
          blob = new Blob(chunks, { type: 'application/pdf' });
        } else blob = await response.blob();
        await checkPDF(blob);
        return blob;
      }
      if (options.image) {
        const blob = await response.blob();
        if (
          !['image/webp', 'image/png', 'image/jpeg'].includes(blob.type) ||
          !blob.size ||
          blob.size > 8 * 1024 * 1024
        )
          throw new Error('Kein gültiges Vorschaubild.');
        return blob;
      }
      try {
        return await response.json();
      } catch (_) {
        throw new Error(
          'Paperless lieferte keine JSON-Antwort. Basis-URL prüfen.'
        );
      }
    }
    async list(endpoint) {
      let page = 1,
        all = [];
      while (true) {
        if (page > 1000) throw new Error('Zu viele API-Seiten.');
        // Reverse proxies may cause absolute next links to advertise an internal
        // host, port or HTTP scheme. Never send credentials to those links.
        // Rebuild every request from our configured base and fixed endpoint.
        const url = apiURL(
          this.base,
          `${endpoint}/?page_size=100&ordering=name&page=${page}`
        );
        const data = await this.request(url);
        if (Array.isArray(data)) return all.concat(data);
        if (!Array.isArray(data.results))
          throw new Error('Unerwartetes Listenformat der API.');
        all.push(...data.results);
        if (!data.next) break;
        let nextPage;
        try {
          const value = new URL(data.next, url).searchParams.get('page');
          if (!/^[1-9][0-9]*$/.test(value || '')) throw new Error();
          nextPage = Number(value);
        } catch (_) {
          throw new Error(
            'Paperless lieferte keine gültige nächste Seitennummer.'
          );
        }
        if (!Number.isSafeInteger(nextPage) || nextPage !== page + 1)
          throw new Error('Ungültige Seitennavigation der API.');
        page = nextPage;
      }
      return all;
    }
    async duplicates(hashes) {
      const found = new Map();
      const lists = await Promise.all(
        [hashes.sha256, hashes.md5].map(async (hash) => {
          if (!/^(?:[a-f0-9]{32}|[a-f0-9]{64})$/.test(hash))
            throw new Error('Ungültige Dateiprüfsumme.');
          const data = await this.request(
            `documents/?checksum__iexact=${hash}&page_size=10&ordering=id`
          );
          const rows = Array.isArray(data) ? data : data?.results;
          if (!Array.isArray(rows))
            throw new Error('Dublettenprüfung: unerwartete API-Antwort.');
          return rows;
        })
      );
      for (const row of lists.flat()) {
        const id = Number(row.id);
        if (!Number.isSafeInteger(id) || id <= 0)
          throw new Error('Dublettenprüfung: ungültige Dokument-ID.');
        if (found.has(id)) continue;
        // Verify the filter result. Never call an arbitrary returned URL or
        // mistake a server ignoring the filter for a positive checksum match.
        const data = await this.request(`documents/${id}/metadata/`);
        if (
          ![hashes.sha256, hashes.md5].includes(
            String(data.original_checksum || '').toLowerCase()
          )
        )
          throw new Error(
            'Dublettenprüfung: Der Server hat den Prüfsummenfilter nicht bestätigt.'
          );
        found.set(id, {
          id,
          title: String(row.title || `Dokument ${id}`).slice(0, 200),
          url: new URL(`documents/${id}/details`, this.base).href
        });
      }
      return [...found.values()];
    }
    async removeInboxTags(documentId) {
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      const definitions = await this.list('tags');
      const inbox = new Set(
        definitions
          .filter((tag) => tag.is_inbox_tag === true)
          .map((tag) => Number(tag.id))
      );
      const path = `documents/${documentId}/`,
        doc = await this.request(path);
      if (
        Number(doc.id) !== documentId ||
        !Array.isArray(doc.tags) ||
        !doc.tags.every((id) => Number.isSafeInteger(id) && id > 0)
      )
        throw new Error('Dokument-Tags konnten nicht sicher gelesen werden.');
      const tags = doc.tags.filter((id) => !inbox.has(id));
      if (tags.length === doc.tags.length) return;
      await this.request(path, {
        method: 'PATCH',
        json: true,
        body: JSON.stringify({ tags })
      });
      const confirmed = await this.request(path);
      if (
        Number(confirmed.id) !== documentId ||
        !Array.isArray(confirmed.tags) ||
        confirmed.tags.some((id) => inbox.has(id))
      )
        throw new Error(
          'Posteingangs-Tags sind weiterhin gesetzt. Bitte Paperless-Workflows prüfen.'
        );
    }
    async createShareLink(documentId, options) {
      if (!Number.isSafeInteger(documentId) || documentId <= 0)
        throw new Error('Ungültige Dokument-ID.');
      if (
        !options ||
        ![0, 1, 7, 30].includes(options.days) ||
        typeof options.archive !== 'boolean'
      )
        throw new Error('Ungültige Freigabeoptionen.');
      const expiration = options.days
        ? new Date(Date.now() + options.days * 86400000).toISOString()
        : null;
      const link = await this.request('share_links/', {
        method: 'POST',
        json: true,
        body: JSON.stringify({
          document: documentId,
          file_version: options.archive ? 'archive' : 'original',
          expiration
        })
      });
      if (typeof link?.slug !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(link.slug))
        throw new Error(
          'Freigabeantwort unklar. Vor erneutem Anlegen die Share Links in Paperless prüfen.'
        );
      return {
        url: new URL('share/' + link.slug, this.base).href,
        expiration: link.expiration ?? expiration
      };
    }
    async upload(blob, filename, raw) {
      const form = new FormData(),
        m = metadata(raw);
      form.append('document', blob, safeName(filename));
      if (m.title) form.append('title', m.title);
      if (m.created) form.append('created', m.created);
      if (m.custom_fields)
        form.append('custom_fields', JSON.stringify(m.custom_fields));
      for (const id of m.tags) form.append('tags', String(id));
      for (const k of ['correspondent', 'document_type', 'storage_path'])
        if (m[k]) form.append(k, String(m[k]));
      return taskID(
        await this.request('documents/post_document/', {
          method: 'POST',
          body: form,
          timeout: 180000
        })
      );
    }
    async task(id) {
      return taskState(
        await this.request(`tasks/?task_id=${encodeURIComponent(id)}`),
        id
      );
    }
  }
  root.Core = {
    MAX_BYTES,
    baseURL,
    apiURL,
    safeName,
    urlName,
    pathURL,
    ids,
    metadata,
    taskID,
    taskState,
    sha256,
    md5,
    fingerprints,
    checkPDF,
    API
  };
})(globalThis);
