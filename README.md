# Projektbeschreibung: Paperless Send

## Projektziel

Paperless Send ist eine Firefox-Erweiterung für die schnelle, strukturierte und nachvollziehbare Übergabe von PDF-Dokumenten an Paperless-ngx. Sie verbindet die Dokumentenerfassung direkt mit dem Arbeitsablauf im Browser: PDFs können aus Webseiten, Webmail-Systemen, dem Firefox-PDF-Viewer oder über eine lokale Dateiauswahl übernommen, mit Metadaten versehen und anschließend an eine konfigurierte Paperless-ngx-Instanz übertragen werden.

Ziel des Projekts ist es, die manuelle Ablage von Dokumenten deutlich zu vereinfachen. Wiederkehrende Arbeitsschritte wie Dateidownload, lokales Wiederfinden, Upload, Verschlagwortung, Dublettenprüfung und anschließende Weiterverarbeitung werden in einem einheitlichen Workflow zusammengeführt.

Paperless Send ist eine eigenständige Erweiterung und kein offizielles Add-on des Paperless-ngx-Projekts.

## Einsatzbereich

Die Erweiterung richtet sich insbesondere an Anwenderinnen und Anwender, die regelmäßig PDF-Dokumente aus Webportalen, E-Mails, elektronischen Akten oder lokalen Verzeichnissen in Paperless-ngx übernehmen.

Typische Anwendungsfälle sind:

* Verarbeitung von Rechnungen, Bescheiden, Verträgen und Schriftverkehr,
* Erfassung umfangreicher Akten mit vielen einzelnen PDF-Dokumenten,
* Übernahme von PDFs aus Webmail- und Dokumentenportalen,
* strukturierte Zuordnung von Metadaten bereits vor dem Upload,
* Vermeidung unbeabsichtigter Mehrfachimporte,
* Erzeugung öffentlicher Paperless-Freigabelinks,
* Übergabe von Dokumentfristen an Nextcloud Deck,
* kontrollierte Löschung lokaler Originaldateien nach erfolgreicher Archivierung.

## Funktionsumfang

### Direkte Dokumentübernahme

PDF-Dokumente können über das Firefox-Kontextmenü, die Symbolleistenschaltfläche, Drag-and-drop oder die normale Dateiauswahl übernommen werden. Direkt erreichbare PDF-Adressen werden aus dem aktiven Browserkontext gelesen.

Bei geschützten Webmail- oder Portalansichten, bei denen ein direkter Abruf nicht möglich ist, kann Paperless Send einen anschließend gestarteten PDF-Download erkennen und übernehmen. Auch im Firefox-PDF-Viewer bearbeitete oder mit Anmerkungen versehene Fassungen lassen sich auf diese Weise erfassen.

### Metadaten und benutzerdefinierte Felder

Vor dem Versand können die von Paperless bereitgestellten Metadaten ausgewählt oder eingetragen werden:

* Dokumenttitel,
* Dokumentdatum einschließlich optionaler Uhrzeit,
* Tags,
* Korrespondent,
* Dokumenttyp,
* Speicherpfad,
* benutzerdefinierte Paperless-Felder.

Benutzerdefinierte Felder werden entsprechend ihres Paperless-Datentyps verarbeitet. Dazu gehören unter anderem Text-, Zahlen-, Währungs-, Datums-, Auswahl- und Dokumentverknüpfungsfelder.

Für häufig verwendete Zuordnungen können Profile gespeichert und später erneut ausgewählt werden. Zusätzlich ermittelt die Erweiterung lokal häufig verwendete Kombinationen aus Korrespondent, Tags und Dokumenttyp und kann daraus Zuordnungsvorschläge anbieten. Die Übernahme eines Vorschlags erfolgt ausschließlich nach ausdrücklicher Auswahl.

### Serienverarbeitung

Der Serienmodus ermöglicht die nacheinander erfolgende Bearbeitung mehrerer PDFs. Jedes Dokument erhält dabei einen eigenen Titel und kann individuell geprüft und angepasst werden.

Optional übernimmt Paperless Send die Zuordnung des zuletzt angenommenen Sendeauftrags für das nächste Dokument. Dazu gehören:

