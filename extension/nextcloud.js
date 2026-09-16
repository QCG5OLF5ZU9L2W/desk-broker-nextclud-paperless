'use strict';
(function (root) {
  const id = (value) => {
    const n = Number(value);
    if (!Number.isSafeInteger(n) || n <= 0)
      throw new Error('Ungültige Deck-ID.');
    return n;
  };
  const md = (value) =>
    String(value)
      .replace(/[\\`*_{}\[\]()<>#!|]/g, '\\$&')
      .replace(/[\r\n]+/g, ' ');
  function dueDate(date) {
    CustomFields.dateOnly(date);
    const [y, m, d] = date.split('-').map(Number),
      local = new Date();
    local.setFullYear(y, m - 1, d);
    local.setHours(23, 59, 0, 0);
    return local.toISOString();
  }
  function cardData({ name, title, date, url, due }) {
    CustomFields.dateOnly(date);
    const link = new URL(url);
    if (
      !['http:', 'https:'].includes(link.protocol) ||
      link.username ||
      link.password
    )
      throw new Error('Ungültiger Paperless-Link.');
    const href = link.href.replace(/[()]/g, (c) => encodeURIComponent(c));
    return {
      title: `${name}: ${title}`.replace(/[\r\n]+/g, ' ').slice(0, 255),
      type: 'plain',
      order: 999,
      duedate: due || dueDate(date),
      description: `${md(name)}: ${date}\n\n${md(title)}\n\n[Dokument in Paperless öffnen](${href})`
    };
  }
  function matches(card, data) {
    return (
      card &&
      !card.deletedAt &&
      card.title === data.title &&
      card.description === data.description &&
      new Date(card.duedate).getTime() === new Date(data.duedate).getTime()
    );
  }
  class Client {
    constructor(base, username, passwordProvider, fetcher = fetch) {
      this.base = Core.baseURL(base);
      this.username = String(username).trim();
      this.passwordProvider = passwordProvider;
      this.fetcher = fetcher.bind(root);
      if (!this.username || /[:\r\n]/.test(this.username))
        throw new Error(
          'Bitte einen gültigen Nextcloud-Benutzernamen eingeben.'
        );
    }
    async request(path, { method = 'GET', body } = {}) {
      // Only locally constructed Deck routes; no server-provided links with credentials.
      if (
        !/^boards(?:\/[1-9]\d*(?:\/stacks(?:\/[1-9]\d*(?:\/cards(?:\/[1-9]\d*)?)?)?)?)?$/.test(
          path
        )
      )
        throw new Error('Ungültiger Deck-API-Pfad.');
      const url = new URL('index.php/apps/deck/api/v1.0/' + path, this.base)
          .href,
        password = await this.passwordProvider();
      if (!password)
        throw new Error(
          'Nextcloud-Sitzung gesperrt. In den Einstellungen entsperren.'
        );
      const bytes = new TextEncoder().encode(this.username + ':' + password),
        auth = btoa(Array.from(bytes, (c) => String.fromCharCode(c)).join(''));
      let response;
      try {
        response = await this.fetcher(url, {
          method,
          body: body === undefined ? undefined : JSON.stringify(body),
          headers: {
            Authorization: 'Basic ' + auth,
            'OCS-APIRequest': 'true',
            'Content-Type': 'application/json',
            Accept: 'application/json'
          },
          credentials: 'omit',
          redirect: 'error',
          cache: 'no-store',
          signal: AbortSignal.timeout(30000)
        });
      } catch (_) {
        const e = new Error(
          'Nextcloud nicht erreichbar oder Anfrage unterbrochen.'
        );
        e.uncertain = method === 'POST';
        throw e;
      }
      if (!response.ok) {
        const e = new Error(
          `Deck-Anfrage fehlgeschlagen (HTTP ${response.status}). Anmeldung, Deck-Rechte und Serveradresse prüfen.`
        );
        e.uncertain = method === 'POST' && response.status >= 500;
        throw e;
      }
      try {
        return await response.json();
      } catch (_) {
        const e = new Error('Deck lieferte keine gültige JSON-Antwort.');
        e.uncertain = method === 'POST';
        throw e;
      }
    }
    async boards() {
      const data = await this.request('boards');
      if (!Array.isArray(data))
        throw new Error('Deck liefert keine Board-Liste.');
      return data
        .filter(
          (b) =>
            !b.archived &&
            !b.deletedAt &&
            b.permissions?.PERMISSION_EDIT === true
        )
        .map((b) => ({ id: id(b.id), name: String(b.title) }));
    }
    async stacks(board) {
      const data = await this.request(`boards/${id(board)}/stacks`);
      if (!Array.isArray(data)) throw new Error('Deck liefert keine Listen.');
      return data
        .filter((s) => !s.deletedAt)
        .map((s) => ({ ...s, id: id(s.id), name: String(s.title) }));
    }
    async ensureCard(target, entry, data, allowCreate = false) {
      const board = id(target.boardId),
        stack = id(target.stackId),
        route = `boards/${board}/stacks/${stack}/cards`;
      // Search all lists in this board as cards may have been moved after creation.
      const stacks = await this.stacks(board);
      const known = stacks
        .flatMap((s) => (s.cards || []).map((card) => ({ card, stack: s.id })))
        .find((x) =>
          entry.cardId
            ? Number(x.card.id) === entry.cardId
            : matches(x.card, data)
        );
      if (known) {
        if (!matches(known.card, data))
          throw new Error(
            'Die vorhandene Deck-Karte wurde geändert. Bitte in Deck prüfen; sie wird nicht überschrieben.'
          );
        entry.cardId = id(known.card.id);
        entry.attempted = false;
        return this.cardLink(board, entry.cardId);
      }
      if (entry.cardId)
        throw new Error(
          'Die bereits angelegte Deck-Karte ist nicht mehr auffindbar. Bitte in Deck prüfen.'
        );
      if (entry.attempted && !allowCreate) {
        const e = new Error(
          'Die Kartenanlage wurde nicht eindeutig bestätigt. Zuerst in Deck prüfen; es wird keine zweite Karte automatisch angelegt.'
        );
        e.uncertain = true;
        throw e;
      }
      if (!stacks.some((s) => s.id === stack))
        throw new Error('Die gewählte Deck-Liste existiert nicht mehr.');
      entry.attempted = true;
      let card;
      try {
        card = await this.request(route, { method: 'POST', body: data });
      } catch (e) {
        entry.attempted = !!e.uncertain;
        throw e;
      }
      if (!card?.id) {
        const e = new Error('Deck hat keine Karten-ID bestätigt.');
        e.uncertain = true;
        throw e;
      }
      entry.cardId = id(card.id);
      if (!matches(card, data))
        card = await this.request(`${route}/${entry.cardId}`);
      if (!matches(card, data))
        throw new Error(
          'Deck hat Datum und Dokumentlink noch nicht bestätigt. Bitte Karte prüfen.'
        );
      entry.attempted = false;
      return this.cardLink(board, entry.cardId);
    }
    cardLink(board, card) {
      return new URL(
        `index.php/apps/deck/#/board/${id(board)}/card/${id(card)}`,
        this.base
      ).href;
    }
  }
  root.Nextcloud = { Client, dueDate, cardData, matches };
})(globalThis);
