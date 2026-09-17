# Gamerack

Eine Spielebibliothek für Linux als Ersatz für GNOME Cartridges. Findet deine
Spiele selbst, holt Cover, Banner und Metadaten automatisch und zeigt alles
wahlweise als Raster, Schaufenster oder Liste.

Gamerack liest deine Launcher nur — es installiert, verschiebt und löscht dort
nichts.

## Was gefunden wird

| Quelle | Woher |
| --- | --- |
| Steam | `appmanifest_*.acf` aller Bibliotheksordner (auch auf anderen Platten), plus Nicht-Steam-Verknüpfungen und die Spielzeit aus `localconfig.vdf` |
| Heroic | Die zwischengespeicherten Bibliotheken für Epic, GOG, Amazon und Sideloads |
| Lutris | Die Datenbank `pga.db` (schreibgeschützt geöffnet) |
| Flatpak | Exportierte `.desktop`-Einträge mit Kategorie `Game` |
| Anwendungsmenü | Alle übrigen `.desktop`-Einträge mit Kategorie `Game` |

Findet dieselbe Sache in mehreren Quellen auf, gewinnt der echte Launcher: ein
Steam-Spiel wird nicht zusätzlich als Menüeintrag geführt.

## Bilder

Jedes Spiel hat ein **Cover** (2:3, für das Raster) und ein **Banner** (breit,
für Schaufenster und Großansicht). Beide werden der Reihe nach gesucht, jeweils
nur wenn der Schritt davor nichts geliefert hat:

1. Ein Bild, das du selbst ausgewählt hast
2. Artwork, das der Launcher schon heruntergeladen hat (Steams `librarycache`, Lutris)
3. Die Bild-URL, die der Launcher meldet (Heroic)
4. Valves CDN, für alles mit Steam-App-ID
5. SteamGridDB, sobald du in den Einstellungen einen API-Schlüssel hinterlegst
6. Das Programmsymbol, mittig auf einem unscharfen Hintergrund

Cover werden auf 600×900 normalisiert, Banner auf 1600×520, beide liegen unter
`~/.local/share/gamerack/covers/`.

Banner werden nur für das Spiel geholt, das du gerade ansiehst — dreihundert
Stück im Voraus herunterzuladen wäre Verschwendung.

### Ein Bild selbst aussuchen

Über **Bearbeiten → Lupe** (oder den Stift auf dem Banner der Großansicht)
öffnet sich eine Auswahl. Gamerack fragt dabei mehrere Quellen ab: was der
Launcher gespeichert hat, Valves CDN — inklusive einer Titelsuche bei Steam,
sodass auch ein Epic- oder GOG-Spiel Steam-Artwork bekommt — und SteamGridDB,
falls ein Schlüssel hinterlegt ist. Du kannst den Suchbegriff ändern oder eine
eigene Datei wählen. Den kostenlosen SteamGridDB-Schlüssel gibt es unter
<https://www.steamgriddb.com/profile/preferences/api>.

## Metadaten

Kategorien, Publisher, Erscheinungsdatum und eine Kurzbeschreibung kommen
zuerst aus den Launchern selbst (Heroic kennt Genres und Beschreibungen, das
Anwendungsmenü seine Kategorien). Was dann noch fehlt, holt Gamerack aus Valves
öffentlicher Store-Schnittstelle — auch für Spiele, die du gar nicht auf Steam
besitzt, denn der Titel reicht zum Nachschlagen.

Das läuft langsam im Hintergrund; ein Spiel, das du gerade öffnest, wird
vorgezogen. Abschaltbar unter Einstellungen → Bilder & Daten.

## Ansichten

* **Raster** — der Standard, wie Cartridges. Cover-Größe im Ansichtsmenü. Ein
  Klick öffnet die Großansicht; beim Zeigen auf ein Cover dunkelt es ab und ▶
  zum Starten sowie ⓘ für die Großansicht erscheinen. Unberührte Cover bleiben
  unverändert hell.
* **Schaufenster** — großes Banner, darunter eine waagerechte Reihe. Mit ← und →
  blättern, Enter startet, das Mausrad blättert ebenfalls. Das ausgewählte
  Spiel steht immer an derselben Stelle im ersten Drittel; die Reihe wandert
  darunter durch. Damit das auch für das erste und das letzte Spiel gilt, ist
  die Reihe an beiden Enden entsprechend gepolstert.
