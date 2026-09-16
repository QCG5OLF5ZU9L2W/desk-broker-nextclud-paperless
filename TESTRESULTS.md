# Version 2.4.12 – Übernahme der letzten Serienzuordnung

- **145 Node-Tests bestanden**, 0 fehlgeschlagen. Neue Fälle: vollständige und
  bearbeitbare Übernahme, Werte `false`/`0`/Währung/Dokumentverweise, letzter
  angenommener Auftrag, fehlgeschlagener Start, unabhängige Kopien, keine dauerhafte
  Speicherung der Serienvorlage, Sperren/Neuanmeldung/Instanzwechsel, Vorrang
  expliziter Profile und manueller Eingaben, entfernte Felder, Ausschalten.
  Protokoll: `validation/node-tests-2.4.12.txt`.
- **Firefox 153: Serienmodus bestanden.** Tatsächliches Sendeformular mit zwei PDFs,
  anschließender Änderung der Zuordnung, neuem Sendefenster und erneuter Übernahme
  der letzten Werte. Kurzdatum und Kalenderwert stimmen überein; Titel leer,
  Geldbetrag und Nein-Wert erhalten, weitere Tags auswählbar, Ausschalten wirksam,
  keine JavaScript-Konsolenfehler. `tests/series-browser.cjs` und
  `validation/firefox-series-2.4.12.txt`. Screenshot visuell geprüft.
- **Mozilla addons-linter 10.11.0: 0 Fehler, 0 Hinweise, 1 Warnung.** Unveränderte
  Warnung zur Android-Mindestversion für den Dateneinwilligungs-Schlüssel.
  Keine Bibliotheken oder unbekannten minifizierten Dateien erkannt.
  Bericht: `validation/addons-linter-2.4.12.json`.
- Gegenüber 2.4.11 sind im XPI nur `app.js`, `app.html`, `background.js` und die
  Manifestversion geändert. Berechtigungen, Add-on-ID, CSP, native mehrseitige
  PDF-Vorschau und Dateihelfer bleiben unverändert. Keine neuen Fremdbibliotheken.
- ZIP-Integrität und bytegleicher Offline-Neubau aus dem ausgelieferten Quellpaket
  geprüft; das Quellpaket enthält ausschließlich die XPI der aktuellen Version.

Die Browserprüfung verwendet simulierte Paperless-/Dateischnittstellen. Kein
Live-Upload an die Nutzerinstanz, kein Android-Test und keine manuelle Mozilla-
Freigabe. Der neue Serienablauf wurde als tatsächliche HTML-Oberfläche im Firefox-
Testbrowser geprüft, nicht als installierter Toolbar-Container. Die unveränderte
Vorschau wurde in 2.4.11 auch unter `moz-extension://` getestet; diese älteren
Ergebnisse folgen unten und wurden für die Serienänderung nicht erneut behauptet.

Für den Browsertest: Playwright 1.62.1 mit Firefox, Node.js und
`CODEX_PRIMARY_RUNTIME_NODE_MODULES` auf das Verzeichnis der Testabhängigkeiten.
Der optionale Schalter `PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX=1` betrifft nur den
Wegwerf-Testbrowser in eingeschränkten Containern und ist kein Add-on-Verhalten.
Alle Testdateien bleiben außerhalb der XPI. Zum Release-Build reicht Python.

## Frühere Version

# Version 2.4.11 – native mehrseitige Vorschau

Prüfstand: Linux, Python 3.12.14, Node.js 24.19.0, Firefox 153.0.

