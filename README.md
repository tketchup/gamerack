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

## Filtern

Im Ansichtsmenü lässt sich die Bibliothek auf einzelne Quellen einschränken:
Steam, Heroic, Lutris und Sonstige (Flatpak, Anwendungsmenü, selbst
eingetragene Spiele). Dazu kommen „Nur installierte“ und „Ausgeblendete
zeigen“.

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
~/.local/share/gamerack/covers/        Cover und Banner
~/.config/gamerack/settings.json       Einstellungen
~/.cache/gamerack/metadata/            Antworten des Steam-Stores
```

Bibliothek und Einstellungen sind normales JSON und lassen sich von Hand
bearbeiten. Der Cache-Ordner kann jederzeit gelöscht werden.

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