* Tags,
* Korrespondent,
* Dokumenttyp,
* Speicherpfad,
* Dokumentdatum,
* benutzerdefinierte Feldwerte,
* Status „Fertig zugeordnet“.

Alle übernommenen Angaben bleiben bearbeitbar. Der Dokumenttitel wird bewusst nicht übernommen. Freigaben, lokale Löschaufträge und Nextcloud-Deck-Aktionen werden ebenfalls nicht automatisch auf das nächste Dokument übertragen.

Die Serienvorlage wird ausschließlich im Arbeitsspeicher gehalten. Sie wird beim Sperren der Sitzung, bei einer erneuten Anmeldung, einem Wechsel der Paperless-Instanz oder beim Beenden von Firefox verworfen.

### Dublettenprüfung

Paperless Send berechnet die Prüfsumme der ausgewählten PDF und prüft, ob auf der verbundenen Paperless-Instanz bereits ein identisches Dokument vorhanden ist.

Gefundene Dubletten können vor dem Upload angezeigt und in der Vorschau betrachtet werden. Anschließend stehen mehrere Möglichkeiten zur Verfügung:

* Upload abbrechen,
* vorhandenen internen Paperless-Link verwenden,
* einen öffentlichen Freigabelink zum vorhandenen Dokument erzeugen,
* Metadaten des vorhandenen Dokuments übernehmen,
* das Dokument nach ausdrücklicher Bestätigung dennoch senden.

Die Prüfung erkennt identische Dateiinhalte. Inhaltlich ähnliche, neu exportierte oder technisch veränderte PDFs können unterschiedliche Prüfsummen besitzen und werden daher nicht zwingend als Dublette erkannt.

### Dokumentvorschau

Archivierte Dokumente und gefundene Dubletten können direkt in der Erweiterung betrachtet werden. Die mehrseitige Vorschau verwendet die in Firefox integrierte PDF-Anzeige. Das Blättern ist per Mausrad, Pfeiltasten sowie Bild-auf und Bild-ab möglich.

Paperless Send enthält keine eigene PDF-Rendering-Bibliothek. PDF-Dateien werden authentifiziert von der konfigurierten Paperless-Instanz abgerufen, als lokale Blob-URL an die Firefox-Anzeige übergeben und nur vorübergehend im Arbeitsspeicher gehalten.

### Öffentliche Freigabelinks

Nach erfolgreicher Archivierung kann die Erweiterung über die Paperless-API einen öffentlichen Freigabelink erzeugen. Unterstützt werden zeitlich begrenzte und unbefristete Freigaben sowie optional die Freigabe der Archivversion.

Der erzeugte Link wird automatisch in die Zwischenablage kopiert. Bereits archivierte Aufträge können auch nachträglich aus dem Auftragsfenster heraus freigegeben werden. Verwaltung und Widerruf der Links erfolgen weiterhin in Paperless-ngx.

### Nextcloud-Deck-Integration

Optional kann ein ausgefülltes Datumsfeld zur Erstellung einer Nextcloud-Deck-Karte verwendet werden. Die Karte enthält das ausgewählte Datum, die Dokumentinformationen und einen Link zum erfolgreich archivierten Paperless-Dokument.

Die Deck-Karte wird erst erstellt, nachdem Paperless die Archivierung bestätigt hat. Schlägt nur die Deck-Verarbeitung fehl, bleibt der Paperless-Import erfolgreich und der offene Folgeschritt kann wiederholt werden, ohne das PDF erneut hochzuladen.

### Kontrollierte lokale Löschung

Lokale Originaldateien können auf Wunsch nach bestätigter Verarbeitung gelöscht werden. Hierfür steht ein optionaler Native-Messaging-Dateihelfer für Windows, Debian und Ubuntu zur Verfügung.

Vor der Löschung werden unter anderem Pfad, Dateityp, Dateigröße und Prüfsumme geprüft. Ein Dateiname allein reicht niemals als Löschgrundlage aus. Bei einem Fehler, einem Timeout oder einer veränderten Datei bleibt das lokale Original erhalten.