- 138 Node-Tests bestanden (`node --test tests/*.test.cjs`). Neu: authentifizierte, validierte Seitenzahl; keine Ausgabe nach Instanz- oder Sitzungswechsel. Die kleinen DOM-Testmodelle unterstützen nun auch das Entfernen der eingebetteten Anzeige.
- `tests/pdf-pages-browser.cjs`: Tatsächliche Seiten in Firefox’ eigener PDF-Anzeige gerendert, Popup und Sendeformular, Text/Grafik, Hoch-/Querformat, Mausrad und Pfeiltasten, Seitengrenzen, Esc/erneutes Hover, Wiederverwendung ohne erneuten PDF-Abruf, mehrere Dokumente, isolierter Frame und Entfernen beim Sperren.
- `tests/native-extension-browser.py`: Temporäre Erweiterung mit unverändertem Preview-Code und Manifest plus ausschließlich temporären Testdateien installiert. Unter `moz-extension://` Seiten 1–3 tatsächlich dargestellt; echte Maus-, Rad- und Tastaturereignisse, kein Zugriff der Erweiterungsseite auf den Viewer-DOM, ein PDF-Abruf, Entfernen des Frames und Widerruf der Blob-URL beim Sperren geprüft. Bei deaktiviertem Viewer kein PDF-Abruf; bei „Datei speichern“ bleibt das Thumbnail sichtbar und es wird kein Download angelegt.
- Bestehende Popup-Hover- und Doubletten-/Zuordnungs-Browsertests bestanden.
- Mozilla addons-linter 10.11.0 mit Standardsatz aller Regeln: **0 Fehler, 0 Hinweise, 1 Warnung**. Keine erkannten JS-Bibliotheken und keine unbekannten minifizierten Dateien. Die einzige Warnung betrifft wie schon 2.4.7 die Android-Mindestversion für den Dateneinwilligungs-Schlüssel; die fünf zusätzlichen Renderer-Codewarnungen aus 2.4.10 entfallen vollständig. Bericht: `validation/addons-linter-2.4.11.json`.
- Quellcode und XPI enthalten keine PDF.js-Dateien, WASM-Binärdateien oder sonstigen Renderer-Bibliotheken. Der CSP-WASM-Zusatz ist entfernt. Die übrigen Oberflächen- und Workflow-Dateien sind mit 2.4.10 bytegleich, abgesehen von den ausdrücklich dokumentierten Änderungen.
- ZIP-Integrität, passende Manifestversion und bytegleicher Offline-Neubau aus dem ausgelieferten Paket geprüft.

Browserprüfungen verwenden lokale Testdaten, keine Nutzerdateien oder Serverzugänge.
Der installierte Test prüft eine Erweiterungsseite; die echten UI-Seiten werden
separat in Firefox geprüft, nicht im tatsächlichen Toolbar-Popup-Container.
Firefox 140 und Android wurden nicht praktisch getestet. Keine manuelle
Mozilla-Freigabe und kein vollständiges Sicherheitsaudit behauptet.

Optionale Test-Abhängigkeiten: Playwright 1.62.1 mit Firefox und pdf-lib 1.17.1;
für die Python-Integration zusätzlich `FIREFOX_BINARY` auf den Firefox-Pfad setzen.
`tests/make-preview-fixture.cjs` erzeugt nur synthetische Testdaten und wird nicht
mit dem Add-on ausgeliefert. Die Tests richten ihre eigenen Wegwerfprofile auf
„In Firefox öffnen“ ein, da Automationsbrowser PDF-Downloads voreinstellen.
In eingeschränkten Testcontainern kann `PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX=1`
gesetzt werden; es betrifft ausschließlich den Testbrowser und weder das Add-on
noch die Einstellungen des Nutzers. Der Build selbst benötigt keine Testpakete.

## Historische Prüfergebnisse

# Version 2.4.10

137 vorhandene automatisierte Tests bestanden. Mehrseitige PDF-Hover-Vorschau im echten Firefox-Testbrowser mit lokalen API-Testdaten erneut geprüft: Popup und Sendeformular, tatsächliches Rendern mehrerer Seiten, Mausrad/Pfeiltasten, Seitengrenzen, Esc, Cache und Sitzungssperre.

