# Splat Relight

Blender add-on for relighting native Gaussian Splats (Blender 5.3+). Works in Cycles and EEVEE.

[English](#english) · [Deutsch](#deutsch)

---

## English

### What it does

Blender 5.3 can import and render Gaussian Splats natively, but relighting them only works in a basic way. The splat colour already contains the lighting from the capture, and each splat's built-in normal is its shortest ellipsoid axis. For splats from ordinary 3DGS training that axis points in a random direction. The result is flat, dark or spotty lighting.

Splat Relight sets up a full relighting pipeline with one click:

- **Normals from the neighbourhood.** A local PCA over the surrounding splats (voxel grid) gives each splat a surface normal. Normals are oriented toward the camera, a chosen object, or world up.
- **Albedo and delighting.** The DC colour without spherical harmonics serves as albedo. A low-frequency brightness map (`baked_light`) weakens the light and shadow that are baked into the capture.
- **Shader.** Principled BSDF plus a little Translucent, driven by the computed attributes. The original look can be mixed back in as emission.
- **Shadow proxy.** A second object that only casts shadows. It drops low-opacity splats and floaters outside a box, and is pushed back along the normal. You get real cast shadows without self-shadowing noise.
- **Light rig (optional).** Sun, sky and moon placed by time of day, date and location. Supports keyframes.

Your original splat data is never changed. Everything is written to new attributes.

### Requirements

- Blender 5.3 or newer
- A Gaussian Splat imported as a point cloud (PLY or SPZ, attribute `radiance:base`)

### Installation

1. Download `splat_relight-x.y.z.zip` from the releases, or build it yourself (see [Development](#development)).
2. Drag the zip into Blender, or go to *Edit → Preferences → Get Extensions → Install from Disk*.
3. Open the sidebar in the 3D viewport (`N`) and select the **Splat Relight** tab.

### Quick start

1. Import your splat and select it.
2. Set **Scale** to the number of Blender units per real metre. Example: if the splat is 1.8× too large, set 1.8.
3. Optional: place a camera roughly at the capture position. Normals are oriented toward it.
4. Click **Relight einrichten** (Set up relighting).
5. Adjust the look in the **Shader**, **Schatten** (Shadows) and **Licht-Rig** (Light rig) sub-panels.

On a large splat (around 10 million splats) the computation takes a little while. Afterwards, *Nur Attribute neu berechnen* recomputes only the attributes, for example after you change the voxel size.

### Settings

The interface is in German. English translations are given in brackets.

**Setup**

| Setting | Default | Meaning |
|---|---|---|
| Maßstab (Scale) | 1.0 | Blender units per real metre. All metre values below are multiplied by it |
| Normalen-Voxel (Normal voxel) | 0.15 m | Neighbourhood size for the PCA normal. Smaller gives more detail, larger gives calmer shading |
| Delight-Blur | 1.0 m | Size over which baked light is averaged |
| Normalen → (Normals toward) | Scene camera | Camera, object, or up (world +Z) |
| Material / Schattenproxy / Licht-Rig | on / on / off | What gets created |
| Min Opazität (Min opacity) | 0.35 | Splats below this value cast no shadow |
| Shadow Bias | 0.05 m | How far the shadow proxy is pushed back along the normal |

**Shader**

| Input | Default | Meaning |
|---|---|---|
| Delight | 0.6 | Strength of delighting: `albedo / baked_light^Delight` |
| Albedo Gamma | 2.2 | Converts sRGB albedo to linear |
| Helligkeit / Sättigung (Brightness / Saturation) | 1.0 / 1.0 | Albedo correction |
| Translucent | 0.15 | Share of light from behind |
| Rauheit (Roughness) / Specular | 0.8 / 0.3 | Principled BSDF |
| Original-Look | 0.0 | Mixes the original radiance back in as emission (0 = fully relit) |
| Tageslicht (Daylight) | 1.0 | Set by the light rig. Fades out the original look at night |
| Emission Stärke (Emission strength) | 1.0 | Strength of the original radiance |

**Shadows:** self-shadowing of the splat on/off, proxy values, *Box neu anpassen* (refit box: fits the shadow area to the dense part of the splat), *Entfernen* (remove proxy and box).

**Light rig:** time of day, day of year (with a *Today* button), latitude and longitude, UTC offset, north direction, and strengths for sun, sky, moon and night sky. The sun position uses the NOAA approximation. Sun strength follows air mass (Kasten-Young, Meinel). Colour temperature goes from 1900 K at the horizon to 6000 K. The sky is a *Multiple Scattering* sky texture. Time of day can be keyframed, and the rig follows during playback and rendering.

### Cycles vs. EEVEE

For every splat, Cycles decides from the splat's own geometric normal whether light counts as reflection or transmission. With random normals, about half of all splats would get no light through the Principled BSDF. To prevent this, the material has a separate Cycles output. It adds a Translucent BSDF with the flipped normal, which picks up exactly the light the Principled BSDF misses. EEVEE uses the plain shader. Both engines then produce comparable results.

### Limitations

- Reflections and glass stay baked in.
- Delighting is a heuristic. Large real brightness differences are weakened as well.
- Floaters stay visible to the camera. They are only removed from the shadow proxy.
- On the side that Cycles counts as transmission there is no specular highlight. At roughness 0.8 this is barely visible.
- The moon direction is set by hand. Stars and light pollution are not included.

### Development

- `splat_relight/`: add-on source (Blender extension)
- `dev/`: test scripts. `make_test_ply.py` creates a synthetic splat scene, `compare_engines.py` and `verify_fix.py` render it in Cycles and EEVEE for comparison, `check_panels.py` runs every panel headlessly and checks icons, properties and operators.

Build:

```bash
blender --command extension build --source-dir splat_relight --output-dir .
```

### License

GPL-3.0-or-later

---

## Deutsch

### Was es macht

Blender 5.3 kann Gaussian Splats nativ importieren und rendern, neu beleuchten lassen sie sich aber nur rudimentär. Die Splat-Farbe enthält das Licht der Aufnahme, und die eingebaute Normale jedes Splats ist seine kürzeste Ellipsoid-Achse. Bei normal trainierten Splats zeigt diese Achse zufällig. Das Ergebnis ist flach, dunkel oder fleckig.

Splat Relight richtet mit einem Klick eine komplette Relighting-Pipeline ein:

- **Normalen aus der Nachbarschaft.** Eine lokale PCA über die umliegenden Splats (Voxelgitter) gibt jedem Splat eine Flächennormale. Die Normalen zeigen zur Kamera, zu einem gewählten Objekt oder nach oben.
- **Albedo und Delighting.** Die DC-Farbe ohne Spherical Harmonics dient als Albedo. Eine tieffrequente Helligkeitskarte (`baked_light`) schwächt eingebackenes Licht und eingebackene Schatten ab.
- **Shader.** Principled BSDF plus etwas Translucent, gesteuert über die berechneten Attribute. Der Original-Look lässt sich als Emission zurückmischen.
- **Schattenproxy.** Ein zweites Objekt, das nur Schatten wirft. Es lässt Splats mit geringer Deckkraft und Floater außerhalb einer Box weg und ist entlang der Normale nach hinten versetzt. So gibt es echte Schlagschatten ohne Selbstschatten-Rauschen.
- **Licht-Rig (optional).** Sonne, Himmel und Mond nach Uhrzeit, Datum und Ort. Keyframes sind möglich.

Die Original-Daten des Splats bleiben unverändert. Alles wird in neue Attribute geschrieben.

### Voraussetzungen

- Blender 5.3 oder neuer
- Ein als Point Cloud importierter Gaussian Splat (PLY oder SPZ, Attribut `radiance:base`)

### Installation

1. `splat_relight-x.y.z.zip` aus den Releases laden oder selbst bauen (siehe [Entwicklung](#entwicklung)).
2. Zip in Blender ziehen oder *Edit → Preferences → Get Extensions → Install from Disk*.
3. Im 3D-Viewport die Sidebar öffnen (`N`) und den Tab **Splat Relight** wählen.

### Schnellstart

1. Splat importieren und auswählen.
2. **Maßstab** auf die Anzahl Blender-Einheiten pro realem Meter setzen. Beispiel: Ist der Splat 1,8× zu groß, 1,8 eintragen.
3. Optional: Eine Kamera ungefähr an die Aufnahmeposition stellen. Die Normalen werden zu ihr ausgerichtet.
4. **Relight einrichten** klicken.
5. Look in den Unterpanels **Shader**, **Schatten** und **Licht-Rig** einstellen.

Bei großen Splats (etwa 10 Mio. Splats) dauert die Berechnung etwas. Danach berechnet *Nur Attribute neu berechnen* nur die Attribute neu, zum Beispiel nach einer Änderung der Voxelgröße.

### Einstellungen

**Setup**

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Maßstab | 1,0 | Blender-Einheiten pro realem Meter. Alle Meter-Werte darunter werden damit multipliziert |
| Normalen-Voxel | 0,15 m | Nachbarschaft für die PCA-Normale. Kleiner = mehr Detail, größer = ruhiger |
| Delight-Blur | 1,0 m | Größe, über die eingebackenes Licht gemittelt wird |
| Normalen → | Szenenkamera | Kamera, Objekt oder oben (Welt +Z) |
| Material / Schattenproxy / Licht-Rig | an / an / aus | Was angelegt wird |
| Min Opazität | 0,35 | Splats darunter werfen keinen Schatten |
| Shadow Bias | 0,05 m | Wie weit der Schattenproxy entlang der Normale zurückversetzt wird |

**Shader**

| Eingang | Standard | Bedeutung |
|---|---|---|
| Delight | 0,6 | Stärke des Delightings: `Albedo / baked_light^Delight` |
| Albedo Gamma | 2,2 | Linearisiert die sRGB-Albedo |
| Helligkeit / Sättigung | 1,0 / 1,0 | Albedo-Korrektur |
| Translucent | 0,15 | Anteil Licht von hinten |
| Rauheit / Specular | 0,8 / 0,3 | Principled BSDF |
| Original-Look | 0,0 | Original-Radiance als Emission beimischen (0 = voll neu beleuchtet) |
| Tageslicht | 1,0 | Wird vom Licht-Rig gesetzt. Blendet den Original-Look nachts aus |
| Emission Stärke | 1,0 | Stärke der Original-Radiance |

**Schatten:** Selbstschatten des Splats an/aus, Proxy-Werte, *Box neu anpassen* (setzt den Schattenbereich auf den dichten Teil des Splats), *Entfernen* (Proxy und Box löschen).

**Licht-Rig:** Uhrzeit, Tag im Jahr (mit *Heute*-Knopf), Breite und Länge, UTC-Offset, Nordrichtung sowie Stärken für Sonne, Himmel, Mond und Nachthimmel. Der Sonnenstand nutzt die NOAA-Näherung. Die Sonnenstärke folgt der Luftmasse (Kasten-Young, Meinel). Die Farbtemperatur geht von 1900 K am Horizont bis 6000 K. Der Himmel ist eine *Multiple Scattering*-Sky-Texture. Die Uhrzeit lässt sich keyframen, das Rig folgt beim Abspielen und Rendern.

### Cycles vs. EEVEE

Cycles entscheidet für jeden Splat über dessen eigene Geometrie-Normale, ob Licht als Reflexion oder Transmission zählt. Bei zufälligen Normalen würde etwa die Hälfte der Splats über den Principled BSDF kein Licht bekommen. Damit das nicht passiert, hat das Material einen eigenen Cycles-Ausgang. Er ergänzt einen Translucent-BSDF mit umgedrehter Normale, der genau das Licht aufnimmt, das beim Principled BSDF wegfällt. EEVEE nutzt den einfachen Shader. Beide Engines liefern damit vergleichbare Ergebnisse.

### Grenzen

- Spiegelungen und Glas bleiben eingebacken.
- Delighting ist eine Heuristik. Große, echte Helligkeitsunterschiede werden mit abgeschwächt.
- Floater bleiben für die Kamera sichtbar. Sie werden nur aus dem Schattenproxy entfernt.
- Auf der Seite, die Cycles als Transmission zählt, gibt es kein Specular. Bei Rauheit 0,8 fällt das kaum auf.
- Die Mond-Richtung wird von Hand gesetzt. Sterne und Lichtverschmutzung fehlen.

### Entwicklung

- `splat_relight/`: Quellcode des Add-ons (Blender Extension)
- `dev/`: Testskripte. `make_test_ply.py` erzeugt eine synthetische Splat-Szene, `compare_engines.py` und `verify_fix.py` rendern sie zum Vergleich in Cycles und EEVEE, `check_panels.py` zeichnet alle Panels headless und prüft Icons, Properties und Operatoren.

Bauen:

```bash
blender --command extension build --source-dir splat_relight --output-dir .
```

### Lizenz

GPL-3.0-or-later
