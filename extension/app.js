'use strict';
(async () => {
  const launchURL = new URL(location.href);
  const compact = launchURL.searchParams.has('compact');
  const intent = launchURL.searchParams.get('intent');
  if (compact) document.body.classList.add('compact');
  const $ = (id) => document.getElementById(id);
  const addonVersion = browser.runtime.getManifest().version;
  document.title = 'Paperless Send ' + addonVersion;
  $('addon-version').textContent = 'Paperless Send · ' + addonVersion;
  const P = (await browser.runtime.getBackgroundPage()).Paperless;
  const duplicatePreviews = new DuplicatePreview(P);
  let state = await P.state(),
    files = [],
    tags = [],
    selected = new Set(),
    recent = [],
    jobSignature = '',
    loadingFiles = 0,
    pendingProfile = '',
    closed = false,
    incomingURL = '',
    incomingName = '',
    viewerOriginalId = '',
    metadataLoaded = false,
    annotationPicker = false,
    protectedViewer = false,
    downloadWatchActive = false,
    downloadWatchGeneration = 0,
    sending = false,
    seriesStarted = 0,
    profileEditId = null,
    existingChoice = null,
    suggestionRevision = 0,
    suggestionKey = '',
    seriesQueueOpen = false;
  let assignmentTouched = false,
    seriesRestored = false,
    incomingLoaded = false,
    metadataCatalog = null,
    metadataBase = '',
    metadataRevision = null;
  $('series-mode').checked = state.series?.enabled === true;
  $('series-inherit').checked = state.series?.inherit !== false;
  // Delayed responses must not replace choices already made in this window.
  for (const event of ['input', 'change', 'click'])
    $('assignment-card').addEventListener(event, () => {
      assignmentTouched = true;
    });
  const customEditor = new CustomFields.Editor($('custom-fields'), (message) =>
    notice(message, true)
  );
  let customBase = state.config.base,
    deckLoadRevision = 0,
    titleBase = null,
    sourceCheckContext = '';
  function notice(text, bad = false) {
    $('notice').textContent = text;
    $('notice').classList.toggle('bad', bad);
    $('notice').hidden = !text;
  }
  function on(id, fn, event = 'click') {
    $(id).addEventListener(event, async (e) => {
      try {
        await fn(e);
      } catch (err) {
        notice(err.message, true);
      }
    });
  }
  function textNode(tag, text, cls) {
    const el = document.createElement(tag);
    el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function button(text, fn, cls = 'quiet') {
    const b = textNode('button', text, cls);
    b.type = 'button';
    b.addEventListener('click', () =>
      Promise.resolve()
        .then(fn)
        .catch((e) => notice(e.message, true))
    );
    return b;
  }
  function view(name) {
    for (const x of ['upload', 'history', 'settings'])
      $('view-' + x).hidden = x !== name;
    document
      .querySelectorAll('[data-view]')
      .forEach((b) => b.classList.toggle('active', b.dataset.view === name));
    location.hash = name;
  }
  function theme(mode) {
    document.documentElement.dataset.theme =
      mode === 'auto'
        ? matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : mode;
  }
  let titleHistory = [],
    titleMatches = [],
    titleActive = 0,
    titleFocused = false;
  function renderTitleSuggestions(reset = true) {
    const query = $('title').value.trim().toLocaleLowerCase('de');
    titleMatches = titleHistory
      .filter((t) => t.toLocaleLowerCase('de').includes(query))
      .sort(
        (a, b) =>
          Number(b.toLocaleLowerCase('de').startsWith(query)) -
          Number(a.toLocaleLowerCase('de').startsWith(query))
      )
      .slice(0, 8);
    if (reset) titleActive = 0;
    titleActive = Math.max(0, Math.min(titleActive, titleMatches.length - 1));
    $('title-suggestions').replaceChildren();
    titleMatches.forEach((title, index) => {
      const option = textNode('div', title, 'title-option');
      option.id = 'title-option-' + index;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(index === titleActive));
      option.addEventListener('pointerdown', (e) => e.preventDefault());
      option.addEventListener('click', () => {
        void chooseTitle(index).catch((e) => notice(e.message, true));
      });
      $('title-suggestions').append(option);
    });
    const open = titleFocused && titleMatches.length > 0;
    $('title-suggestions').hidden = !open;
    $('title').setAttribute('aria-expanded', String(open));
    $('title').setAttribute(
      'aria-activedescendant',
      open ? 'title-option-' + titleActive : ''
    );
    if (open)
      $('title-suggestions').children[titleActive]?.scrollIntoView?.({
        block: 'nearest'
      });
  }
  function closeTitleSuggestions() {
    titleFocused = false;
    $('title-suggestions').hidden = true;
    $('title').setAttribute('aria-expanded', 'false');
    $('title').setAttribute('aria-activedescendant', '');
  }
  async function chooseTitle(index) {
    if (!titleMatches[index]) return;
    $('title').value = titleMatches[index];
    closeTitleSuggestions();
    await P.rememberTitle($('title').value, state.config.base);
    await loadTitleSuggestions();
  }
  async function loadTitleSuggestions() {
    const base = state.config.base,
      titles = await P.titleHistory();
    if (base !== state.config.base) return;
    titleHistory = titles;
    renderTitleSuggestions();
  }
  on(
    'title',
    () => {
      titleFocused = true;
      renderTitleSuggestions();
    },
    'input'
  );
  on(
    'title',
    () => {
      titleFocused = true;
      renderTitleSuggestions();
    },
    'focus'
  );
  on('title', closeTitleSuggestions, 'blur');
  on(
    'title',
    async (e) => {
      if (e.isComposing || e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        closeTitleSuggestions();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const wasOpen = !$('title-suggestions').hidden;
        titleFocused = true;
        if (wasOpen && titleMatches.length)
          titleActive =
            (titleActive +
              (e.key === 'ArrowDown' ? 1 : -1) +
              titleMatches.length) %
            titleMatches.length;
        renderTitleSuggestions(false);
        return;
      }
      if (
        e.key === 'Enter' &&
        !$('title-suggestions').hidden &&
        titleMatches.length
      ) {
        e.preventDefault();
        await chooseTitle(titleActive);
      }
    },
    'keydown'
  );
  on(
    'title',
    async () => {
      await P.rememberTitle($('title').value, state.config.base);
      await loadTitleSuggestions();
    },
    'change'
  );
  function syncDatePicker() {
    const parsed = CustomFields.documentDate($('created').value);
    $('created').value = parsed.display;
    const match = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(parsed.display);
    $('created-picker').value = match
      ? `${match[3]}-${match[2]}-${match[1]}`
      : '';
  }
  on('created', syncDatePicker, 'change');
  on('open-calendar', () => {
    try {
      syncDatePicker();
    } catch (_) {
      $('created-picker').value = '';
    }
    $('created-picker').showPicker();
  });
  on(
    'created-picker',
    () => {
      const time = / (\d{2}:\d{2})$/.exec($('created').value)?.[1];
      $('created').value = CustomFields.documentDate(
        $('created-picker').value +
          ($('created-picker').value && time ? 'T' + time : '')
      ).display;
      $('created').focus();
    },
    'change'
  );
  on('clear-title-history', async () => {
    await P.clearTitleHistory();
    await loadTitleSuggestions();
    notice('Titelverlauf dieser Paperless-Instanz gelöscht.');
  });
  function profileOptionsText(p) {
    const sharing = p?.share
      ? `Öffentlicher Link: ${p.share.days ? p.share.days + ' Tage' : 'unbefristet'}${p.share.archive ? ' · Archivversion' : ''}`
      : 'Kein öffentlicher Link';
    return (
      sharing +
      ' · ' +
      (p?.complete_tagging
        ? 'Posteingangs-Tags entfernen'
        : 'Posteingangs-Tags beibehalten')
    );
  }
  let keyboardDraft = { ...Shortcuts.defaults };
  function renderKeyboardSettings() {
    keyboardDraft = { ...Shortcuts.defaults, ...state.config.shortcuts };
    $('fast-tabs').checked = state.config.fastTabs !== false;
    $('keyboard-bindings').replaceChildren();
    for (const [action, label] of Object.entries(Shortcuts.labels)) {
      const row = textNode('div', '', 'keyboard-binding'),
        name = textNode('label', label),
        input = document.createElement('input');
      input.id = 'shortcut-' + action;
      name.htmlFor = input.id;
      input.readOnly = true;
      input.value = keyboardDraft[action];
      input.placeholder = 'Deaktiviert';
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Tab' || e.key === 'Escape') return;
        e.preventDefault();
        if (e.key === 'Backspace' || e.key === 'Delete') {
          input.value = '';
          keyboardDraft[action] = '';
          return;
        }
        const value = Shortcuts.eventKey(e);
        if (value) {
          input.value = value;
          keyboardDraft[action] = value;
        }
      });
      row.append(
        name,
        input,
        button('Aus', () => {
          input.value = '';
          keyboardDraft[action] = '';
          input.focus();
        })
      );
      $('keyboard-bindings').append(row);
    }
  }
  on(
    'keyboard-form',
    async (e) => {
      e.preventDefault();
      state = await P.saveKeyboard({
        shortcuts: keyboardDraft,
        fastTabs: $('fast-tabs').checked
      });
      renderKeyboardSettings();
      notice('Tastenkürzel und Tab-Bereiche gespeichert.');
    },
    'submit'
  );
  on('keyboard-reset', () => {
    keyboardDraft = { ...Shortcuts.defaults };
    for (const action of Object.keys(keyboardDraft))
      $('shortcut-' + action).value = keyboardDraft[action];
    $('fast-tabs').checked = true;
  });
  const shortcutTargets = {
    send: 'send',
    profile: 'save-profile',
    tags: 'tag-search',
    calendar: 'open-calendar',
    share: 'quick-share'
  };
  window.addEventListener('keydown', (e) => {
    if (
      e.isComposing ||
      $('view-upload').hidden ||
      document.querySelectorAll('dialog[open]').length
    )
      return;
    if (
      e.key === 'Tab' &&
      !e.ctrlKey &&
      !e.altKey &&
      !e.metaKey &&
      state.config.fastTabs !== false &&
      e.target.closest?.('.metadata-card')
    ) {
      const stops = [
        ...document.querySelectorAll('.metadata-card [data-tab-stop]')
      ].filter(
        (node) =>
          !node.disabled &&
          node.getClientRects().length &&
          !node.closest('[hidden]')
      );
      const next = Shortcuts.nextStop(stops, e.target, e.shiftKey);
      if (next) {
        e.preventDefault();
        next.focus();
      }
      return;
    }
    const binding = Shortcuts.eventKey(e);
    if (!binding) return;
    const settings = { ...Shortcuts.defaults, ...state.config.shortcuts },
      action = Object.keys(settings).find((key) => settings[key] === binding);
    if (!action) return;
    e.preventDefault();
    if (e.repeat) return;
    const target = $(shortcutTargets[action]);
    if (target.disabled) return;
    if (action === 'tags') target.focus();
    else target.click();
  });
  function renderState() {
    duplicatePreviews.sync(state);
    syncSourceChecks();
    if (titleBase !== state.config.base) {
      titleBase = state.config.base;
      titleHistory = [];
      closeTitleSuggestions();
      $('title-suggestions').replaceChildren();
      void loadTitleSuggestions().catch(() => {});
    }
    if (customBase !== state.config.base) {
      customEditor.setFields([]);
      customBase = state.config.base;
      $('custom-fields-status').textContent =
        'Benutzerdefinierte Felder für das neue Ziel laden.';
    }
    renderDeckStatus();
    const priorProfile = $('profile').value;
    $('session-state').textContent = state.unlocked
      ? 'Sitzung verbunden'
      : 'Sitzung gesperrt';
    $('session-state').classList.toggle('connected', state.unlocked);
    $('connect').textContent = state.unlocked
      ? 'Verbindung aktiv'
      : 'Sitzung entsperren';
    $('connect').disabled = state.unlocked;
    $('lock').disabled = !state.unlocked;
    $('helper-status').textContent = state.helperAllowed
      ? 'Firefox-Berechtigung aktiviert. Helfer mit „Verbindung testen“ prüfen.'
      : 'Dateihelfer ist optional. API-Uploads funktionieren auch ohne ihn.';
    $('profile').replaceChildren(new Option('Individuelle Zuordnung', ''));
    for (const p of state.config.profiles)
      $('profile').append(
        new Option(p.name + (p.share ? ' · öffentlich' : ''), p.id)
      );
    $('profile').value = priorProfile;
    $('target-server').textContent = state.config.base
      ? 'Ziel: ' + state.config.base
      : 'Noch keine Paperless-Adresse eingerichtet';
    $('profiles-list').replaceChildren();
    if (!state.config.profiles.length)
      $('profiles-list').append(
        textNode(
          'p',
          'Noch keine Profile gespeichert. Auf der Upload-Seite Tags und weitere Angaben auswählen und als Profil speichern.',
          'muted small'
        )
      );
    for (const p of state.config.profiles) {
      const row = textNode('div', '', 'profile-row');
      row.append(
        textNode(
          'span',
          `${p.name} · ${p.tags.length} Tags · ${profileOptionsText(p)}`
        ),
        button('Entfernen', async () => {
          await P.removeProfile(p.id);
          state = await P.state();
          renderState();
        })
      );
      $('profiles-list').append(row);
    }
    $('base').value = state.config.base;
    $('allow-http').checked = state.config.allowHttp;
    $('erase-history').checked = state.config.eraseHistory;
    $('theme').value = state.config.theme;
    theme(state.config.theme);
    updateSend();
  }
  function assignmentSummary() {
    const name = (key) =>
      singleItems[key].find((x) => String(x.id) === String($(key).value))?.name;
    const parts = [
      name('document_type'),
      name('correspondent'),
      selected.size + ' Tags'
    ];
    if ($('share-enabled').checked)
      parts.push(
        'Öffentlich: ' +
          (Number($('share-days').value)
            ? $('share-days').value + ' Tage'
            : 'unbefristet')
      );
    if ($('complete-tagging').checked) parts.push('Fertig zugeordnet');
    $('assignment-summary').textContent = parts.filter(Boolean).join(' · ');
    $('update-profile').hidden = !state.config.profiles.some(
      (p) => p.id === $('profile').value
    );
  }
  function resetDocumentFields() {
    $('title').value = '';
    closeTitleSuggestions();
    if (!$('series-inherit').checked) {
      customEditor.resetValues();
      selected.clear();
      for (const key of [
        'correspondent',
        'document_type',
        'storage_path',
        'profile'
      ])
        $(key).value = '';
      $('complete-tagging').checked = false;
    }
    cancelDownloadWatch();
    incomingURL = '';
    incomingName = '';
    viewerOriginalId = '';
    protectedViewer = false;
    $('annotation-choice').hidden = true;
    sourceStatus('');
    for (const key of [
      'tag-search',
      'correspondent-search',
      'document_type-search'
    ])
      $(key).value = '';
    renderTags();
    for (const key of Object.keys(singleItems)) renderSingle(key);
  }
  on(
    'series-mode',
    async () => {
      renderFiles();
      await saveSeriesOptions();
      await restoreSeriesAssignment();
    },
    'change'
  );
  on(
    'series-inherit',
    async () => {
      await saveSeriesOptions();
      await restoreSeriesAssignment();
    },
    'change'
  );
  async function saveSeriesOptions() {
    if (!state.unlocked) return;
    await P.saveSeriesOptions(
      {
        enabled: $('series-mode').checked,
        inherit: $('series-inherit').checked
      },
      state.config.base,
      state.previewRevision
    );
  }
  async function restoreSeriesAssignment() {
    const wanted = () =>
      incomingLoaded &&
      metadataLoaded &&
      $('series-mode').checked &&
      $('series-inherit').checked &&
      !assignmentTouched &&
      !seriesRestored &&
      metadataBase === state.config.base &&
      metadataRevision === state.previewRevision;
    if (!wanted()) return;
    const base = state.config.base,
      revision = state.previewRevision;
    const current = await P.state();
    if (
      !wanted() ||
      !current.unlocked ||
      base !== current.config.base ||
      revision !== current.previewRevision
    )
      return;
    const previous = current.series?.assignment;
    if (!previous) return;
    const missing = [];
    selected = new Set(
      (previous.tags || [])
        .filter((id) => {
          if (tags.some((tag) => Number(tag.id) === Number(id))) return true;
          missing.push('Tag ' + id);
          return false;
        })
        .map(Number)
    );
    for (const [field, list] of [
      ['correspondent', 'correspondents'],
      ['document_type', 'document_types'],
      ['storage_path', 'storage_paths']
    ]) {
      const value = previous[field];
      const available = metadataCatalog[list].some(
        (item) => Number(item.id) === Number(value)
      );
      $(field).value = value && available ? String(value) : '';
      if (value && !available) missing.push(field);
    }
    // Import per field: a removed/changed definition must not discard the rest.
    for (const [id, value] of Object.entries(previous.custom_fields || {})) {
      try {
        customEditor.importValues({ [id]: value });
      } catch (error) {
        missing.push(error.message);
      }
    }
    if (previous.created) {
      const date = new Date(previous.created),
        pad = (value) => String(value).padStart(2, '0');
      $('created').value =
        `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
      syncDatePicker();
    }
    $('complete-tagging').checked = previous.complete_tagging === true;
    $('profile').value = '';
    seriesRestored = true;
    renderTags();
    for (const key of Object.keys(singleItems)) renderSingle(key);
    updateSend();
    if (missing.length)
      notice(
        'Letzte Zuordnung teilweise übernommen. Nicht mehr verfügbar: ' +
          missing.join(', '),
        true
      );
  }
  on('series-add', () => {
    annotationPicker = false;
    $('file-input').click();
  });
  on('series-history', () => view('history'));
  on('series-return', () => view('upload'));
  async function loadAssignmentSuggestions() {
    const correspondent = $('correspondent').value,
      base = state.config.base,
      key = JSON.stringify([base, correspondent]);
    if (key === suggestionKey) return;
    suggestionKey = key;
    const revision = ++suggestionRevision;
    $('assignment-suggestions').hidden = true;
    $('assignment-suggestions').replaceChildren();
    if (!correspondent) return;
    const choices = await P.assignmentSuggestions(correspondent);
    if (
      revision !== suggestionRevision ||
      base !== state.config.base ||
      correspondent !== $('correspondent').value
    )
      return;
    const valid = choices.filter(
      (choice) =>
        (!choice.document_type ||
          singleItems.document_type.some(
            (t) => Number(t.id) === choice.document_type
          )) &&
        choice.tags.every((id) => tags.some((t) => Number(t.id) === id))
    );
    for (const choice of valid) {
      const type =
        singleItems.document_type.find(
          (t) => Number(t.id) === choice.document_type
        )?.name || 'Kein Dokumenttyp';
      const names = choice.tags
        .map((id) => tags.find((t) => Number(t.id) === id).name)
        .join(', ');
      $('assignment-suggestions').append(
        button(
          `${type} · ${names || 'keine Tags'} übernehmen`,
          () => {
            for (const id of choice.tags) selected.add(id);
            $('document_type').value = choice.document_type
              ? String(choice.document_type)
              : '';
            renderTags();
            renderSingle('document_type');
            assignmentSummary();
          },
          'secondary'
        )
      );
    }
    $('assignment-suggestions').hidden = !valid.length;
  }
  on('clear-assignment-history', async () => {
    await P.clearAssignmentHistory();
    suggestionKey = '';
    await loadAssignmentSuggestions();
    notice('Zuordnungsverlauf gelöscht.');
  });
  function openExisting(file, match) {
    existingChoice = { file, match, base: state.config.base };
    $('existing-days').value = $('share-days').value;
    $('existing-archive').checked = $('share-archive').checked;
    $('existing-title').textContent = match.title;
    $('existing-error').textContent = '';
    $('existing-dialog').showModal();
  }
  async function useExisting(
    file,
    match,
    share = null,
    base = state.config.base
  ) {
    if (sending || file.existingBusy) return;
    file.existingBusy = true;
    renderFiles();
    try {
      const result = await P.useExistingDuplicate(
        file.id,
        match.id,
        share,
        base
      );
      if (!files.includes(file) || base !== state.config.base) return;
      await P.removeSource(file.id);
      const wasCurrent = files[0] === file;
      files = files.filter((f) => f !== file);
      if ($('series-mode').checked && wasCurrent) resetDocumentFields();
      const link = textNode('a', result.url);
      link.href = result.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      $('existing-result').replaceChildren(
        textNode(
          'span',
          result.copied
            ? 'Vorhandenes Dokument · Link kopiert: '
            : 'Vorhandenes Dokument · Link zum Kopieren: '
        ),
        link
      );
      $('existing-result').hidden = false;
      notice(
        'Vorhandenes Dokument genutzt. Kein Upload; lokale Datei beibehalten.'
      );
    } finally {
      file.existingBusy = false;
      renderFiles();
    }
  }
  on(
    'existing-form',
    async (e) => {
      e.preventDefault();
      if (!existingChoice) return;
      $('existing-submit').disabled = true;
      try {
        const { file, match, base } = existingChoice;
        await useExisting(
          file,
          match,
          {
            days: Number($('existing-days').value),
            archive: $('existing-archive').checked
          },
          base
        );
        $('existing-dialog').close();
      } catch (e) {
        $('existing-error').textContent = e.message;
      } finally {
        $('existing-submit').disabled = false;
      }
    },
    'submit'
  );
  function rawMetadata() {
    return {
      title: $('title').value,
      created: CustomFields.documentDate($('created').value).iso,
      tags: [...selected],
      correspondent: $('correspondent').value,
      document_type: $('document_type').value,
      storage_path: $('storage_path').value,
      custom_fields: customEditor.read(),
      deck_fields: customEditor.deckFields(),
      complete_tagging: $('complete-tagging').checked,
      share: $('share-enabled').checked
        ? {
            days: Number($('share-days').value),
            archive: $('share-archive').checked
          }
        : null
    };
  }
  function renderDeckStatus() {
    const target = state.config.nextcloud;
    customEditor.setDeckEnabled(!!(target && state.nextcloudUnlocked));
    $('deck-hint').textContent = target
      ? state.nextcloudUnlocked
        ? `Deck-Ziel: ${target.boardName} → ${target.stackName}. Gewünschte Datumsfelder einzeln aktivieren.`
        : 'Nextcloud-Sitzung gesperrt. Zum Anlegen von Deck-Karten in den Einstellungen verbinden.'
      : 'Optional: Nextcloud Deck in den Einstellungen verbinden, um Datumsfelder als Karten zu übernehmen.';
    $('cloud-status').textContent = target
      ? `${state.nextcloudUnlocked ? 'Verbunden' : 'Sitzung gesperrt'} · Gespeichertes Ziel: ${target.boardName} → ${target.stackName}`
      : 'Noch kein Deck-Ziel gespeichert.';
  }
  async function loadDeckStacks() {
    const board = $('deck-board').value,
      revision = ++deckLoadRevision;
    $('deck-stack').replaceChildren(new Option('Listen werden geladen …', ''));
    $('cloud-save').disabled = true;
    if (!board) return;
    const stacks = await P.deckStacks(board);
    if (revision !== deckLoadRevision) return;
    $('deck-stack').replaceChildren(new Option('Liste auswählen', ''));
    for (const stack of stacks)
      $('deck-stack').append(new Option(stack.name, stack.id));
    const target = state.config.nextcloud;
    if (
      target?.boardId === Number(board) &&
      stacks.some((s) => s.id === target.stackId)
    )
      $('deck-stack').value = String(target.stackId);
    else if (stacks.length === 1) $('deck-stack').value = String(stacks[0].id);
    $('cloud-save').disabled = false;
    if (!stacks.length)
      notice(
        'Dieses Board hat noch keine Liste. Bitte in Deck eine Liste anlegen.'
      );
  }
  on('cloud-connect', async () => {
    const password = $('cloud-password').value;
    $('cloud-password').value = '';
    $('cloud-connect').disabled = true;
    try {
      const boards = await P.connectNextcloud({
        base: $('cloud-base').value,
        username: $('cloud-user').value,
        password
      });
      $('deck-board').replaceChildren(new Option('Board auswählen', ''));
      for (const board of boards)
        $('deck-board').append(new Option(board.name, board.id));
      const saved = state.config.nextcloud?.boardId;
      $('deck-board').value = String(
        boards.some((b) => b.id === saved) ? saved : boards[0].id
      );
      state = await P.state();
      renderDeckStatus();
      await loadDeckStacks();
      notice(
        'Nextcloud verbunden. Board und Liste auswählen und Deck-Ziel speichern.'
      );
    } finally {
      $('cloud-password').value = '';
      $('cloud-connect').disabled = false;
    }
  });
  on('deck-board', loadDeckStacks, 'change');
  on(
    'deck-form',
    async (e) => {
      e.preventDefault();
      state = await P.saveNextcloud({
        base: $('cloud-base').value,
        username: $('cloud-user').value,
        boardId: $('deck-board').value,
        stackId: $('deck-stack').value
      });
      renderDeckStatus();
      notice(
        'Deck-Ziel gespeichert. Gewünschte Datumsfelder beim Senden aktivieren.'
      );
    },
    'submit'
  );
  on('cloud-lock', async () => {
    state = await P.lockNextcloud();
    $('cloud-password').value = '';
    renderDeckStatus();
    notice('Nextcloud-App-Passwort aus der Sitzung entfernt.');
  });
  const tagCursor = new SearchList.Cursor();
  let tagMatches = [];
  function renderTags(reset = true) {
    const query = $('tag-search').value.toLocaleLowerCase('de');
    $('tag-list').replaceChildren();
    $('selected-tags').replaceChildren();
    const byId = new Map(tags.map((t) => [t.id, t]));
    for (const id of selected) {
      const t = byId.get(id),
        chip = button(
          (t?.name || `Tag ${id}`) + ' ×',
          () => {
            selected.delete(id);
            renderTags();
          },
          'tag-chip'
        );
      chip.title = 'Auswahl entfernen';
      $('selected-tags').append(chip);
    }
    const sorted = [...tags].sort(
      (a, b) =>
        Number(selected.has(b.id)) - Number(selected.has(a.id)) ||
        Number(recent.includes(b.id)) - Number(recent.includes(a.id)) ||
        a.name.localeCompare(b.name, 'de')
    );
    tagMatches = SearchList.rank(
      sorted.filter((t) => !selected.has(t.id)),
      query
    );
    tagCursor.clamp(tagMatches.length, reset);
    for (const tag of tagMatches) {
      const label = textNode('label', '', 'tag-option'),
        input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = selected.has(tag.id);
      input.addEventListener('change', () => {
        input.checked ? selected.add(tag.id) : selected.delete(tag.id);
        renderTags();
      });
      const dot = textNode('span', '', 'tag-dot');
      dot.style.backgroundColor = /^#[a-f0-9]{6}$/i.test(tag.color)
        ? tag.color
        : '#17541f';
      label.append(input, dot, textNode('span', tag.name));
      if (recent.includes(tag.id))
        label.append(textNode('small', 'zuletzt verwendet'));
      $('tag-list').append(label);
    }
    SearchList.paint($('tag-search'), $('tag-list'), tagCursor.index);
    if (!$('tag-list').children.length)
      $('tag-list').append(
        textNode(
          'p',
          state.unlocked
            ? 'Keine passenden Tags.'
            : 'Sitzung entsperren, um Tags aus Paperless zu laden.',
          'empty'
        )
      );
    $('tag-count').textContent = selected.size;
    assignmentSummary();
  }
  const singleItems = { correspondent: [], document_type: [] },
    singleCursors = {
      correspondent: new SearchList.Cursor(),
      document_type: new SearchList.Cursor()
    },
    singleMatches = {};
  function renderSingle(key, reset = true) {
    const query = $(key + '-search').value.toLocaleLowerCase('de'),
      value = String($(key).value);
    $(key + '-selected').replaceChildren();
    $(key + '-list').replaceChildren();
    const current = singleItems[key].find((item) => String(item.id) === value);
    if (current)
      $(key + '-selected').append(
        button(
          current.name + ' ×',
          () => {
            $(key).value = '';
            renderSingle(key);
          },
          'tag-chip'
        )
      );
    const matches = SearchList.rank(
      singleItems[key].filter((item) => String(item.id) !== value),
      query
    );
    singleMatches[key] = matches;
    singleCursors[key].clamp(matches.length, reset);
    for (const item of matches) {
      const label = textNode('label', '', 'tag-option'),
        input = document.createElement('input');
      input.type = 'radio';
      input.name = key + '-choice';
      input.checked = String(item.id) === value;
      input.addEventListener('change', () => {
        $(key).value = String(item.id);
        $(key + '-search').value = '';
        renderSingle(key);
      });
      label.append(input, textNode('span', item.name));
      $(key + '-list').append(label);
    }
    SearchList.paint(
      $(key + '-search'),
      $(key + '-list'),
      singleCursors[key].index
    );
    if (!matches.length)
      $(key + '-list').append(
        textNode('p', 'Keine passenden Einträge.', 'empty')
      );
    assignmentSummary();
    if (key === 'correspondent')
      void loadAssignmentSuggestions().catch(() => {});
  }
  for (const key of Object.keys(singleItems)) {
    on(key + '-search', () => renderSingle(key), 'input');
    on(
      key + '-search',
      (e) =>
        singleCursors[key].key(
          e,
          singleMatches[key] || [],
          (item) => {
            $(key).value = String(item.id);
            $(key + '-search').value = '';
            renderSingle(key);
          },
          (reset) => renderSingle(key, reset)
        ),
      'keydown'
    );
  }
  function syncShareControls() {
    const enabled = $('share-enabled').checked;
    $('share-options').hidden = !enabled;
    $('quick-share').setAttribute('aria-pressed', String(enabled));
    for (const key of ['off', '7', '30', '0', '1'])
      $('share-' + key).setAttribute(
        'aria-pressed',
        String(
          key === 'off' ? !enabled : enabled && $('share-days').value === key
        )
      );
    $('share-1').hidden = !enabled || $('share-days').value !== '1';
    assignmentSummary();
    $('quick-share').textContent = enabled
      ? 'Öffentlicher Link: ' +
        (Number($('share-days').value)
          ? $('share-days').value + ' Tage'
          : 'unbefristet')
      : 'Öffentlicher Link: aus';
  }
  on('complete-tagging', assignmentSummary, 'change');
  for (const key of ['off', '7', '30', '0', '1'])
    on('share-' + key, () => {
      $('share-enabled').checked = key !== 'off';
      if (key !== 'off') $('share-days').value = key;
      syncShareControls();
    });
  on('share-enabled', syncShareControls, 'change');
  on('share-days', syncShareControls, 'change');
  on('quick-share', () => {
    $('share-enabled').checked = !$('share-enabled').checked;
    syncShareControls();
  });
  async function loadMetadata(refresh = false) {
    $('refresh-tags').disabled = true;
    const base = state.config.base,
      revision = state.previewRevision;
    try {
      const data = await P.metadata(refresh);
      tags = data.tags;
      recent =
        (await browser.storage.session.get('recentTags')).recentTags || [];
      renderTags();
      for (const [field, key] of [
        ['correspondent', 'correspondents'],
        ['document_type', 'document_types'],
        ['storage_path', 'storage_paths']
      ]) {
        const prev = $(field).value;
        $(field).replaceChildren(new Option('Automatisch / keine Vorgabe', ''));
        for (const item of data[key])
          $(field).append(new Option(item.name, item.id));
        $(field).value = prev;
        if (singleItems[field]) {
          singleItems[field] = data[key];
          renderSingle(field);
        }
      }
      if (data.custom_fields_error) {
        $('custom-fields-status').textContent =
          'Benutzerdefinierte Felder konnten nicht geladen werden. Bitte Leserechte prüfen und aktualisieren. Vorhandene Eingaben bleiben erhalten.';
      } else {
        customEditor.setFields(data.custom_fields || []);
        $('custom-fields-status').textContent = data.custom_fields?.length
          ? 'Felder aus Paperless · Datumswerte ohne Uhrzeit'
          : 'Keine benutzerdefinierten Felder in Paperless vorhanden.';
      }
      metadataLoaded = true;
      metadataCatalog = data;
      metadataBase = base;
      metadataRevision = revision;
      suggestionKey = '';
      void loadAssignmentSuggestions().catch(() => {});
      if (pendingProfile) {
        applyProfile(pendingProfile, true);
        pendingProfile = '';
      }
      await restoreSeriesAssignment();
      updateSend();
      if (data.warnings.length)
        notice(
          'Tags geladen. Einige weitere Auswahllisten sind nicht verfügbar: ' +
            data.warnings.join(' ')
        );
      return data;
    } finally {
      $('refresh-tags').disabled = false;
    }
  }
  function applyProfile(id, metadataOnly = false) {
    if (!metadataOnly) assignmentTouched = true;
    const p = state.config.profiles.find((x) => x.id === id);
    $('profile').value = id;
    selected = new Set(p?.tags || []);
    if (!metadataOnly) {
      $('share-enabled').checked = !!p?.share;
      $('share-options').hidden = !p?.share;
      $('share-days').value = String(p?.share?.days ?? 7);
      $('share-archive').checked = p?.share?.archive === true;
      $('complete-tagging').checked = p?.complete_tagging === true;
      syncShareControls();
    }
    for (const k of ['correspondent', 'document_type', 'storage_path'])
      $(k).value = p?.[k] || '';
    for (const key of Object.keys(singleItems)) renderSingle(key);
    renderTags();
    updateSend();
  }
  function updateSend() {
    const scope = $('series-mode').checked ? files.slice(0, 1) : files;
    const eligible = scope.length > 0 && scope.every((f) => f.canDelete);
    $('delete-local').disabled = !eligible;
    if (!eligible) $('delete-local').checked = false;
    $('send').disabled =
      sending ||
      files.some((f) => f.existingBusy) ||
      files.length === 0 ||
      loadingFiles > 0 ||
      (!!pendingProfile && !metadataLoaded);
    $('quick-send').disabled = $('send').disabled;
    $('series-mode').disabled = sending || files.some((f) => f.existingBusy);
    $('series-inherit').disabled = $('series-mode').disabled;
    $('series-inherit-option').hidden = !$('series-mode').checked;
    const knownDuplicate = scope.some((f) => f.precheck?.state === 'duplicate');
    $('send').textContent = knownDuplicate
      ? $('series-mode').checked
        ? '↥ Trotz Doublette senden · weiter'
        : '↥ Trotz Doublette senden'
      : $('series-mode').checked
        ? '↥ Diese PDF senden · weiter'
        : '↥ An Paperless senden';
    $('quick-send').textContent = knownDuplicate
      ? 'Trotz Doublette senden'
      : 'Senden';
    $('series-add').hidden = !$('series-mode').checked;
    $('series-history').hidden = !$('series-mode').checked;
    $('series-return').hidden = !$('series-mode').checked;
    $('series-status').hidden = !$('series-mode').checked;
    $('series-status').textContent =
      `${files.length} PDF(s) in der Warteschlange · ${seriesStarted} Auftrag/Aufträge gestartet` +
      (seriesRestored ? ' · Letzte Zuordnung übernommen' : '');
    assignmentSummary();
    $('selection-summary').textContent =
      loadingFiles > 0
        ? 'PDF wird übernommen …'
        : files.length
          ? `${files.length} ${files.length === 1 ? 'Dokument bereit' : 'Dokumente bereit'}${state.unlocked ? '' : ' · Sitzung vor dem Senden entsperren'}`
          : 'Noch keine Datei ausgewählt';
    $('delete-hint').textContent = eligible
      ? 'Löscht die ausgewählten Originale endgültig, sobald Paperless die Archivierung bestätigt hat. Bei Fehlern bleiben sie erhalten.'
      : 'Für lokale Dateien den Dateihelfer oder die Firefox-Downloadliste verwenden. Eine normale Dateiauswahl übermittelt keinen löschbaren Dateipfad.';
  }
  function syncSourceChecks() {
    const context = JSON.stringify([state.config.base, state.unlocked]);
    if (context === sourceCheckContext) return;
    sourceCheckContext = context;
    for (const file of files) void checkSource(file);
  }
  async function checkSource(file) {
    const marker = {
        state: state.unlocked ? 'checking' : 'locked',
        matches: []
      },
      base = state.config.base;
    file.precheck = marker;
    renderFiles();
    if (!state.unlocked) return;
    try {
      const result = await P.precheckSource(file.id, base);
      if (
        !closed &&
        files.includes(file) &&
        file.precheck === marker &&
        base === state.config.base
      ) {
        file.precheck = result;
        renderFiles();
      }
    } catch (e) {
      if (
        !closed &&
        files.includes(file) &&
        file.precheck === marker &&
        base === state.config.base
      ) {
        file.precheck = { state: 'error', matches: [], message: e.message };
        renderFiles();
      }
    }
  }
  async function importDuplicateAssignment(file, match) {
    if (sending || file.existingBusy || !files.includes(file)) return;
    assignmentTouched = true;
    const base = state.config.base;
    file.existingBusy = true;
    renderFiles();
    try {
      const assignment = await P.documentAssignment(match.id, base);
      const catalog = await loadMetadata(true);
      if (closed || state.config.base !== base || !files.includes(file)) return;
      const available = {
        correspondent: catalog.correspondents,
        document_type: catalog.document_types,
        storage_path: catalog.storage_paths
      };
      for (const key of ['correspondent', 'document_type', 'storage_path'])
        if (
          assignment[key] &&
          !available[key].some((item) => Number(item.id) === assignment[key])
        )
          throw new Error(
            'Eine Zuordnung der Doublette ist nicht mehr verfügbar.'
          );
      customEditor.importValues(assignment.custom_fields);
      for (const id of assignment.tags) selected.add(id);
      for (const key of ['correspondent', 'document_type', 'storage_path']) {
        $(key).value = assignment[key] ? String(assignment[key]) : '';
        if (singleItems[key]) {
          $(key + '-search').value = '';
          renderSingle(key);
        }
      }
      $('tag-search').value = '';
      renderTags();
      updateSend();
      notice(
        `Zuordnung aus „${match.title}“ übernommen. Du kannst sie weiter ergänzen und ändern.`
      );
    } finally {
      file.existingBusy = false;
      renderFiles();
    }
  }
  function renderFiles() {
    if (compact) document.body.classList.toggle('has-files', files.length > 0);
    $('files').replaceChildren();
    const queued = textNode('details', '', 'series-queue');
    queued.open = seriesQueueOpen;
    queued.addEventListener('toggle', () => {
      seriesQueueOpen = queued.open;
    });
    queued.append(
      textNode(
        'summary',
        `${Math.max(0, files.length - 1)} weitere PDF(s) in der Warteschlange`
      )
    );
    const kind = {
      web: 'Web-PDF · kein lokales Original',
      helper: 'Dateihelfer · Löschen verfügbar',
      download: 'Firefox-Download · Löschen verfügbar',
      picker: 'Dateiauswahl · Original bleibt erhalten',
      local: 'Lokale PDF · Original bleibt erhalten'
    };
    for (const f of files) {
      const row = textNode('div', '', 'file-row'),
        meta = textNode('div', '', 'file-meta');
      meta.append(
        textNode('div', f.name, 'file-name'),
        textNode(
          'div',
          `${(f.size / 1024 / 1024).toLocaleString('de', { maximumFractionDigits: 2 })} MiB · ${kind[f.kind]}`,
          'file-sub'
        )
      );
      if ($('series-mode').checked)
        meta.append(
          textNode(
            'div',
            files[0] === f
              ? 'Jetzt bearbeiten'
              : 'Wartet · ' + (files.indexOf(f) + 1),
            'file-sub'
          )
        );
      if (f.path) meta.append(textNode('div', f.path, 'file-sub'));
      const check = f.precheck;
      if (check) {
        const labels = {
          checking: 'Dublettenprüfung läuft …',
          locked: 'Dublettenprüfung nach dem Entsperren',
          clear: 'Keine identische PDF gefunden',
          duplicate: 'Identische PDF bereits vorhanden',
          error: 'Dublettenprüfung nicht möglich'
        };
        const status = textNode(
          'div',
          labels[check.state] || 'Dublettenprüfung offen',
          'source-check ' + check.state
        );
        status.setAttribute('role', 'status');
        meta.append(status);
        for (const match of check.matches || []) {
          const nameRow = textNode('div', '', 'duplicate-name-row');
          if (match.url) {
            const link = textNode('a', match.title, 'duplicate-preview-link');
            link.href = match.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            duplicatePreviews.bind(link, match.id, state.config.base);
            nameRow.append(link);
          } else nameRow.append(textNode('span', match.title, 'file-sub'));
          if (match.id && (!$('series-mode').checked || files[0] === f)) {
            const copyTags = button(
              'Zuordnung übernehmen',
              () => importDuplicateAssignment(f, match),
              'quiet duplicate-tags'
            );
            copyTags.title =
              'Tags, Dokumenttyp, Korrespondent, Speicherpfad und benutzerdefinierte Felder übernehmen';
            copyTags.disabled = !!f.existingBusy || sending;
            nameRow.append(copyTags);
          }
          meta.append(nameRow);
          if (match.id && (!$('series-mode').checked || files[0] === f)) {
            const actions = textNode('div', '', 'row wrap');
            const use = button(
                'Vorhandenen Link nutzen',
                () => useExisting(f, match),
                'quiet'
              ),
              share = button(
                'Öffentlichen Link erzeugen',
                () => openExisting(f, match),
                'quiet'
              );
            use.disabled = share.disabled = !!f.existingBusy || sending;
            actions.append(use, share);
            meta.append(actions);
          }
        }
        if (check.state === 'error') {
          meta.append(
            textNode('div', check.message, 'file-sub'),
            button('Erneut prüfen', () => checkSource(f))
          );
        }
      }
      const remove = button('×', async () => {
        await P.removeSource(f.id);
        const current = files[0] === f;
        files = files.filter((x) => x.id !== f.id);
        if (current && $('series-mode').checked) resetDocumentFields();
        renderFiles();
      });
      remove.disabled = !!f.existingBusy || sending;
      row.append(textNode('span', 'PDF', 'file-mark'), meta, remove);
      if ($('series-mode').checked && files[0] !== f) queued.append(row);
      else $('files').append(row);
    }
    if ($('series-mode').checked && files.length > 1) $('files').append(queued);
    updateSend();
  }
  async function addFile(task) {
    let added = null;
    loadingFiles++;
    updateSend();
    try {
      const file = await task;
      if (file) {
        if (closed) await P.removeSource(file.id);
        else {
          files.push(file);
          added = file;
        }
      }
    } finally {
      loadingFiles--;
      renderFiles();
    }
    if (added) void checkSource(added);
    return added;
  }
  async function picked(list) {
    for (const file of list) {
      try {
        await addFile(P.chooseFile(file));
      } catch (e) {
        notice(`${file.name}: ${e.message}`, true);
      }
    }
  }
  function cancelDownloadWatch() {
    downloadWatchGeneration++;
    downloadWatchActive = false;
    $('watch-annotated').disabled = false;
    $('watch-annotated').textContent = 'Download-Überwachung neu starten';
  }
  async function removeViewerOriginal() {
    const id = viewerOriginalId;
    viewerOriginalId = '';
    if (!id || !files.some((file) => file.id === id)) return;
    await P.removeSource(id);
    files = files.filter((file) => file.id !== id);
    renderFiles();
  }
  function annotatedSelected() {
    cancelDownloadWatch();
    incomingURL = '';
    $('annotation-choice').hidden = true;
    sourceStatus(
      protectedViewer
        ? 'PDF aus dem geschützten Viewer automatisch ausgewählt. Genau diese heruntergeladene Datei wird übertragen.'
        : 'Heruntergeladene PDF automatisch ausgewählt. Die darin gespeicherten Firefox-Anmerkungen werden mit übertragen.'
    );
  }
  function showDownloadChoice(isProtected = false) {
    protectedViewer = isProtected;
    $('download-choice-title').textContent = isProtected
      ? 'Geschützten Webmail-Viewer erkannt'
      : 'Firefox-Anmerkungen übernehmen?';
    $('download-choice-text').textContent = isProtected
      ? 'Der Viewer zeigt die PDF an, gibt bei einem direkten Abruf aber die Webmail-Seite zurück. Paperless Send wartet deshalb automatisch auf genau den nächsten neu gestarteten PDF-Download.'
      : 'Firefox hält Text, Zeichnungen und Markierungen zunächst nur im PDF-Editor. Paperless Send wartet automatisch auf die daraus heruntergeladene Fassung.';
    $('download-choice-step-one').textContent =
      'Die Download-Überwachung läuft automatisch.';
    $('download-choice-step-two').textContent = isProtected
      ? 'Im Webmail-Viewer einmal „Download“ anklicken. Die PDF wird automatisch ausgewählt.'
      : 'Im Firefox-PDF-Viewer einmal „Download“ anklicken. Die annotierte PDF wird automatisch ausgewählt.';
    $('watch-annotated').textContent = 'Download-Überwachung neu starten';
    $('use-original').hidden = isProtected;
    $('annotation-details').open = false;
    $('annotation-choice').hidden = false;
  }
  function askAuth() {
    if (!state.config.base) {
      view('settings');
      $('base').focus();
      notice('Zuerst die Adresse deiner Paperless-Instanz speichern.');
      return;
    }
    $('auth-error').textContent = '';
    $('api-token').value = '';
    $('auth-dialog').showModal();
    $('api-token').focus();
  }
  on('connect', askAuth);
  on('settings-unlock', askAuth);
  on('lock', async () => {
    await P.lock();
    state = await P.state();
    tags = [];
    renderState();
    renderTags();
    notice(
      'Paperless-Token und Nextcloud-App-Passwort aus der Sitzung entfernt.'
    );
  });
  on(
    'auth-form',
    async (e) => {
      e.preventDefault();
      $('auth-submit').disabled = true;
      $('auth-error').textContent = '';
      const token = $('api-token').value;
      $('api-token').value = '';
      try {
        await P.unlock(token);
        $('auth-dialog').close();
        state = await P.state();
        renderState();
        await loadMetadata();
        await saveSeriesOptions();
        notice(
          'Verbunden. API-Token bleibt nur für diese Firefox-Sitzung verfügbar.'
        );
      } catch (err) {
        if ($('auth-dialog').open) $('auth-error').textContent = err.message;
        else notice(err.message, true);
      } finally {
        $('api-token').value = '';
        $('auth-submit').disabled = false;
      }
    },
    'submit'
  );
  document
    .querySelectorAll('.close-dialog')
    .forEach((b) =>
      b.addEventListener('click', () => b.closest('dialog').close())
    );
  $('auth-dialog').addEventListener('close', () => {
    $('api-token').value = '';
  });
  document
    .querySelectorAll('[data-view]')
    .forEach((b) => b.addEventListener('click', () => view(b.dataset.view)));
  on(
    'settings-form',
    async (e) => {
      e.preventDefault();
      state = await P.saveSettings({
        base: $('base').value,
        allowHttp: $('allow-http').checked,
        eraseHistory: $('erase-history').checked,
        theme: $('theme').value
      });
      renderState();
      if (!state.unlocked) {
        tags = [];
        selected.clear();
        renderTags();
      }
      notice('Einstellungen gespeichert.');
    },
    'submit'
  );
  on('theme-toggle', () => {
    const t =
      document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    theme(t);
    $('theme').value = t;
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (state.config.theme === 'auto') theme('auto');
  });
  on('enable-helper', async () => {
    const granted = await browser.permissions.request({
      permissions: ['nativeMessaging']
    });
    state = await P.state();
    renderState();
    notice(
      granted
        ? 'Berechtigung aktiviert. Jetzt die Verbindung zum installierten Dateihelfer testen.'
        : 'Berechtigung nicht erteilt.',
      !granted
    );
  });
  on('test-helper', async () => {
    if (!state.helperAllowed)
      throw new Error('Zuerst den Dateihelfer aktivieren.');
    const r = await P.testHelper();
    $('helper-status').textContent =
      `Dateihelfer verbunden · Version ${r.version}`;
  });
  on('pick', () => {
    annotationPicker = false;
    $('file-input').click();
  });
  on('pick-annotated', () => {
    annotationPicker = true;
    $('file-input').click();
  });
  on(
    'file-input',
    async (e) => {
      const annotated = annotationPicker,
        before = files.length;
      annotationPicker = false;
      await picked([...e.target.files]);
      e.target.value = '';
      if (annotated && files.length > before) {
        await removeViewerOriginal();
        annotatedSelected();
      }
    },
    'change'
  );
  on('pick-helper', async () => {
    if (!state.helperAllowed) {
      view('settings');
      notice(
        'Dateihelfer installieren und aktivieren, um lokale Originale nach dem Import zu löschen.'
      );
      return;
    }
    await addFile(P.helperFile());
  });
  const drop = $('dropzone');
  for (const event of ['dragenter', 'dragover'])
    drop.addEventListener(event, (e) => {
      e.preventDefault();
      drop.classList.add('dragging');
    });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('dragging');
    void picked([...e.dataTransfer.files]);
  });
  on(
    'url-form',
    async (e) => {
      e.preventDefault();
      await addFile(P.sourceURL($('source-url').value));
      $('source-url').value = '';
    },
    'submit'
  );
  async function selectDownloaded(d, annotations = false) {
    const before = files.length;
    try {
      await addFile(P.chooseDownload(d.id));
    } catch (readError) {
      if (!state.helperAllowed)
        throw new Error(
          readError.message +
            ' Alternativ den Dateihelfer aktivieren oder die gespeicherte PDF auswählen.'
        );
      await addFile(P.helperFile(d.path));
    }
    if (files.length <= before)
      throw new Error('Der PDF-Download konnte nicht übernommen werden.');
    if (annotations) {
      await removeViewerOriginal();
      annotatedSelected();
    }
  }
  async function showDownloads(annotations = false) {
    const list = await P.downloads();
    $('downloads-list').replaceChildren();
    $('downloads-hint').textContent = annotations
      ? 'Die zuletzt über den PDF-Viewer gespeicherte Datei steht normalerweise oben. Sie enthält die exportierten Anmerkungen.'
      : 'PDFs aus den letzten 100 abgeschlossenen Downloads.';
    if (!list.length)
      $('downloads-list').append(
        textNode('p', 'Keine passenden Downloads gefunden.', 'empty')
      );
    for (const d of list) {
      const row = textNode('div', '', 'download-row');
      const info = textNode('span', d.name);
      info.title = d.path;
      row.append(
        info,
        button(
          'Auswählen',
          async () => {
            try {
              await selectDownloaded(d, annotations);
            } finally {
              $('downloads-dialog').close();
            }
          },
          'secondary'
        )
      );
      $('downloads-list').append(row);
    }
    $('downloads-dialog').showModal();
  }
  on('pick-download', () => showDownloads(false));
  on('pick-annotated-download', () => showDownloads(true));
  async function watchAnnotatedDownload() {
    if (downloadWatchActive) return;
    const marker = ++downloadWatchGeneration;
    const control = $('watch-annotated'),
      label = control.textContent;
    downloadWatchActive = true;
    control.disabled = true;
    control.textContent = 'Warte auf PDF-Download …';
    sourceStatus(
      protectedViewer
        ? 'PDF erkannt. Jetzt im Webmail-Viewer einmal „Download“ anklicken; die Auswahl erfolgt automatisch.'
        : 'Warte auf PDF-Download · Anmerkungen werden automatisch übernommen.'
    );
    try {
      const item = await P.waitForPDFDownload(Date.now(), incomingName);
      if (closed || marker !== downloadWatchGeneration) return;
      await selectDownloaded(item, true);
      window.focus?.();
      notice(
        protectedViewer
          ? 'PDF aus dem Webmail-Viewer automatisch übernommen. Zuordnung prüfen und Auftrag starten.'
          : 'Annotierte PDF automatisch übernommen. Zuordnung prüfen und Auftrag starten.'
      );
    } catch (error) {
      if (!closed && marker === downloadWatchGeneration) {
        sourceStatus(error.message, true);
        $('annotation-details').open = true;
      }
    } finally {
      if (marker === downloadWatchGeneration) {
        downloadWatchActive = false;
        control.disabled = false;
        control.textContent = label;
      }
    }
  }
  on('watch-annotated', watchAnnotatedDownload);
  on(
    'refresh-tags',
    async () => {
      if (!state.unlocked) return askAuth();
      await loadMetadata(true);
    },
    'click'
  );
  on('tag-search', renderTags, 'input');
  on(
    'tag-search',
    (e) =>
      tagCursor.key(
        e,
        tagMatches,
        (tag) => {
          selected.add(tag.id);
          $('tag-search').value = '';
          renderTags();
          updateSend();
        },
        renderTags
      ),
    'keydown'
  );
  on(
    'profile',
    () => {
      const id = $('profile').value;
      applyProfile(id);
      if (!metadataLoaded) pendingProfile = id;
      updateSend();
    },
    'change'
  );
  on('save-profile', () => {
    profileEditId = null;
    $('profile-options').textContent = profileOptionsText({
      share: $('share-enabled').checked
        ? {
            days: Number($('share-days').value),
            archive: $('share-archive').checked
          }
        : null,
      complete_tagging: $('complete-tagging').checked
    });
    $('profile-dialog').showModal();
    $('profile-name').focus();
  });
  on('update-profile', () => {
    const p = state.config.profiles.find((x) => x.id === $('profile').value);
    if (!p) return;
    profileEditId = p.id;
    $('profile-name').value = p.name;
    $('profile-options').textContent =
      'Dieses Profil aktualisieren: ' + profileOptionsText(rawMetadata());
    $('profile-dialog').showModal();
  });
  on(
    'profile-form',
    async (e) => {
      e.preventDefault();
      const p = await P.saveProfile(
        $('profile-name').value,
        rawMetadata(),
        profileEditId
      );
      state = await P.state();
      renderState();
      $('profile').value = p.id;
      $('profile-dialog').close();
      notice('Profil gespeichert.');
    },
    'submit'
  );
  on('new-tag', () => {
    if (!state.unlocked) return askAuth();
    $('tag-dialog').showModal();
    $('tag-name').focus();
  });
  on(
    'tag-form',
    async (e) => {
      e.preventDefault();
      const b = e.target.querySelector('button.primary');
      b.disabled = true;
      try {
        const tag = await P.createTag(
          $('tag-name').value,
          $('tag-color').value
        );
        selected.add(tag.id);
        $('tag-dialog').close();
        $('tag-name').value = '';
        await loadMetadata(true);
      } finally {
        b.disabled = false;
      }
    },
    'submit'
  );
  on('send', async () => {
    if (
      sending ||
      !files.length ||
      loadingFiles ||
      files.some((f) => f.existingBusy)
    )
      return;
    const duplicateConsent = new Map(
      files.map((file) => [
        file.id,
        file.precheck?.state === 'duplicate'
          ? (file.precheck.matches || [])
              .map((m) =>
                m.id
                  ? 'document:' + m.id
                  : m.sessionJobId
                    ? 'job:' + m.sessionJobId
                    : ''
              )
              .filter(Boolean)
          : []
      ])
    );
    sending = true;
    updateSend();
    try {
      const previousBase = state.config.base;
      state = await P.state();
      if (state.config.base !== previousBase) {
        selected.clear();
        tags = [];
        renderState();
        renderTags();
        if (state.unlocked) await loadMetadata();
        throw new Error(
          'Die Zieladresse wurde geändert. Bitte Zuordnung prüfen.'
        );
      }
      if (!state.unlocked) return askAuth();
      const series = $('series-mode').checked,
        meta = rawMetadata(),
        deleting = $('delete-local').checked,
        batchId = await P.beginBatch(),
        chosen = series ? files.slice(0, 1) : [...files];
      let accepted = 0;
      try {
        for (const file of chosen) {
          await P.start(
            file.id,
            meta,
            deleting,
            previousBase,
            batchId,
            duplicateConsent.get(file.id) || []
          );
          files = files.filter((f) => f !== file);
          accepted++;
        }
      } finally {
        await P.sealBatch(batchId);
        if (series && accepted) {
          seriesStarted += accepted;
          assignmentTouched = true;
          resetDocumentFields();
        }
      }
      await browser.storage.session.set({ recentTags: [...selected] });
      recent = [...selected];
      if (series) {
        view('upload');
        notice(
          files.length
            ? 'Auftrag gestartet. Nächste PDF bereit.'
            : 'Auftrag gestartet. Weitere PDFs hinzufügen; Zuordnung bleibt erhalten.'
        );
        $('title').focus();
      } else if (compact) {
        window.close();
        return;
      } else {
        view('history');
        notice(
          'Übertragung gestartet. Firefox bis zum Abschluss geöffnet lassen.'
        );
      }
    } finally {
      sending = false;
      renderFiles();
    }
  });
  on('quick-send', () => $('send').click());
  async function renderJobs() {
    const list = P.jobs();
    $('job-count').textContent = list.length;
    const signature = JSON.stringify(list);
    if (signature === jobSignature) return;
    jobSignature = signature;
    $('jobs').replaceChildren();
    if (!list.length)
      $('jobs').append(
        textNode(
          'div',
          'Noch keine Übertragungen in dieser Sitzung.',
          'card empty'
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
    for (const j of [...list].reverse()) {
      const card = textNode('article', '', 'card job ' + j.state),
        top = textNode('div', '', 'job-top');
      top.append(
        textNode('h3', j.name),
        textNode(
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
                    : labels[j.state] || j.state,
          'badge'
        )
      );
      card.append(top, textNode('p', j.message));
      if (j.taskId)
        card.append(textNode('div', 'Task-ID: ' + j.taskId, 'task-id'));
      if (j.linkCopied)
        card.append(
          textNode(
            'p',
            j.shareURL
              ? 'Öffentlicher Link automatisch kopiert · mit Strg+V einfügen.'
              : 'Paperless-Link automatisch kopiert · mit Strg+V einfügen.',
            'muted small'
          )
        );
      if (j.linkCopyError)
        card.append(textNode('p', j.linkCopyError, 'muted small'));
      const actions = textNode('div', '', 'job-actions');
      if (j.documentURL) {
        const link = textNode('a', 'Dokument in Paperless öffnen');
        link.href = j.documentURL;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        actions.append(
          link,
          button(
            'Link kopieren',
            async () => {
              await P.copyJobLink(j.id);
              notice(
                'Paperless-Link kopiert – jetzt in der Buchhaltung mit Strg+V einfügen.'
              );
              await renderJobs();
            },
            'secondary'
          )
        );
      }
      if (j.shareURL) {
        const link = textNode('a', 'Öffentliches Dokument öffnen');
        link.href = j.shareURL;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        actions.append(
          link,
          button(
            'Öffentlichen Link kopieren',
            async () => {
              await P.copyShareLink(j.id);
              notice('Öffentlicher Link kopiert.');
            },
            'secondary'
          )
        );
      }
      if (j.inboxWarning) {
        card.append(textNode('p', j.inboxWarning, 'error'));
        if (!j.busy)
          actions.append(
            button(
              'Posteingangs-Tags erneut entfernen',
              () => P.retryInbox(j.id),
              'secondary'
            )
          );
      }
      if (j.shareWarning) card.append(textNode('p', j.shareWarning, 'error'));
      if (j.taskId && !j.busy && ['pending', 'uncertain'].includes(j.state))
        actions.append(
          button('Status erneut prüfen', () => P.retryStatus(j.id), 'secondary')
        );
      if (j.state === 'duplicate') {
        const matches = textNode('ul', '', 'duplicate-matches');
        for (const match of j.duplicates || []) {
          const item = textNode('li', '');
          if (match.url) {
            const a = textNode('a', match.title);
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
          textNode(
            'p',
            'Ja sendet die unveränderte PDF. Paperless muss identische Dateien zulassen; eine Serversperre kann das Plugin nicht übersteuern.',
            'muted small'
          )
        );
        actions.append(
          button(
            'Nein, nicht übernehmen',
            () => P.decideDuplicate(j.id, false),
            'secondary'
          ),
          button(
            'Ja, trotzdem übernehmen',
            () => P.decideDuplicate(j.id, true),
            'primary'
          )
        );
      }
      if (j.state === 'check_failed' && !j.busy)
        actions.append(
          button('Prüfung wiederholen', () => P.retryCheck(j.id), 'secondary')
        );
      for (const item of j.deckLinks || []) {
        const a = textNode('a', 'Deck: ' + item.name);
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
          button('Als gelesen markieren', () => P.acknowledgeJob(j.id))
        );
      if (!j.busy)
        actions.append(button('Eintrag entfernen', () => P.discardJob(j.id)));
      card.append(actions);
      $('jobs').append(card);
    }
  }
  if (compact) {
    document.querySelector('#view-upload h1').textContent =
      'An Paperless senden';
    $('send').textContent = 'Auftrag starten';
    document.querySelector('.submit-area .tiny').textContent =
      'Danach kannst du dieses Fenster schließen. Aufträge findest du am Plugin-Symbol. Firefox geöffnet lassen.';
    $('quick-send').hidden = false;
    const settings = button('Einstellungen', () => P.openPage('settings'));
    document.querySelector('.topbar .row').append(settings);
  }
  $('cloud-base').value = state.config.nextcloud?.base || '';
  $('cloud-user').value = state.config.nextcloud?.username || '';
  if (state.config.nextcloud) {
    const t = state.config.nextcloud;
    $('deck-board').replaceChildren(new Option(t.boardName, t.boardId));
    $('deck-stack').replaceChildren(new Option(t.stackName, t.stackId));
  }
  window.addEventListener('focus', async () => {
    state = await P.state();
    renderDeckStatus();
    syncSourceChecks();
  });
  renderKeyboardSettings();
  renderState();
  renderFiles();
  renderTags();
  view(
    ['settings', 'history'].includes(location.hash.slice(1))
      ? location.hash.slice(1)
      : 'upload'
  );
  await renderJobs();
  const timer = setInterval(() => {
    void renderJobs();
    if ($('series-mode').checked) {
      const jobs = P.jobs();
      const open = jobs.filter(
        (j) =>
          [
            'duplicate',
            'check_failed',
            'failed',
            'pending',
            'uncertain'
          ].includes(j.state) ||
          j.shareWarning ||
          j.inboxWarning ||
          j.deckWarning
      ).length;
      $('series-history').textContent = open
        ? `Aufträge · ${open} offen`
        : 'Aufträge';
    }
  }, 1000);
  window.addEventListener('unload', () => {
    closed = true;
    clearInterval(timer);
    for (const f of files) void P.removeSource(f.id);
  });
  function sourceStatus(message, bad = false) {
    $('source-status').textContent = message;
    $('source-status').hidden = !message;
    $('source-status').classList.toggle('error', bad);
    $('source-status').classList.toggle('muted', !bad);
  }
  async function adoptIncoming(monitorAnnotations = false) {
    if (!incomingURL || loadingFiles > 0) return;
    $('retry-source').hidden = true;
    sourceStatus('PDF wird übernommen …');
    $('source-url').value = incomingURL;
    try {
      const task =
        incomingURL.startsWith('file:') && state.helperAllowed
          ? P.helperFile(incomingURL)
          : P.sourceURL(incomingURL);
      const added = await addFile(task);
      if (closed) return;
      if (added && monitorAnnotations && !incomingURL) {
        await P.removeSource(added.id);
        files = files.filter((file) => file.id !== added.id);
        renderFiles();
        return;
      }
      if (added && monitorAnnotations) viewerOriginalId = added.id;
      if (files.length)
        sourceStatus(
          monitorAnnotations
            ? 'PDF bereits ausgewählt · Bei Anmerkungen im Viewer „Download“ anklicken.'
            : 'PDF übernommen. Zuordnung prüfen und Auftrag starten.'
        );
      else {
        sourceStatus('Keine Datei übernommen. Bitte erneut auswählen.', true);
        $('retry-source').hidden = false;
      }
    } catch (e) {
      if (closed) return;
      if (e.code === 'PDF_SOURCE_PROTECTED') {
        $('retry-source').hidden = true;
        showDownloadChoice(true);
        sourceStatus(
          'Geschützter PDF-Viewer erkannt. Die Download-Überwachung wurde automatisch gestartet.'
        );
        void watchAnnotatedDownload();
        return;
      }
      sourceStatus(
        e.message + ' Die PDF wurde noch nicht an Paperless gesendet.',
        true
      );
      $('retry-source').hidden = false;
    }
  }
  on('retry-source', adoptIncoming);
  on('use-original', async () => {
    cancelDownloadWatch();
    $('annotation-choice').hidden = true;
    if (viewerOriginalId) {
      sourceStatus('Die bereits ausgewählte Original-PDF wird übertragen.');
      return;
    }
    sourceStatus('Unbearbeitetes Original wird übernommen …');
    await adoptIncoming();
  });
  async function loadIncoming() {
    if (!intent) return;
    sourceStatus('PDF wird übernommen …');
    try {
      const data = await P.intent(intent);
      if (closed) return;
      if (!data?.url)
        throw new Error(
          'Die Dateiübergabe fehlt oder ist abgelaufen. Bitte die PDF erneut per Rechtsklick übernehmen.'
        );
      history.replaceState(
        null,
        '',
        compact ? 'app.html?compact=1#upload' : 'app.html#upload'
      );
      incomingURL = data.url;
      incomingName = String(data.name || '');
      if (
        data.profileId &&
        state.config.profiles.some((p) => p.id === data.profileId)
      ) {
        applyProfile(data.profileId);
        if (!metadataLoaded) pendingProfile = data.profileId;
      }
      if (data.viewerSource) {
        showDownloadChoice(false);
        sourceStatus(
          'PDF im Firefox-Viewer erkannt. Original wird ausgewählt; die Download-Überwachung läuft parallel.'
        );
        void watchAnnotatedDownload();
        await adoptIncoming(true);
      } else await adoptIncoming();
    } catch (e) {
      sourceStatus(e.message, true);
    }
  }
  // A slow or failed catalog request must never block adoption of the clicked PDF.
  await Promise.all([
    loadIncoming(),
    state.unlocked
      ? loadMetadata().catch((e) => notice(e.message, true))
      : Promise.resolve()
  ]);
  incomingLoaded = true;
  await restoreSeriesAssignment();
})().catch(() => {
  const error = document.getElementById('notice');
  if (error) {
    error.textContent =
      'Versanddialog konnte nicht vollständig geladen werden. Bitte schließen und über das Plugin erneut öffnen.';
    error.hidden = false;
    error.classList.add('bad');
  }
});