Alle 200 ausgelieferten PDF.js-Dateien sind bytegleich mit dem offiziellen npm-Archiv 5.6.205. Das Originalarchiv wurde gegen dessen npm-SHA-512-Integrität geprüft. `verify_vendor.py` prüft diese Herkunft und die Dateiliste bei jedem Build. Eigene Dateien werden beim Packen unverändert übernommen.

Tabtitel und Fußzeile mit dem tatsächlichen App-Skript geprüft: beide zeigen 2.4.10. Ein isolierter Offline-Neubau ausschließlich aus den dokumentierten Eingaben erzeugt eine bytegleiche XPI. ZIP-Integrität und Manifestversion geprüft.

# Version 2.4.9

137 automatisierte Tests bestanden. Zusätzliche API-Prüfungen: authentifizierter Abruf der Original-PDF, Schutz vor falscher Instanz und Sitzungswechsel, Zurückweisung von Nicht-PDF-Antworten und übergroßen Dateien.

Reale Firefox-Tests mit den tatsächlichen HTML-/CSS-/JS-Dateien:
- Neue `tests/pdf-pages-browser.cjs`: PDF.js rendert eine dreiseitige Test-PDF mit Text, eingebetteter Grafik und einer Seite im Querformat unter der CSP des Add-ons. Popup und Doubletten im Sendeformular geprüft. Verschiedene Canvas-Inhalte bei Seitenwechsel, Mausrad ohne Seitenscrollen, Pfeiltasten, letzte Seite, Esc, Cache ohne erneuten Download, unterschiedliche PDFs und Leeren beim Sperren.
- Bisherige Popup-Hover- und Doubletten-/Zuordnungs-Browsertests bestanden.

Die PDF- und API-Antworten stammen aus lokalen Testdaten; kein Zugriff auf die Nutzerinstanz. Der neue Test benötigt zusätzlich pdf-lib zum Erstellen der Test-PDF und startet einen lokalen Testserver für JavaScript-Module. Produktiv werden alle Renderer-Ressourcen direkt aus dem Add-on geladen. Archivintegrität und Manifestversion geprüft.

# Version 2.4.8

35 bestehende Tests des Sendeformulars bestanden. Die Testumgebung liefert die Versionsnummer wie Firefox über runtime.getManifest(). Der hart codierte Stand 2.3.4 wurde aus der Oberfläche entfernt. XPI-Manifest und Archivintegrität geprüft.

# Version 2.4.7

135 automatisierte Tests bestanden. Neue Prüfungen: dokumentbezogener Thumbnail-Abruf, keine Ausgabe nach Sitzungswechsel, unverändernder Lesezugriff auf bestehende Zuordnungen, Zusammenführen von Tags ohne Duplikate und ohne Entfernen manueller Tags, Übernahme von Dokumenttyp/Korrespondent/Speicherpfad, benutzerdefinierte Geldbeträge ohne erneute Centumrechnung, Boolean- und Dokumentlink-Werte sowie anschließende Bearbeitbarkeit.

Zusätzlich mit Firefox 153 / Playwright und lokalen API-Testdaten geprüft:
- Unterschiedliche Vorschaubilder beim Wechsel zwischen Doublettennamen, Cache ohne erneuten Abruf, Größenänderung, Esc, Namenslinks und Sitzungswechsel.
- Zuordnung aus einer Doublette übernehmen; danach zusätzlichen Kontext-Tag wählen, Dokumenttyp ändern und Betrag bearbeiten.
- Bestehende Hover-Vergrößerung im Auftrags-Popup weiterhin funktionsfähig (separater Popup-Browsertest).

Optionale Browsertests: `node tests/duplicate-browser.cjs` und `node tests/popup-browser.cjs`. Kein Zugriff auf die Nutzerinstanz; Browsertests verwenden die tatsächlichen HTML-/CSS-/JS-Dateien mit simulierten API-Antworten. Archivintegrität geprüft.

# Version 2.4.6

