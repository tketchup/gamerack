# Änderungsverlauf

## Unveröffentlicht

* **Backlog-Score**: 0 bis 100 je Spiel aus einem Launcher, aus Liegezeit und
  bisher gespielten Stunden. Sortierung, Filter „Nur Backlog“ ab 60 Punkten und
  eine Zeile auf der Detailseite
* **Statistikseite** über einen Knopf in der Kopfleiste: Spielzeit, Starts,
  gespielte Spiele, Durchschnitt pro aktivem Tag und eine Bestenliste nach
  Spielzeit oder Starts. Zeitraum als Woche, Monat, Jahr, jemals oder eigener
  Bereich; Klick auf eine Zeile öffnet das Spiel
* **Verlaufsaufzeichnung** in `history.jsonl`, angehängt und nie umgeschrieben.
  Jeder Start sofort, jeder von einem Launcher gemeldete Zuwachs an Spielzeit
  beim nächsten Suchlauf. Sprünge über 24 Stunden werden verworfen, statt einem
  einzelnen Tag zugeschlagen zu werden
* **Filter als eigenes Fenster** hinter dem Trichter in der Kopfleiste:
  Sortierung, Quellen, Backlog mit Mindestwert und ausgeblendete Spiele, mit
  laufender Anzahl und einem Knopf zum Zurücksetzen. Der Trichter ist markiert,
  solange ein Filter greift. Im Ausklappmenü bleiben nur Ansichtsmodus,
  Cover-Größe und „Nur installierte“; die doppelten Aktionen dafür sind
  entfernt, damit Menü und Fenster nicht auseinanderlaufen können
* Erfolge bzw. Achievements sind bewusst nicht dabei — dafür bräuchte es einen
  Steam-Web-API-Schlüssel und die Steam-ID

Die Versionsnummer steht an einer Stelle: `gamerack/__init__.py`. Der
Info-Dialog liest sie von dort, damit beides nicht auseinanderläuft.

Zählweise: erste Zahl bei Umbauten, die etwas kaputtmachen können, zweite bei
neuen Funktionen, dritte bei Fehlerbehebungen.

## 1.1.0 — 17.09.2026

Erste Version unter Versionsverwaltung.

**Großansicht**

* Neue ganzseitige Ansicht pro Spiel mit Banner, Gesamtspielzeit, zuletzt
  gespielt, Startzahl, Kategorien und Beschreibung
* Knöpfe für Spielen, Bearbeiten, Ausblenden sowie einen, der nur den Launcher
  öffnet — ausgeblendet bei Quellen ohne eigenen Launcher
* Im Raster öffnet ein Klick diese Ansicht, statt das Spiel sofort zu starten
* Beim Zeigen auf ein Cover erscheinen ▶ und ⓘ
* Rechtsklickmenü führt jetzt getrennt „Details…“ und „Bearbeiten…“

**Bilder**

* Banner (1600×520) zusätzlich zum Cover, nachgeladen nur für das Spiel, das
  gerade angesehen wird
* Bildauswahl fragt mehrere Quellen ab und zeigt die Treffer zur Auswahl,
  statt den ersten zu nehmen; Suchbegriff änderbar, eigene Datei möglich
* Titelsuche bei Steam, damit auch Epic- und GOG-Spiele Artwork bekommen —
  funktioniert ohne SteamGridDB-Schlüssel

**Metadaten**

* Kategorien, Publisher, Erscheinungsdatum und Kurzbeschreibung, zuerst aus
  den Launchern, der Rest aus Valves Store-Schnittstelle
* Läuft im Hintergrund; das gerade geöffnete Spiel wird vorgezogen

**Konsolenmodus**

* Schaufenster im Vollbild, bedienbar mit dem Controller
* Controller direkt über `/dev/input/js*` gelesen, ohne Zusatzpaket; die
  Tastenbelegung wird vom Gerät erfragt statt geraten
* Start-Taste, `F11` und der Knopf ⛶ schalten um; Vollbild über den
  Fenstermanager zählt ebenfalls
* Kopfleiste verschwindet und kommt zurück, wenn die Maus den oberen Rand
  sucht
* Einstellungen zeigen erkannte Controller und die letzte Eingabe

**Ansichten und Filter**

* Schaufenster: Banner statt gestrecktem Cover, ausgewähltes Spiel immer an
  derselben Stelle im ersten Drittel, Scrollen möglich, Kacheln genau so groß
  wie das Cover, Knöpfe für Bearbeiten und Launcher
* Liste: Knopf, der nur den Launcher startet
* Filter nach Quelle: Steam, Heroic, Lutris, Sonstige
* Ansichtsmenü ohne Markennamen — nur Raster, Schaufenster, Liste

**Behoben**

* Cover im Raster waren dauerhaft abgedunkelt: der `GtkRevealer` bekam als
  Overlay-Kind die volle Fläche zugewiesen und zeichnete seinen Hintergrund,
  auch wenn er nichts zeigte. Jetzt über eine CSS-Klasse geblendet
* Start-Taste wirkte nur bei fokussiertem Fenster und nur, wenn der
  Konsolenmodus über den eigenen Knopf betreten wurde
* Achsenbelegung des Controllers wurde von der Nullfüllung der ioctl-Antwort
  überschrieben, wodurch alle Achsen als links/rechts galten
* Bildauswahl zeigte die Vorschaubilder in voller Auflösung, eine pro Zeile
* Konsolenmodus überschrieb die gespeicherte Standardansicht
* GTK-Warnung beim Scrollen im Schaufenster, weil die Polsterung mitten in
  der Größenberechnung geändert wurde

## 1.0 — vor der Versionsverwaltung

Kein Commit vorhanden, nur hier festgehalten: Erkennung von Spielen in Steam,
Heroic, Lutris, Flatpak und im Anwendungsmenü samt Abgleich von Dubletten,
Cover-Beschaffung, die drei Ansichten, Bearbeiten-Dialog, Spiele von Hand
eintragen, Einstellungen und der Schutz eigener Änderungen vor einem erneuten
Suchlauf.