* **Liste** — schmale Zeilen, ein Klick klappt kurze Details aus.

### Spieldauer

Die Detailseite hat eine Zeile **Spieldauer**, die die Suche bei
HowLongToBeat im Browser öffnet — als Verweis, nicht als Abfrage.

HowLongToBeat hat keine offene Schnittstelle. Die Suche des Browsers verlangt
ein ablaufendes Token und einen berechneten Zusatzschlüssel im Kopf der
Anfrage, also eine Bot-Abwehr. Die zu umgehen wäre erstens genau das, was die
Seite verhindern will, und zweitens beim nächsten Umbau ihrer Oberfläche wieder
kaputt. Wenn die Zahlen einmal in Gamerack selbst stehen sollen, ist IGDB der
richtige Weg: offizielle Schnittstelle, kostenlos mit einer Twitch-Kennung, und
sie führt dieselben drei Werte.

### Mods

Bei Steam-Spielen listet die Großansicht die installierten Workshop-Objekte mit
Namen, Größe und Datum der letzten Änderung; ein Klick öffnet die
Workshop-Seite. Die Liste kommt aus `appworkshop_<appid>.acf` in allen
Bibliotheksordnern und ist damit genau das, was Steam wirklich auf der Platte
liegen hat. Nur die Namen kommen aus dem Netz und werden dauerhaft
zwischengespeichert, weil sie sich nicht ändern.

DLC ist bewusst nicht dabei. Der Store weiß, was es für ein Spiel *gibt*, aber
keine Datei sagt, was davon dir gehört — und eine Liste, die wie ein
Besitzstand aussieht und in Wahrheit ein Katalog ist, wäre schlechter als keine.

### Großansicht

Banner, Spielzeit, zuletzt gespielt, Kategorien und Beschreibung, dazu
**Spielen**, **Bearbeiten**, **Ausblenden** und ein Knopf, der den Launcher
öffnet, ohne das Spiel zu starten. Der erscheint nur für Steam, Heroic und
Lutris — bei einem Flatpak oder Menüeintrag gibt es nichts zu öffnen. Oben
links geht es zurück zur Bibliothek.

## Konsolenmodus

Der Knopf ⛶ in der Kopfleiste — links neben der Suche, und auch in der
Großansicht vorhanden — schaltet das Schaufenster ins Vollbild. `F11` und die
**Start-Taste** am Controller tun dasselbe.

Die Kopfleiste verschwindet dabei samt Fensterknöpfen, und das Bild reicht bis
an die Oberkante. Fährst du mit der Maus an den oberen Rand, fährt sie wieder
heraus — mit Hintergrund, damit sie über dem Banner lesbar bleibt — und
verschwindet, sobald du dich wieder nach unten bewegst. Die Maus bleibt also
voll benutzbar: Ansicht wechseln, filtern, suchen, und derselbe Knopf beendet
das Vollbild wieder.

| Controller | Wirkung |
| --- | --- |
| Start | Konsolenmodus an und aus |
| Steuerkreuz / linker Stick | Blättern, in der Großansicht Knöpfe anwählen |
| A | Spielen, bzw. den angewählten Knopf drücken |
| B | Zurück; auf der Bibliotheksseite verlässt es den Konsolenmodus |
| Y | Großansicht |
| X | Bearbeiten |

Vollbild, das auf anderem Weg entsteht — über den Fenstermanager, `F11`, den
Titelleistenknopf —, gilt ebenfalls als Konsolenmodus. Sonst säße der Controller
in einem Fenster, das richtig aussieht, aber nicht auf ihn hört.

Gamerack liest die Pads direkt über `/dev/input/js*`, ohne Zusatzpaket. Zwei
ioctls fragen das Gerät, welche physische Taste hinter welcher Nummer steckt,
statt eine Nummerierung zu raten. Nötig ist nur Lesezugriff — auf den meisten
Systemen gegeben, sonst hilft Mitgliedschaft in der Gruppe `input`. Pads, die
erst später eingeschaltet werden, werden im Zwei-Sekunden-Takt bemerkt.