- 8 Popup-Tests im bestehenden DOM-Modell bestanden.
- Zusätzlicher Test mit echtem Firefox 153 / Playwright und echten Mausereignissen bestanden: Hover, Bildgröße, Popup-Größenänderung, Kartenaktualisierung unter dem Mauszeiger, Esc, Verlassen und Wiederbetreten, Tastaturfokus, Scrollposition und Wiederverwendung des geladenen Bildes.
- Regression mit dem veröffentlichten XPI 2.4.5 reproduziert: Der Test scheitert dort nach der Größenänderung, weil die Vergrößerung ausgeblendet wird. Version 2.4.6 besteht denselben Test.
- Browserprüfung nutzt lokale API-Testdaten und eine Testgrafik. Es wurde nicht auf die Nutzerinstanz zugegriffen; kein Test des echten Firefox-Toolbar-Containers, sondern der Popup-Seite im Firefox-Testbrowser.
- Optionaler Browsertest: `node tests/popup-browser.cjs` (Playwright und dessen Firefox erforderlich). Die Umgebung kann für isolierte Container `PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX=1` setzen; das ändert nur den Testbrowser, nicht die Erweiterung.
- Archivintegrität geprüft.

# Version 2.4.5

Alle 8 Popup-Tests bestanden. Zusätzliche Interaktionsprüfung: Vergrößerung bei Hover und Fokus, Schließen bei Verlassen/Fokusverlust, Esc, Scrollen und Neuzeichnen; Wiederverwendung des geladenen Bildes ohne weiteren Abruf. DOM-Simulation mit dem tatsächlichen Popup-Skript, kein Live-Test in Firefox. Archivintegrität geprüft.

# Version 2.4.4

Alle 41 Tests für Sendeformular und Popup bestanden. Zusätzlich geprüft: direkte Laufzeitwahl im Formular, sichtbarer Auswahlstatus, Synchronisierung der Menüleiste, Ausschalten und Übernahme der Laufzeit in den Versand. Die angepasste Interaktionsprüfung deckt die drei Laufzeiten (7, 30, unbefristet), direkte Ausführung, Sperren weiterer Klicks und anschließende Kopieraktion ab. JavaScript wird im bestehenden DOM-Testmodell ausgeführt; kein Live-Test mit Firefox/Paperless. Archivintegrität geprüft.

# Version 2.4.3

Reine Größen- und Layoutanpassung der Vorschau (120 × 160 px), Versionsnummer aktualisiert. JavaScript-Syntax und Archivintegrität geprüft. Bestehender Funktionsstand: 130 Tests in Version 2.4.2 bestanden. Keine neuen Tests für die Größenänderung; kein Live-Test in Firefox.

# Version 2.4.2

130 automatisierte Tests bestanden. Zusätzliche Regressionen: angezeigte Doubletten werden einmalig bestätigt und hochgeladen, unbekannte Treffer halten den Upload an; beide Sendeknöpfe zeigen die ausdrückliche Übernahme an; Thumbnail-Accept-Header und sichtbarer Fehler bei gescheitertem Abruf. Tests laufen in Node VM/DOM-Simulation. Kein Live-Test in Firefox oder an der Nutzerinstanz.

# Version 2.4.1

126 automatisierte Tests bestanden (Node VM/DOM-Simulation). Zusätzliche Prüfungen: passives automatisches Vorschaubild, authentifizierter reiner Lesezugriff, keine Ausgabe nach Sperren der Sitzung, Ablehnung von HTML statt Bild. Kein Live-Test in Firefox mit einer Paperless-Instanz durchgeführt.

# Prüfung der Version 2.4.0

123 automatisierte Tests bestanden (`node --test tests/*.test.cjs`).