### Auftragsverwaltung

Uploads und nachgelagerte Verarbeitungsschritte werden als Aufträge dargestellt. Die Erweiterung unterscheidet unter anderem zwischen:

* angenommenem Upload,
* laufender Paperless-Verarbeitung,
* erfolgreicher Archivierung,
* offener Freigabe,
* offener Deck-Verarbeitung,
* offener Entfernung von Posteingangs-Tags,
* fehlgeschlagener oder nicht bestätigter lokaler Löschung.

Fehlgeschlagene Folgeschritte können getrennt wiederholt werden. Dadurch wird verhindert, dass ein bereits erfolgreich archiviertes Dokument unbeabsichtigt erneut hochgeladen wird.

## Datenschutz und Sicherheit

Paperless Send kommuniziert ausschließlich mit den vom Benutzer konfigurierten Paperless- und optionalen Nextcloud-Instanzen. Es werden keine externen Analyse-, Tracking- oder Cloud-Dienste eingebunden.

Der Paperless-API-Token wird für die aktive Sitzung entsperrt. Dokumentvorschauen, Serienvorlagen und zwischengespeicherte PDF-Daten verbleiben nur vorübergehend im Arbeitsspeicher und werden bei Sitzungs- oder Instanzwechsel verworfen.

Die Erweiterung verwendet eine restriktive Content Security Policy. Es gibt keinen dynamisch nachgeladenen Programmcode, kein JavaScript-`eval`, kein WebAssembly und keine verschleierten oder minifizierten Programmbestandteile. Die in der Erweiterung enthaltenen Laufzeitquellen liegen als lesbarer eigener JavaScript- und CSS-Code vor.

Einige Komfortfunktionen speichern lokal und getrennt nach Paperless-Adresse unter anderem Profile, Titelverläufe und häufig verwendete Zuordnungskombinationen. PDF-Inhalte und konkrete Werte benutzerdefinierter Felder werden für diese Vorschlagsfunktion nicht dauerhaft gespeichert.

## Technische Grundlage

Paperless Send ist als klassische Firefox-WebExtension umgesetzt. Die Erweiterung greift über die REST-API auf Paperless-ngx zu und verwendet für die optionale Nextcloud-Integration die Nextcloud-Deck-API.

Zielplattformen sind:

* Firefox Desktop ab Version 140,
* Windows,
* Debian,
* Ubuntu.

Der optionale Dateihelfer basiert auf Python und Firefox Native Messaging. Der eigentliche Erweiterungsbuild benötigt lediglich Python ab Version 3.9 und verwendet keine externen Build-Abhängigkeiten.

## Projektstand

Der aktuelle Entwicklungsstand ist Version 2.4.12. Diese Version ergänzt insbesondere die bearbeitbare Übernahme der letzten Zuordnung im Serienmodus und verwendet weiterhin die native Firefox-PDF-Anzeige für mehrseitige Vorschauen.

Die Erweiterung liegt derzeit als unsignierte XPI-Datei einschließlich vollständigem Quellpaket, Build-Skript, Tests, Prüferhinweisen und dokumentierten Testergebnissen vor. Sie ist für eine private Verteilung über Mozillas „Unlisted“-Verfahren vorbereitet.

Eine Signierung oder Freigabe durch Mozilla ist mit dem vorliegenden Paket noch nicht erfolgt. Für eine dauerhafte Installation in regulären Firefox-Versionen muss die XPI zunächst von Mozilla geprüft und signiert werden.

## Abgrenzung

Paperless Send ersetzt weder Paperless-ngx noch dessen serverseitige Berechtigungs-, Workflow- oder Dublettenregeln. Die Erweiterung stellt eine komfortable, browserbasierte Erfassungs- und Verarbeitungsschicht vor der vorhandenen Paperless-API bereit.

Die endgültige Archivierung, Volltextverarbeitung, Rechteprüfung und Dokumentverwaltung verbleiben vollständig bei Paperless-ngx. Ebenso richtet sich die Erreichbarkeit öffentlicher Freigabelinks nach der Netzwerkkonfiguration der jeweiligen Paperless-Instanz.