Unter Einstellungen → Quellen → Bedienung stehen die erkannten Controller und
die zuletzt empfangene Eingabe. Dort lässt sich in zwei Sekunden feststellen, ob
Gamerack den Controller gar nicht sieht, ihn sieht aber nichts empfängt, oder
eine Taste anders ankommt als erwartet. Am selben Ort lässt sich die
Controller-Unterstützung abschalten.

Die Start-Taste wirkt, sobald Gamerack läuft — auch wenn das Fenster nicht im
Vordergrund ist. Das ist Absicht, damit der Modus vom Sofa aus erreichbar
bleibt; der Preis ist, dass ein Druck auf Start während eines laufenden Spiels
Gamerack nach vorn holt.

## Ambient-Modus

Bleibt das Schaufenster eine Minute unberührt, übernimmt eine Bildschau:
Screenshots der Spiele aus deiner Bibliothek, einzeln im Vollbild, sanft
überblendet und mit dem Namen unten links. Jede Eingabe beendet sie wieder —
eine Taste, ein Klick, das Mausrad oder der Controller; die erste Eingabe tut
sonst nichts, wie bei einem Bildschirmschoner.

Eine ruhende Maus weckt ihn nicht. Erscheint die Bildschau unter einem
Zeiger, der schon dort lag, liefert das System dafür ein Bewegungsereignis, und
darauf zu reagieren würde sie im selben Moment wieder schließen. Der Zeiger muss
sich erst ein Stück bewegen.

Die Bilder sind Steam-Screenshots in 1920×1080, also genau 16:9; passt das nicht
zum Fenster, wird zugeschnitten statt verzerrt. Gezeigt werden nur Spiele, für
die ein Bild vorliegt — bei einer Bibliothek von 293 Spielen sind das
derzeit 221. Geladen wird erst, wenn ein Bild gebraucht wird, und der Ordner
behält nur die letzten 45.

Abschaltbar unter Einstellungen → Bedienung, zusammen mit der Wartezeit.

## Filtern

Der Trichter in der Kopfleiste öffnet ein eigenes Fenster über der Bibliothek.
Darin stehen die Sortierung, die Quellen (Steam, Heroic, Lutris und Sonstige —
also Flatpak, Anwendungsmenü und selbst eingetragene Spiele), der Backlog samt
Mindestwert und „Ausgeblendete zeigen“. Jede Änderung wirkt sofort, unten steht
laufend, wie viele Spiele übrig bleiben, und „Zurücksetzen“ nimmt alles auf
einmal weg.

Solange ein Filter etwas zurückhält, ist der Trichter farbig markiert — sonst
sucht man lange, warum die Bibliothek halb leer aussieht.

Im Ansichtsmenü bleiben nur die zwei Schalter, die man ständig umlegt: der
Ansichtsmodus und „Nur installierte“.

## Backlog-Score

Jedes Spiel aus einem Launcher bekommt einen Wert von 0 bis 100, der sagt, wie
fällig es wäre. Er wird aus zwei Faktoren gebildet: wie lange das Spiel
unangetastet liegt, und wie wenig davon gespielt ist. Bereits versenkte Stunden
drücken den Wert — achtzig Stunden tief ist kein Backlog. Der höchste
Startwert geht an Spiele, die installiert und nie gestartet wurden.

Sortierbar über das Ansichtsmenü, sichtbar auf der Detailseite, und „Nur
Backlog“ engt die Bibliothek auf alles ab 60 Punkten ein. Die Schwelle steht
als `backlog_min` in den Einstellungen; senkst du sie auf 50, kommt der große
Stapel dazu, der nur besessen und nie installiert ist.

Ein Kaufdatum führt kein Launcher, deshalb zählt für ein nie gestartetes Spiel
der Tag, an dem Gamerack es zuerst gesehen hat. Am Anfang ist der Score dadurch
grob — alle nie gespielten Titel starten gemeinsam auf dem gleichen Wert — und
er wird über die Monate genauer.

## Statistik

Der Knopf mit dem Balkendiagramm in der Kopfleiste öffnet eine eigene Seite:
Spielzeit, Starts, Anzahl gespielter Spiele und der Durchschnitt pro aktivem
Tag, dazu eine Bestenliste nach Spielzeit oder nach Starts. Ein Klick auf eine
Zeile springt zur Detailseite des Spiels.

Zeitraum wählbar als Woche, Monat, Jahr, jemals oder ein eigener Bereich über
zwei Kalender. Woche, Monat und Jahr sind rollend gerechnet, also die letzten
7, 30 und 365 Tage.