Neue Prüfungen: Serienmodus versendet nur die erste PDF, hält das Fenster offen, erhält Dokumentdatum und Zuordnung und leert Beträge; nächster Auftrag mit neuen Werten; Fehler vor Auftragsannahme erhält Datei und Eingaben. Einheitliche Pfeiltasten-/Enter-Auswahl für Tags, Korrespondenten und Customfelder. Vorschläge werden nur auf Klick übernommen und erhalten bestehende Tags. Profilaktualisierung behält ID und erzeugt keine zweite Kopie. Zuordnungshistorie wird nur nach bestätigtem Upload gelernt und nach Instanz getrennt. Vorhandene Dubletten werden vor Nutzung verifiziert; öffentliche Freigabe ohne Upload/Metadatenänderung und ohne erneuten POST bei unklarem Ergebnis. Nachträgliche Linkerzeugung im Popup für abgeschlossene Aufträge und Erhalt des archivierten Ergebnisses bei Freigabefehlern.

Zusätzlich Manifest-Abgleich (nur Versionsnummer), eindeutige statische HTML-IDs und ZIP-Konsistenz. Die Tests verwenden simulierte DOM-, Firefox- und Paperless-Schnittstellen. Kein visueller Live-Test in Firefox und kein Live-Test gegen die Benutzerinstanz.

# Prüfung der Version 2.3.13

112 automatisierte Tests bestanden. Neu: Kürzelvalidierung und Doppelbelegung, Persistenz über allgemeine Einstellungsänderungen, normale Texteingaben und AltGr, Strg+S nur im Versandbereich ohne Dialog, Wiederholungs- und Disabled-Schutz, Tab-Bereiche vorwärts/rückwärts und von einer per Maus fokussierten Checkbox aus sowie Kürzelaufzeichnung und Deaktivierung. DOM/Firefox-Schnittstellen simuliert; kein Live-Test in Firefox.

Manifest-Abgleich: neue interne keyboard.js und Versionsnummer; keine geänderten Berechtigungen oder Add-on-ID.

# Prüfung der Version 2.3.12

Gezielter Vergleich mit 2.3.11: ausschließlich HTML/CSS des Datumsfelds und Versionsnummer geändert; sämtliche JavaScript-Dateien unverändert. Keine erneuten Funktionstests für diese Layoutänderung. XPI und Paket auf ZIP-Konsistenz geprüft. Kein visueller Live-Test in Firefox.

# Prüfung der Version 2.3.11

107 automatisierte Tests bestanden. Neue Prüfungen: Dubletten-Vorabprüfung ohne Upload oder Verbrauch der Quelle; erneute Serverprüfung beim Senden trotz zuvor negativem Ergebnis; gesperrte Sitzung und API-Fehler; Verwerfen verspäteter Ergebnisse nach Sperren; nicht blockierter Versanddialog während laufender Prüfung; verspätete Ergebnisse stellen bereits gesendete Dateien nicht wieder her.

Firefox- und Paperless-Schnittstellen werden simuliert. Kein Live-Test gegen die Benutzerinstanz. Berechtigungen und Add-on-ID unverändert.

# Prüfung der Version 2.3.10

101 automatisierte Tests bestanden. Die Kalenderprüfung bestätigt den direkten showPicker-Aufruf per Klick, das Fehlen eines zusätzlichen Aufklappbereichs und die Synchronisierung einschließlich optionaler Uhrzeit. Kein Live-Test der nativen Firefox-Kalenderoberfläche.

# Prüfung der Version 2.3.9

101 automatisierte Tests bestanden (`node --test tests/*.test.cjs`). Neue Prüfungen: Enter übernimmt den sichtbar markierten ersten Titelvorschlag, Pfeiltasten/Escape/Maus, Synchronisierung von Kalender und Kurznotation mit optionaler Uhrzeit sowie Menüleisten-Freigabe mit Checkbox/Laufzeit/Profilen. Kein Live-Test der nativen Kalenderoberfläche in Firefox; Schnittstellen und DOM werden simuliert.

# Prüfung der Version 2.3.8

`node --test tests/*.test.cjs`: 97 Tests bestanden, 0 fehlgeschlagen.

Neue Prüfungen: persistierte Profiloptionen und ungültige Freigabevorgaben; Wechsel zu alten Profilen deaktiviert die neuen Optionen; eingeklappte Anmerkungsalternativen bei laufender Überwachung und automatisches Öffnen im Fehlerfall; begrenzter, deduplizierter und nach Instanz getrennter Titelverlauf einschließlich Löschung; Laden und Speichern von Titelvorschlägen; Kurzdatum mit Kalenderprüfung, Schaltjahren und optionaler Uhrzeit; Cent-Eingabe mit Währung und negativen Beträgen, idempotente Formatierung und unveränderte normale Zahlenfelder.

Die Prüfungen verwenden simulierte Firefox-/Paperless-Schnittstellen. Native Vorschlagsdarstellung und Layout wurden nicht in echtem Firefox geprüft; ein Live-Test mit der Benutzerinstanz steht aus. Berechtigungen und Add-on-ID sind unverändert. Das erzeugte XPI bleibt unsigniert.

## Frühere Testergebnisse

# Prüfung der Version 2.3.5

`node --test tests/*.test.cjs`: 89 Tests bestanden, 0 fehlgeschlagen.

Zusätzlich zu den bisherigen Prüfungen: Freigabe-API mit allen Ablaufzeiten und beiden Dateiversionen, Unterpfad-URLs, öffentliche Zwischenablage, Deck-Link, fehlgeschlagene/unklare Freigabe ohne Wiederholungsupload, Suchauswahl und entfernbare Customfelder, ausgewählte Tags außerhalb der Auswahlliste, Popup-Freigabelink, optionale Entfernung mehrerer Posteingangs-Tags unter Erhalt anderer Tags, Fehler und Wiederholung ohne Upload sowie Erkennung unmittelbar erneut gesetzter Posteingangs-Tags.

Manifest-Abgleich: ausschließlich Versionsnummer geändert; Berechtigungen und Add-on-ID unverändert. Native Helferdateien unverändert.

Grenzen: API-/Firefox-Funktionen sind in automatisierten Tests simuliert. Kein Live-Test gegen die Benutzerinstanz und keine Prüfung in echtem Firefox. Ein versuchter zusätzlicher Chromium-Layouttest konnte mangels installiertem Browser nicht ausgeführt werden. Das XPI wurde gebaut und auf Archivkonsistenz geprüft; es ist nicht signiert.

## Frühere Testergebnisse zu 2.3.4

# Prüfprotokoll · 8. September 2026

- JavaScript: **65 Tests bestanden** (Node.js Test Runner).
- Python/Dateihelfer: **10 Tests bestanden** (unittest).
- HTML-ID-Verweise, Manifest-Ressourcen und JavaScript-/Python-Syntax geprüft.
- Linux-Installer in einem isolierten Testverzeichnis ausgeführt: Registrierung,
  tatsächlicher Launcherstart, Native-Messaging-Ping und Deinstallation erfolgreich.
- API-Antworten simuliert; kein Upload an eine echte Paperless-Instanz.
- Keine Laufzeitprüfung in Windows bzw. Firefox auf den Zielsystemen.
- Visuelle Prüfung blockiert: Cloud-Browser lässt lokale Vorschauadressen nicht zu.
- Mozilla-Signierung steht aus; temporäres Laden zum Testen ist vorgesehen.

Die Tests enthalten insbesondere den Nachweis, dass eine erfolgreiche HTTP-Antwort
allein keine Löschung auslöst. Erst passende Task-ID + SUCCESS + abrufbares Dokument
ermöglichen die Löschung. Bei Fehlern, Timeouts, fehlenden Rechten, fehlender
Dokument-ID und geänderten/ersetzten Dateien bleibt das Original erhalten.

## Regression 2.0.1

Browserähnliche Prüfung des fetch-Aufrufkontexts: alter Code schlägt fehl,
korrigierter Code besteht. Zwei weitere Tests unterscheiden Anmelde- und
Uploadfehler und prüfen, dass Fehlertexte keinen Token enthalten.

## Regression 2.0.2