**Die Daten beginnen mit dem ersten Start dieser Version.** Die Launcher führen
nur Summen — Steam kennt die Gesamtspielzeit eines Spiels und den Tag, an dem es
zuletzt lief, aber keine Zeitreihe. Was vorher gespielt wurde, hat niemand
mitgeschrieben und fehlt hier. Die Seite sagt das auch selbst, solange der
gewählte Zeitraum weiter zurückreicht als die Aufzeichnung.

Mitgeschrieben wird zweierlei: jeder Start, den Gamerack auslöst, sofort, und
jeder Zuwachs an Spielzeit, den ein Launcher meldet, beim nächsten Suchlauf.
Der zweite Weg kommt in Schüben, weil Steam seine Zahlen erst beim Beenden
schreibt — die Spielzeit landet dann an dem Tag, an dem Gamerack sie bemerkt,
was bei einer Sitzung über Mitternacht einen Tag verschieben kann. Ein
unplausibler Sprung von mehr als 24 Stunden wird verworfen statt einem Tag
zugeschlagen.

## Installation

Voraussetzungen: Python 3.11+, GTK 4, libadwaita 1.5+, PyGObject sowie die
Python-Pakete `requests`, `Pillow` und `vdf`.

Auf Arch:

```bash
sudo pacman -S --needed python-gobject gtk4 libadwaita python-requests python-pillow python-vdf
```

Dann im Projektordner:

```bash
./install.sh
```

Das legt `~/.local/bin/gamerack` und einen Menüeintrag an. Ohne Installation
geht auch `./gamerack.sh`.

## Bedienung

| Taste | Wirkung |
| --- | --- |
| Klick auf ein Spiel | Großansicht öffnen |
| Zeigen, dann ▶ | Direkt starten |
| Rechtsklick | Menü: Spielen, Details, Bearbeiten, Launcher, Ausblenden |
| `Strg`+`F` | Suche |
| `Strg`+`R` | Neu suchen |
| `Strg`+`1` / `2` / `3` | Raster / Schaufenster / Liste |
| `Strg`+`,` | Einstellungen |
| `F11` | Konsolenmodus |
| `Esc` | Zurück zur Bibliothek, Konsolenmodus verlassen |

Über `+` in der Kopfleiste trägst du ein Spiel von Hand ein, etwa einen
Emulator-Aufruf oder ein Skript.

## Eigene Änderungen bleiben erhalten

Änderst du Titel, Entwickler, Startbefehl, Cover oder Banner, wird das Feld als
Übersteuerung vermerkt. Ein späterer Suchlauf aktualisiert alle anderen Felder,
lässt deine Änderung aber in Ruhe. Verschwindet ein Spiel aus seiner Quelle,
wird es ausgeblendet statt gelöscht — Spielzeit und Bearbeitungen überleben
eine vorübergehend nicht erreichbare Festplatte.

## Dateien

```
~/.local/share/gamerack/library.json   erkannte Spiele und deine Änderungen
~/.local/share/gamerack/history.jsonl  Starts und Spielzeit, für die Statistik
~/.local/share/gamerack/covers/        Cover und Banner
~/.config/gamerack/settings.json       Einstellungen
~/.cache/gamerack/metadata/            Antworten des Steam-Stores
~/.cache/gamerack/ambient/             Screenshots für den Ambient-Modus
```

Bibliothek und Einstellungen sind normales JSON und lassen sich von Hand
bearbeiten. Der Cache-Ordner kann jederzeit gelöscht werden. `history.jsonl`
ist eine Zeile JSON je Ereignis und wird nur angehängt, niemals umgeschrieben —
löschst du sie, fängt die Statistik von vorn an.

Die Ordner oben liegen außerhalb des Projektordners. Ein Rücksprung auf eine
ältere Version wirft deine Bibliothek also nicht weg.

## Versionen

Der Stand ist in Git festgehalten, jede Version hat eine Marke. Was sich wann
geändert hat, steht in [CHANGELOG.md](CHANGELOG.md).

```bash
git -C ~/Documents/code/cartridges tag
```

Zurück auf eine ältere Version und wieder nach vorn:

```bash
git checkout v1.1.0
```

```bash
git checkout main
```