Reverse-Proxy-Folgelinks (HTTP, interne Hosts/Ports, andere Pfade und relative
Links) bleiben auf der konfigurierten HTTPS-API-Adresse. Ungültige und
rückwärts laufende Seitennummern werden abgelehnt. 24 JavaScript-Tests bestehen.

## Version 2.1.0

Drei weitere Regressionstests prüfen das kompakte Fenster ohne Token in der URL,
das Weiterlaufen eines gestarteten Auftrags trotz UI-Aufräumaktion sowie Badge-
und Benachrichtigungsverhalten bei Erfolg und Fehler. Die neuen Oberflächen wurden
statisch geprüft; die generierte Entwurfsvorschau ist kein Laufzeitnachweis.

## Version 2.1.1

Datumübertragung mit Zeitzonenumrechnung, Auslassen leerer Datumswerte und
Ausschluss des Dokumentdatums aus Profilen automatisiert geprüft.

## Version 2.1.2

Vier zusätzliche Tests führen das tatsächliche app.js mit einem minimalen DOM-
Testmodell aus. Sie prüfen Dateiübernahme bei noch wartender Metadaten-API,
sichtbaren Ladestatus, fehlende Übergaben und Fehler, die nach dem Laden von
Metadaten sichtbar bleiben. Diese Tests schlugen vor der Korrektur fehl.

Fünf zusätzliche Hintergrundtests prüfen Toolbar-Übernahme eines Mail-PDF-Links,
Rechtsklick mit Profil, interne Viewer-/Frame-Adressen, manuelle Auswahl auf
normalen Webseiten und korrigierbare ungültige Metadaten. Insgesamt 38 JavaScript-
und 10 Python-Tests bestehen. Kein Live-Test mit dem SOGo-Postfach des Nutzers
oder der echten Paperless-Instanz; keine native Firefox-Oberflächenprüfung.

## Version 2.2.0

Zusätzliche Regressionen prüfen:

- MD5-Kompatibilität gegen Node.js-Referenzwerte, inklusive Blockgrenzen und Binärdaten.
- API-v9-/v10-Ergebnisse; Duplikat-ID bei FAILURE ist kein erfolgreicher Import.
- Nein sendet nichts; Ja sendet unveränderte Bytes nur einmal, auch bei Doppelklick.
- Ablehnende Server und fehlgeschlagene Vorprüfung erhalten das lokale Original.
- Gleichzeitige identische Dateien erzeugen einen Upload und eine Entscheidung.
- Erfolgsbenachrichtigung und Badge bleiben korrekt bis zur Bestätigung sichtbar.
- Tatsächliches popup.js zeigt Original-Löschwarnung, Dokumentlink und Ja/Nein-Aktionen
  im DOM-Testmodell korrekt an.

49 JavaScript- und 10 Python-Tests bestanden. Die API-Strukturen wurden zusätzlich
mit dem offiziellen Quellcode der Version 3.1.3 abgeglichen. Kein Live-Upload an
die Paperless-Instanz des Nutzers und kein nativer Firefox-Oberflächentest.

## Version 2.3.0

Die automatisierten Prüfungen decken zusätzlich die Paperless-Custom-Field-
Datentypen, reine Datumswerte, Kalenderarithmetik für +4 Wochen, +1 Monat und
+6 Wochen sowie den JSON-Multipart-Upload ab. Weiter geprüft werden:

- Nextcloud-Anmeldung per App-Passwort ausschließlich im Sitzungsspeicher;
- Deck-Board-/Listenabfrage mit Basic Auth, `OCS-APIRequest` und ohne Redirects;
- Kartenanlage erst nach bestätigtem Paperless-Dokument;
- Fälligkeitsdatum und Markdown-Link zum Paperless-Dokument in der Karte;
- keine Deck-Karte nach Paperless-Fehler oder Dublettenentscheidung „Nein“;
- Wiederholung der Kartenprüfung ohne erneuten PDF-Upload;
- Suche nach bereits angelegten Karten vor einer Wiederholung;
- explizite Bestätigung vor einem zweiten POST nach unklarem Ergebnis;
- Erhalt des lokalen Originals, solange die Deck-Karte nicht bestätigt ist.

Die Deck-API wurde mit simulierten Antworten geprüft; es fand keine Anmeldung an
einer echten Nextcloud- oder Paperless-Instanz statt. Ein nativer Firefox-Test
auf Windows, Debian oder Ubuntu bleibt erforderlich.

## Version 2.3.1

Zwei zusätzliche UI-Regressionstests prüfen den sicheren Firefox-Viewer-Ablauf:

- Eine PDF aus dem Firefox-Viewer wird nicht automatisch über ihre Original-URL
  geladen; zuerst muss die annotierte oder unbearbeitete Fassung gewählt werden.
- Eine ausgewählte, zuvor aus Firefox exportierte PDF ersetzt die Viewer-URL.
  Das Plugin ruft die ursprüngliche PDF dabei nicht zusätzlich ab.

Damit bestehen 65 JavaScript- und 10 Python-Tests. Ob eine konkrete gespeicherte
PDF sämtliche Firefox-Anmerkungstypen enthält, muss mit dem eingesetzten Firefox
am Zielsystem geprüft werden; der Erweiterung ist der interne Editorzustand aus
Sicherheitsgründen nicht zugänglich.

## Version 2.3.2

Fünf zusätzliche Regressionstests prüfen den beschleunigten Viewer-Ablauf:

- Die Download-Überwachung akzeptiert nur eine vollständig abgeschlossene PDF,
  deren Download nach dem Aktivieren der Überwachung gestartet wurde.
- Veraltete Aktivierungszeitpunkte werden abgewiesen, damit keine frühere Datei
  versehentlich übernommen wird.
- Die erkannte annotierte PDF ersetzt die Viewer-URL automatisch, ohne das
  unbearbeitete Original abzurufen.
- Enter übernimmt in der Tagsuche den exakten oder ersten passenden Tag.
- Der obere Schnellstart ist im kompakten Fenster sichtbar und folgt dem
  Aktivierungszustand des regulären Auftragsknopfs.

Damit bestehen 70 JavaScript- und 10 Python-Tests.

## Version 2.3.3

Vier zusätzliche Regressionstests prüfen die schnelle Link-Rückgabe:

- Der bestätigte Paperless-Link wird erst kopiert, nachdem die vollständige
  Versandgruppe registriert wurde; laufende Mehrfachaufträge überschreiben die
  Zwischenablage nicht einzeln.
- Der manuelle Kopierbutton gibt ausschließlich den aus der bestätigten
  Dokument-ID gebildeten Paperless-Link zurück.
- Eine blockierte Zwischenablage verändert den erfolgreichen Archivstatus nicht
  und erzeugt eine sichtbare Rückfallmeldung für „Link kopieren“.
- Der Versanddialog registriert alle ausgewählten Dateien als eine Gruppe und
  schließt diese Gruppe erst nach dem Start aller Einzelaufträge ab.

Damit bestehen 74 JavaScript- und 10 Python-Tests.

## Version 2.3.4

Drei zusätzliche Regressionstests prüfen den optimierten Viewer-Ablauf:

- HTML-Anmeldeseiten sowie HTTP 401/403 eines geschützten PDF-Viewers lösen
  automatisch die Download-Überwachung aus.
- Bei mehreren neuen Downloads wird nur die PDF übernommen, deren Dokumentname
  zum aktiven Viewer passt; Firefox-Zusätze wie `(1)` bleiben zulässig.
- Eine direkt erreichbare Viewer-PDF ist sofort ausgewählt. Eine anschließend
  heruntergeladene annotierte Fassung ersetzt das Original, während eine
  abgebrochene Überwachung die bestehende Auswahl unverändert lässt.

Damit bestehen 77 JavaScript- und 10 Python-Tests.
